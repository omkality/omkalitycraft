package omk.lab.trace;

import java.io.*;
import java.lang.instrument.Instrumentation;
import java.nio.file.*;

/** JDK-only observer. Does not load ASM or modify game/loader classes. */
public final class ConsoleStartupAgent {
    private static final String MARKER = "A re-entrant transformer 'net.minecraftforge.fml.common.asm.transformers.DeobfuscationTransformer'";
    private static Path directory;
    private static volatile boolean captured;
    private static volatile boolean gameOutputSeen;

    public static void premain(String args, Instrumentation unused) throws Exception {
        directory = Paths.get(args).toRealPath();
        if (!Files.isRegularFile(directory.resolve("lab-trace-owner"))) {
            throw new IllegalArgumentException("Expected an isolated lab trace directory");
        }
        Files.write(directory.resolve("trace.txt"),
            "agent-ready\ntrace-mode=console\nconsole-hook-armed\n".getBytes("UTF-8"), StandardOpenOption.CREATE_NEW);
        System.setOut(observe(System.out));
        System.setErr(observe(System.err));
    }

    private static PrintStream observe(final PrintStream original) throws Exception {
        final byte[] pattern = MARKER.getBytes("US-ASCII");
        final byte[] gamePattern = "Forge Mod Loader version 14.23.5.2860".getBytes("US-ASCII");
        return new PrintStream(new OutputStream() {
            private int position;
            private int gamePosition;
            public void write(int value) {
                original.write(value);
                accept(value);
            }
            public synchronized void write(byte[] bytes, int offset, int length) {
                original.write(bytes, offset, length);
                for (int index = offset; index < offset + length; index++) accept(bytes[index] & 255);
            }
            public void flush() { original.flush(); }
            // Never close the original stdout/stderr owned by the JVM.
            public void close() { flush(); }
            private void accept(int value) {
                if (!gameOutputSeen) {
                    if (value == (gamePattern[gamePosition] & 255)) gamePosition++;
                    else gamePosition = value == (gamePattern[0] & 255) ? 1 : 0;
                    if (gamePosition == gamePattern.length) {
                        gamePosition = 0;
                        gameOutputSeen = true;
                        try { Files.write(directory.resolve("trace.txt"), "console-game-log-observed\n".getBytes("UTF-8"), StandardOpenOption.APPEND); }
                        catch (IOException ignored) { }
                    }
                }
                if (captured) return;
                if (value == (pattern[position] & 255)) position++;
                else position = value == (pattern[0] & 255) ? 1 : 0;
                if (position == pattern.length) { position = 0; capture(); }
            }
        }, true, "UTF-8");
    }

    private static synchronized void capture() {
        if (captured) return;
        captured = true;
        StringBuilder text = new StringBuilder("DEOBF-EXCLUDED console-stack\n");
        StackTraceElement[] frames = new Throwable().getStackTrace();
        for (int index = 0; index < frames.length && index < 80; index++) {
            text.append("  ").append(frames[index].toString()).append('\n');
        }
        try {
            Files.write(directory.resolve("trace.txt"), text.toString().getBytes("UTF-8"), StandardOpenOption.APPEND);
        } catch (IOException failure) {
            // Preserve normal game output even if the diagnostic disk fails.
        }
    }

    public static void main(String[] args) throws Exception {
        if (!Boolean.getBoolean("omkality.lab.consoleProbe")) throw new IllegalArgumentException("Lab probe only");
        System.out.println("Forge Mod Loader version 14.23.5.2860");
        // Split writes exercise matching across buffer boundaries.
        System.out.print(MARKER.substring(0, 24));
        System.out.println(MARKER.substring(24));
        System.out.flush();
        if (!captured) throw new AssertionError("Console event was not observed");
        System.out.println("console-probe-passed");
    }
}
