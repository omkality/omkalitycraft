package net.omkality;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.*;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

/** One bounded daemon writer; the tick thread never waits for filesystem I/O. */
final class MetricFile implements AutoCloseable {
    interface Errors { void report(String kind); }
    static final int MAX_BYTES=65536;
    private static final Set<Path> OWNERS=new HashSet<Path>();
    private final Path root;
    private final FileChannel channel;
    private final FileLock lock;
    private final Errors errors;
    private final ArrayBlockingQueue<byte[]> queue=new ArrayBlockingQueue<byte[]>(1);
    private final Thread worker;
    private volatile boolean closing;
    MetricFile(Path path,Errors handler) throws IOException {
        root=path.toAbsolutePath().normalize();errors=handler;
        if(!root.toRealPath(LinkOption.NOFOLLOW_LINKS).equals(root)) throw new IOException("Linked metrics directory");
        // The caller creates the private directory; never clean an unrelated one.
        checkDirectory();
        try(DirectoryStream<Path> entries=Files.newDirectoryStream(root)) {
            for(Path entry:entries) checkFile(entry);
        }
        Path owner=root.resolve(".writer.lock");
        privateFile(owner);
        channel=openOwner(owner);
        FileLock acquired=null;
        try {
            acquired=channel.tryLock();
            if(acquired==null) throw new IOException("Metrics writer already owns directory");
            lock=acquired;
        } catch(IOException error) { channel.close();releaseOwner(root);throw error; }
        catch(RuntimeException error) { channel.close();releaseOwner(root);throw error; }
        worker=new Thread(new Runnable() { public void run() { writeLoop(); } },"Omkality metrics writer");
        worker.setDaemon(true);worker.start();
    }
    private static synchronized FileChannel openOwner(Path owner) throws IOException {
        Path directory=owner.getParent();
        // Avoid opening/closing a second fd on the same inode in this JVM:
        // POSIX record locks can be released by that close, despite Java's guard.
        if(!OWNERS.add(directory)) throw new IOException("Metrics writer already owns directory");
        try { return FileChannel.open(owner,StandardOpenOption.WRITE,LinkOption.NOFOLLOW_LINKS); }
        catch(IOException error) { OWNERS.remove(directory);throw error; }
    }
    private static synchronized void releaseOwner(Path root) { OWNERS.remove(root); }
    static void createDirectory(Path path) throws IOException {
        if(!Files.exists(path,LinkOption.NOFOLLOW_LINKS)) {
            if(FileSystems.getDefault().supportedFileAttributeViews().contains("posix"))
                Files.createDirectories(path,PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
            else Files.createDirectories(path);
        }
    }
    private void checkDirectory() throws IOException {
        if(!Files.isDirectory(root,LinkOption.NOFOLLOW_LINKS) || !root.toRealPath().equals(root)) throw new IOException("Invalid metrics directory");
        if(Files.getFileStore(root).supportsFileAttributeView("posix") && !Files.getPosixFilePermissions(root).equals(PosixFilePermissions.fromString("rwx------")))
            throw new IOException("Metrics directory must be private");
    }
    private void checkFile(Path path) throws IOException {
        if(!Arrays.asList("current.json",".pending",".writer.lock").contains(path.getFileName().toString())
            || !Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS) || Files.size(path)>MAX_BYTES)
            throw new IOException("Unexpected metrics file");
        if(Files.getFileStore(path).supportsFileAttributeView("unix") && ((Number)Files.getAttribute(path,"unix:nlink",LinkOption.NOFOLLOW_LINKS)).intValue()!=1)
            throw new IOException("Hardlinked metrics file");
        if(Files.getFileStore(path).supportsFileAttributeView("posix") && !Files.getPosixFilePermissions(path).equals(PosixFilePermissions.fromString("rw-------")))
            throw new IOException("Metrics file must be private");
    }
    private void privateFile(Path path) throws IOException {
        if(Files.exists(path,LinkOption.NOFOLLOW_LINKS)) { checkFile(path);return; }
        if(Files.getFileStore(root).supportsFileAttributeView("posix"))
            Files.createFile(path,PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
        else Files.createFile(path);
    }
    void offer(String value) {
        if(closing) return;
        byte[] bytes=value.getBytes(StandardCharsets.UTF_8);
        if(bytes.length>MAX_BYTES) throw new IllegalArgumentException("Oversized game metrics");
        if(!queue.offer(bytes)) { queue.poll();queue.offer(bytes); }
    }
    private void writeLoop() {
        try {
            while(!closing || !queue.isEmpty()) {
                byte[] bytes;
                try { bytes=queue.poll(100,TimeUnit.MILLISECONDS); }
                catch(InterruptedException interrupted) { continue; }
                if(bytes==null) continue;
                try { publish(bytes); }
                catch(Exception error) { errors.report(error.getClass().getSimpleName()); }
            }
        } finally {
            try { lock.release();channel.close(); }
            catch(IOException error) { errors.report(error.getClass().getSimpleName()); }
            finally { releaseOwner(root); }
        }
    }
    private void publish(byte[] bytes) throws IOException {
        checkDirectory();
        Path pending=root.resolve(".pending"),current=root.resolve("current.json");
        privateFile(pending);
        if(Files.exists(current,LinkOption.NOFOLLOW_LINKS)) checkFile(current);
        try(FileChannel output=FileChannel.open(pending,StandardOpenOption.WRITE,StandardOpenOption.TRUNCATE_EXISTING,LinkOption.NOFOLLOW_LINKS)) {
            ByteBuffer data=ByteBuffer.wrap(bytes);
            while(data.hasRemaining()) output.write(data);
            output.force(true);
        }
        Files.move(pending,current,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        if(Files.getFileStore(root).supportsFileAttributeView("posix"))
            try(FileChannel directory=FileChannel.open(root,StandardOpenOption.READ)) { directory.force(true); }
    }
    public void close() {
        closing=true;
        try { worker.join(1000); }
        catch(InterruptedException interrupted) { Thread.currentThread().interrupt(); }
        if(worker.isAlive()) errors.report("shutdown_timeout");
    }
}
