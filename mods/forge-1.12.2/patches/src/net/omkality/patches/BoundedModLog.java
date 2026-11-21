package net.omkality.patches;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

/** Bounds the dedicated-server Groovy log at its native byte stream. */
public final class BoundedModLog extends OutputStream {
    private static final int MAX_FILES = 8;
    private static final long RETRY_DELAY = TimeUnit.SECONDS.toNanos(5);
    private final Path file;
    private final long limit;
    private final int files;
    private OutputStream stream;
    private long length;
    private long failedAt;
    private boolean retrying;
    private boolean oversized;
    private boolean closed;


    /** Wrap the publisher's already opened truncating log stream for a known server log. */
    public static OutputStream wrap(Path path, OutputStream stream) {
        Path file = path.toAbsolutePath().normalize();
        Path cwd = Paths.get("").toAbsolutePath().normalize();
        if (!file.equals(cwd.resolve("logs/groovy_server.log"))) {
            return stream;
        }
        long limit = setting("OMK_GROOVY_LOG_MIB", 8, 64) * 1024L * 1024L;
        int files = setting("OMK_GROOVY_LOG_FILES", 3, MAX_FILES);
        BoundedModLog log = new BoundedModLog(file, stream, limit, files);
        log.trimArchives();
        return log;
    }

    /** Use byte-granular limits for verification of the stream in isolation. */
    public BoundedModLog(Path file, OutputStream stream, long limit, int files) {
        if (limit < 1 || files < 1 || files > MAX_FILES) {
            throw new IllegalArgumentException("Invalid mod log retention policy");
        }
        this.file = file;
        this.stream = stream;
        this.limit = limit;
        this.files = files;
    }

    private static int setting(String name, int defaultValue, int max) {
        String raw = System.getenv(name);
        if (raw == null) return defaultValue;
        if (!raw.matches("[1-9][0-9]?") || Integer.parseInt(raw) > max) {
            throw new IllegalArgumentException("Invalid " + name);
        }
        return Integer.parseInt(raw);
    }

    private Path archive(int index) {
        return file.resolveSibling(file.getFileName() + ".omk-log." + index);
    }

    private void trimArchives() {
        try {
            for (int index = 1; index < MAX_FILES; index++) {
                Path archive = archive(index);
                if (Files.isRegularFile(archive, LinkOption.NOFOLLOW_LINKS) &&
                        (index >= files || Files.size(archive) > limit)) {
                    Files.delete(archive);
                }
            }
        } catch (IOException | SecurityException failure) {
            System.err.println("Omkality: could not enforce script log archive retention for " + file.getFileName());
        }
    }

    private void rotate() throws IOException {
        closeStream();
        if (files > 1) {
            for (int index = files - 1; index > 1; index--) {
                Path previous = archive(index - 1);
                if (Files.exists(previous, LinkOption.NOFOLLOW_LINKS)) {
                    Files.move(previous, archive(index), StandardCopyOption.REPLACE_EXISTING);
                }
            }
            Files.move(file, archive(1), StandardCopyOption.REPLACE_EXISTING);
        }
        stream = Files.newOutputStream(file, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING,
                LinkOption.NOFOLLOW_LINKS);
        length = 0;
    }

    private void closeStream() throws IOException {
        OutputStream owned = stream;
        stream = null;
        if (owned != null) owned.close();
    }

    private void fail() {
        if (!retrying) {
            System.err.println("Omkality: script log writes paused after an I/O failure for " + file.getFileName());
        }
        failedAt = System.nanoTime();
        retrying = true;
        try {
            closeStream();
        } catch (IOException ignored) {
            // The next attempt opens a new descriptor and reads the current size.
        }
    }

    @Override
    public synchronized void write(int value) {
        write(new byte[] {(byte) value}, 0, 1);
    }

    @Override
    public synchronized void write(byte[] data, int offset, int count) {
        Objects.requireNonNull(data);
        if (offset < 0 || count < 0 || count > data.length - offset) {
            throw new IndexOutOfBoundsException();
        }
        if (closed || count == 0 || (retrying && System.nanoTime() - failedAt < RETRY_DELAY)) return;
        if (count > limit) {
            if (!oversized) {
                System.err.println("Omkality: skipped an oversized script log write for " + file.getFileName());
                oversized = true;
            }
            return;
        }
        try {
            if (stream == null) {
                stream = Files.newOutputStream(file, StandardOpenOption.CREATE, StandardOpenOption.APPEND,
                        LinkOption.NOFOLLOW_LINKS);
                length = Files.size(file);
            }
            if (length + count > limit) rotate();
            stream.write(data, offset, count);
            length += count;
            retrying = false;
        } catch (IOException | SecurityException failure) {
            fail();
        }
    }

    @Override
    public synchronized void flush() {
        if (stream == null) return;
        try {
            stream.flush();
        } catch (IOException failure) {
            fail();
        }
    }

    @Override
    public synchronized void close() {
        closed = true;
        try {
            closeStream();
        } catch (IOException failure) {
            fail();
        }
    }
}
