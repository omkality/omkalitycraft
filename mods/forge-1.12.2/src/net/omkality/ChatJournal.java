package net.omkality;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import java.util.regex.Pattern;

/** Bounded private journal. Only the worker scans, rotates and syncs files. */
final class ChatJournal implements AutoCloseable {
    private static final long DAY = 86_400_000L;
    private static final int SEGMENT_BYTES = 1_048_576;
    private static final int SEGMENTS = 512;
    static final int RECORD_BYTES = 8192;
    static final Pattern SEGMENT = Pattern.compile("chat-[0-9]{13}-[0-9a-f]{32}-[0-9]{9}\\.jsonl");
    private static final Set<Path> OWNED = new HashSet<>();
    private static final Set<PosixFilePermission> DIR_MODE = PosixFilePermissions.fromString("rwx------");
    private static final Set<PosixFilePermission> FILE_MODE = PosixFilePermissions.fromString("rw-------");
    private final ArrayBlockingQueue<byte[]> queue = new ArrayBlockingQueue<>(256);
    private final AtomicLong observed = new AtomicLong(), lost = new AtomicLong();
    private final Path root;
    private final int budget, days;
    private final String server, profile;
    private final String boot = UUID.randomUUID().toString().replace("-", "");
    private final Consumer<String> warning;
    private final FileChannel owner;
    private final FileLock lock;
    private final Thread worker;
    private volatile boolean closing;
    private Path current;
    private int part;

    ChatJournal(Path path, String server, String profile, int days, int budget, Consumer<String> warning)
            throws IOException {
        this.root = path.toAbsolutePath().normalize();
        this.profile = profile;
        this.server = server;
        this.days = days;
        this.budget = budget;
        this.warning = warning;
        requireDirectory();
        owner = acquire(root);
        try {
            FileLock acquired = owner.tryLock();
            if (acquired == null) throw new IOException("Chat history already has a writer");
            bindOwner();
            lock = acquired;
        } catch (IOException | RuntimeException error) {
            owner.close();
            release(root);
            throw error;
        }
        worker = new Thread(this::writeLoop, "Omkality chat history writer");
        worker.setDaemon(true);
        worker.start();
    }

    private static synchronized FileChannel acquire(Path root) throws IOException {
        if (!OWNED.add(root)) throw new IOException("Chat history already has a writer");
        Path owner = root.resolve(".writer.lock");
        try {
            if (!Files.exists(owner, LinkOption.NOFOLLOW_LINKS))
                Files.createFile(owner, PosixFilePermissions.asFileAttribute(FILE_MODE));
            requireFile(owner);
            return FileChannel.open(owner, StandardOpenOption.READ, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS);
        } catch (IOException | RuntimeException error) {
            release(root);
            throw error;
        }
    }

    private static synchronized void release(Path root) {
        OWNED.remove(root);
    }

    private void bindOwner() throws IOException {
        byte[] identity = (server + "\n" + profile + "\n").getBytes(StandardCharsets.UTF_8);
        if (owner.size() == 0) {
            ByteBuffer bytes = ByteBuffer.wrap(identity);
            while (bytes.hasRemaining()) owner.write(bytes);
            owner.force(true);
            return;
        }
        if (owner.size() != identity.length) throw new IOException("Chat history belongs to another server");
        ByteBuffer previous = ByteBuffer.allocate(identity.length);
        while (previous.hasRemaining() && owner.read(previous) >= 0) { }
        if (!Arrays.equals(identity, previous.array())) throw new IOException("Chat history belongs to another server");
    }

