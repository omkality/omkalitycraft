package net.omkality;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class ChatJournalControlsTest {
    private static final int MIB = 1_048_576;
    private static final long DAY = 86_400_000L;

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("omk-chat-controls-");
        try {
            privatePermissions(root);
            long now = System.currentTimeMillis();
            Path old = segment(root, now - 91 * DAY, 1);
            Path full = segment(root, now - 3 * DAY, 2);
            Files.write(old, new byte[512]);
            Files.write(full, new byte[MIB]);
            List<String> warnings = Collections.synchronizedList(new ArrayList<>());
            Map<String, Object> row = Collections.singletonMap("text", "Unicode: ё \"quote\" Ω");
            try (ChatJournal journal = new ChatJournal(root, "dj2", "fixture", 90, MIB, warnings::add)) {
                refused(root, "dj2", warnings);
                for (int i = 0; i < 4096; i++) journal.record(row);
                journal.record(Collections.singletonMap("text", String.join("", Collections.nCopies(8192, "*"))));
            }
            check(!Files.exists(old) && !Files.exists(full), "age and byte rotation");
            List<String> first = lines(root);
            check(first.get(0).contains("\"kind\":\"start\""), "boot recorded");
            String stop = first.get(first.size() - 1);
            check(stop.contains("\"kind\":\"stop\""), "graceful drain");
            Matcher dropped = Pattern.compile("\"dropped\":([0-9]+)").matcher(stop);
            check(dropped.find() && Integer.parseInt(dropped.group(1)) > 0, "bounded input loss visible");
            check(first.stream().anyMatch(line -> line.contains("ё \\\"quote\\\" Ω")), "UTF-8 and escaping");
            refused(root, "other", warnings);
            try (ChatJournal journal = new ChatJournal(root, "dj2", "fixture", 90, MIB, warnings::add)) {
                journal.record(row);
            }
            List<String> restarted = lines(root);
            check(restarted.stream().filter(line -> line.contains("\"kind\":\"stop\"")).count() == 2,
                "clean boot boundaries survive restart");
            check(warnings.isEmpty(), "no unexpected writer failure");
            System.out.println("Chat journal Java controls passed");
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).collect(Collectors.toList())) Files.delete(path);
            }
        }
    }

    private static void refused(Path root, String id, List<String> warnings) throws IOException {
        try (ChatJournal unexpected = new ChatJournal(root, id, "fixture", 90, MIB, warnings::add)) {
            throw new AssertionError("Conflicting writer was accepted");
        } catch (IOException expected) { }
    }

    private static Path segment(Path root, long at, int part) throws IOException {
        Path path = root.resolve(String.format(Locale.ROOT,
            "chat-%013d-0123456789abcdef0123456789abcdef-%09d.jsonl", at, part));
        return Files.createFile(path, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
    }

    private static List<String> lines(Path root) throws IOException {
        List<String> result = new ArrayList<>();
        try (Stream<Path> paths = Files.list(root)) {
            for (Path path : paths.filter(p -> p.getFileName().toString().endsWith(".jsonl")).sorted()
                    .collect(Collectors.toList()))
                result.addAll(Files.readAllLines(path, StandardCharsets.UTF_8));
        }
        return result;
    }

    private static void privatePermissions(Path path) throws IOException {
        Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rwx------"));
    }

    private static void check(boolean success, String name) {
        if (!success) throw new AssertionError(name);
    }
}
