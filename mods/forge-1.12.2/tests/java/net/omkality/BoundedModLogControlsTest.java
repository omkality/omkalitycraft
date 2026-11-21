package net.omkality;

import java.io.IOException;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import net.omkality.patches.BoundedModLog;

/** Exercise byte limits, UTF-8, native writer lifecycle and I/O failure handling. */
public final class BoundedModLogControlsTest {
    private static void require(boolean value, String check) {
        if (!value) throw new AssertionError(check);
    }

    private static String text(Path file) throws IOException {
        return new String(Files.readAllBytes(file), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("omk-script-logs-");
        Path active = directory.resolve("test.log");
        Path previous = directory.resolve("test.log.omk-log.1");
        Path older = directory.resolve("test.log.omk-log.2");
        try {
            try (OutputStreamWriter log = new OutputStreamWriter(
                    new BoundedModLog(active, Files.newOutputStream(active), 6, 3),
                    StandardCharsets.UTF_8)) {
                for (String line : new String[] {"мир", "ад\n", "рай", "✓"}) {
                    log.write(line);
                    log.flush();
                }
            }
            require(text(older).equals("ад\n"), "oldest retained UTF-8 segment");
            require(text(previous).equals("рай"), "previous UTF-8 segment");
            require(text(active).equals("✓"), "latest UTF-8 segment");
            require(Files.size(active) <= 6 && Files.size(previous) <= 6 && Files.size(older) <= 6,
                    "bounded total retained content");

            try (BoundedModLog log = new BoundedModLog(active, Files.newOutputStream(active), 4, 1)) {
                log.write(new byte[] {1, 2, 3, 4});
                log.write(new byte[] {0, 0, 0, 0, 0});
                require(Files.size(active) == 4, "oversized chunks do not grow the file");
                log.write(9);
                require(Files.readAllBytes(active).length == 1 && Files.readAllBytes(active)[0] == 9,
                        "single-file policy retains latest content");
            }

            try (BoundedModLog log = new BoundedModLog(active, new OutputStream() {
                @Override
                public void write(int value) throws IOException {
                    throw new IOException("simulated full disk");
                }
            }, 6, 2)) {
                log.write(new byte[] {1, 2, 3});
                log.flush();
                log.write(7);
                require(Files.size(active) == 1, "failed write does not interrupt owner or spin during I/O backoff");
            }
        } finally {
            Files.deleteIfExists(older);
            Files.deleteIfExists(previous);
            Files.deleteIfExists(active);
            Files.delete(directory);
        }
        System.out.println("Bounded script log controls passed");
    }
}