    private void requireDirectory() throws IOException {
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS) || !root.toRealPath().equals(root)
                || !Files.getPosixFilePermissions(root).equals(DIR_MODE))
            throw new IOException("Chat history needs a dedicated private directory");
    }

    private static long requireFile(Path path) throws IOException {
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                || !Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS).equals(FILE_MODE)
                || ((Number)Files.getAttribute(path, "unix:nlink", LinkOption.NOFOLLOW_LINKS)).intValue() != 1)
            throw new IOException("Chat history file is not private");
        return Files.size(path);
    }

    synchronized void record(Map<String, Object> message) {
        if (closing) return;
        Map<String, Object> row = row("message", System.currentTimeMillis());
        row.put("sequence", observed.incrementAndGet());
        row.putAll(message);
        byte[] bytes = encode(row);
        if (bytes.length > RECORD_BYTES || !queue.offer(bytes)) lost.incrementAndGet();
    }

    synchronized void omitted() {
        observed.incrementAndGet();
        lost.incrementAndGet();
    }

    private Map<String, Object> row(String kind, long at) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("schema", 1);
        row.put("kind", kind);
        row.put("at_ms", at);
        row.put("server", server);
        row.put("profile", profile);
        row.put("core_version", OmkalityCore.VERSION);
        row.put("boot", boot);
        return row;
    }

    private byte[] control(String kind, long at, long dropped) {
        Map<String, Object> row = row(kind, at);
        row.put("dropped", dropped);
        row.put("retention_days", days);
        row.put("budget_bytes", budget);
        return encode(row);
    }

    private static byte[] encode(Map<String, Object> row) {
        return (CommandCatalog.json(row) + "\n").getBytes(StandardCharsets.UTF_8);
    }

    private void writeLoop() {
        boolean started = false;
        long lastCheckpoint = 0, lastLoss = -1, lastWarning = 0;
        try (FileChannel ignored = owner; FileLock held = lock) {
            while (true) {
                List<byte[]> batch = new ArrayList<>(34);
                // Wait between batches, including when the queue is busy.
                TimeUnit.MILLISECONDS.sleep(250);
                queue.drainTo(batch, 32);
                int messages = batch.size();
                boolean end = closing && queue.isEmpty();
                long now = System.currentTimeMillis(), dropped = lost.get();
                long tick = System.nanoTime();
                boolean checkpoint = end || !started || dropped != lastLoss
                    || tick - lastCheckpoint >= TimeUnit.MINUTES.toNanos(1);
                if (!started) batch.add(0, control("start", now, dropped));
                if (checkpoint) batch.add(control(end ? "stop" : "checkpoint", now, dropped));
                try {
                    if (!batch.isEmpty()) append(batch, now);
                    started = true;
                    if (checkpoint) {
                        lastCheckpoint = tick;
                        lastLoss = dropped;
                    }
                } catch (IOException | RuntimeException failure) {
                    current = null;
                    lost.addAndGet(messages);
                    if (lastWarning == 0 || tick - lastWarning >= TimeUnit.MINUTES.toNanos(1)) {
                        lastWarning = tick;
                        warning.accept("write_failed");
                    }
                    if (!end) TimeUnit.SECONDS.sleep(1);
                }
                if (end) return;
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            warning.accept("interrupted");
        } catch (IOException error) {
            warning.accept("close_failed");
        } finally {
            release(root);
        }
    }

    private void append(List<byte[]> rows, long now) throws IOException {
        requireDirectory();
        int bytes = 0;
        for (byte[] row : rows) bytes += row.length;
        long currentBytes = current == null ? 0 : requireFile(current);
        boolean rotate = current == null || time(current) / DAY != now / DAY
            || currentBytes + bytes > SEGMENT_BYTES;
        prune(now, bytes, !rotate ? current : null);
        if (rotate) {
            current = root.resolve(String.format(Locale.ROOT, "chat-%013d-%s-%09d.jsonl", now, boot, ++part));
            Files.createFile(current, PosixFilePermissions.asFileAttribute(FILE_MODE));
        }
        try (FileChannel output = FileChannel.open(current, StandardOpenOption.WRITE, StandardOpenOption.APPEND,
                LinkOption.NOFOLLOW_LINKS)) {
            for (byte[] row : rows) {
                ByteBuffer buffer = ByteBuffer.wrap(row);
                while (buffer.hasRemaining()) output.write(buffer);
            }
            output.force(true);
        }
        if (rotate) try (FileChannel directory = FileChannel.open(root, StandardOpenOption.READ)) {
            directory.force(true);
        }
    }

    private void prune(long now, int bytes, Path keep) throws IOException {
        List<Path> segments = new ArrayList<>();
        long occupied = 0;
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(root, "chat-*.jsonl")) {
            for (Path path : entries) {
                if (!SEGMENT.matcher(path.getFileName().toString()).matches() || segments.size() >= SEGMENTS)
                    throw new IOException("Unexpected chat segment layout");
                long size = requireFile(path);
                if (size > SEGMENT_BYTES) throw new IOException("Oversized chat segment");
                if (!path.equals(keep) && time(path) <= now - days * DAY) {
                    Files.delete(path);
                } else {
                    segments.add(path);
                    occupied += size;
                }
            }
        }
        segments.sort(Comparator.naturalOrder());
        int count = segments.size() + (keep == null ? 1 : 0);
        for (Path path : segments) {
            if (occupied + bytes <= budget && count <= SEGMENTS) return;
            if (path.equals(keep)) continue;
            occupied -= requireFile(path);
            Files.delete(path);
            count--;
        }
        if (occupied + bytes > budget || count > SEGMENTS) throw new IOException("Chat history quota is too small");
    }

    private static long time(Path path) {
        return Long.parseLong(path.getFileName().toString().substring(5, 18));
    }

    @Override
    public void close() {
        closing = true;
        try {
            worker.join(3000);
            if (worker.isAlive()) warning.accept("shutdown_timeout");
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            warning.accept("shutdown_interrupted");
        }
    }
}
