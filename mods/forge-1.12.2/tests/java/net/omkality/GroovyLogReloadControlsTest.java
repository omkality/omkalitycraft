package net.omkality;

import java.io.IOException;
import java.io.Writer;
import net.omkality.patches.GroovyLogReloadGuard;

public final class GroovyLogReloadControlsTest {
    private static int checks;
    private static void check(boolean value) { if (!value) throw new AssertionError(); checks++; }
    private static final class TrackingWriter extends Writer {
        int closes;
        boolean closed, fail;
        public void write(char[] data, int off, int length) throws IOException {
            if (closed) throw new IOException("closed fixture");
        }
        public void flush() { }
        public void close() throws IOException {
            closes++; closed = true;
            if (fail) throw new IOException("expected close failure fixture");
        }
    }
    public static void main(String[] args) throws Exception {
        System.setProperty("log4j2.loggerContextFactory", "org.apache.logging.log4j.simple.SimpleLoggerContextFactory");
        GroovyLogReloadGuard.closeOwned(null);
        check(!System.out.checkError());
        TrackingWriter previous = new TrackingWriter();
        previous.write("кириллица");
        GroovyLogReloadGuard.closeOwned(previous);
        check(previous.closed && previous.closes == 1);
        try { previous.write("stale"); throw new AssertionError(); }
        catch (IOException expected) { check(true); }
        try (TrackingWriter current = new TrackingWriter()) {
            current.write("new writer remains usable");
            check(!current.closed && current.closes == 0);
        }
        TrackingWriter failing = new TrackingWriter(); failing.fail = true;
        GroovyLogReloadGuard.closeOwned(failing);
        check(failing.closed && failing.closes == 1);
        check(!System.out.checkError());
        System.out.println("Groovy file logger controls passed: " + checks);
    }
}
