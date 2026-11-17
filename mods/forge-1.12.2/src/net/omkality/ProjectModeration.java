package net.omkality;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/** Bounded reader for the owner-written project state. Game servers open it read-only. */
final class ProjectModeration {
    private static final int MAX_BYTES = 65536;
    private final Path path;
    private final UUID id;
    private Snapshot current;

    private static final class Restriction {
        final long expires;
        final String reason;

        Restriction(long expires, String reason) {
            this.expires = expires;
            this.reason = reason;
        }
    }

    private static final class Snapshot {
        final UUID id;
        final Map<UUID, Restriction> bans = new HashMap<>();
        final Map<UUID, Restriction> mutes = new HashMap<>();

        Snapshot(UUID id) {
            this.id = id;
        }
    }

    static ProjectModeration configured() throws IOException {
        String value = System.getenv("OMK_PROJECT_MODERATION_FILE");
        return value == null ? null : new ProjectModeration(Paths.get(value));
    }

    private ProjectModeration(Path path) throws IOException {
        if (!path.isAbsolute() || !path.equals(path.normalize())) {
            throw new IllegalArgumentException("Use an absolute project moderation file path");
        }
        this.path = path;
        current = read();
        id = current.id;
    }

    String refresh() throws IOException {
        Snapshot next = read();
        if (!id.equals(next.id)) {
            throw new IOException("Project moderation identity changed");
        }
        current = next;
        return id.toString();
    }

    String banReason(UUID player, long now) {
        Restriction ban = current.bans.get(player);
        return ban != null && ban.expires > now ? ban.reason : null;
    }

    boolean muted(UUID player, long now) {
        Restriction mute = current.mutes.get(player);
        return mute != null && mute.expires > now;
    }

    private Snapshot read() throws IOException {
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Project moderation file is missing or linked");
        }
        byte[] bytes;
        try (InputStream input = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS);
             ByteArrayOutputStream buffer = new ByteArrayOutputStream()) {
            byte[] chunk = new byte[4096];
            int count;
            while ((count = input.read(chunk)) != -1) {
                if (buffer.size() + count > MAX_BYTES) {
                    throw new IOException("Project moderation file is too large");
                }
                buffer.write(chunk, 0, count);
            }
            bytes = buffer.toByteArray();
        }
        String content = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes)).toString();
        try {
            return parse(content);
        } catch (IllegalArgumentException invalid) {
            throw new IOException("Invalid project moderation file");
        }
    }

    private static Snapshot parse(String content) {
        String[] lines = content.split("\n", -1);
        String[] header = lines[0].split("\t", -1);
        if (lines.length < 2 || !lines[lines.length - 1].isEmpty()
                || header.length != 2 || !"omk-project-moderation-v1".equals(header[0])) {
            throw new IllegalArgumentException("Invalid moderation header");
        }
        Snapshot snapshot = new Snapshot(uuid(header[1]));
        for (int index = 1; index < lines.length - 1; index++) {
            String[] fields = lines[index].split("\t", -1);
            if (fields.length != 6 || !fields[0].matches("ban|mute")
                    || !fields[2].matches("[A-Za-z0-9_]{1,16}")
                    || !fields[3].matches("[1-9][0-9]{0,11}")
                    || !fields[4].matches("[1-9][0-9]{0,11}") || !validReason(fields[5])) {
                throw new IllegalArgumentException("Invalid moderation record");
            }
            UUID player = uuid(fields[1]);
            long created = Long.parseLong(fields[3]), expires = Long.parseLong(fields[4]);
            Map<UUID, Restriction> records = "ban".equals(fields[0]) ? snapshot.bans : snapshot.mutes;
            if (expires <= created || expires - created > 31536000
                    || records.put(player, new Restriction(expires, fields[5])) != null) {
                throw new IllegalArgumentException("Invalid expiry or duplicate restriction");
            }
        }
        return snapshot;
    }

    private static UUID uuid(String value) {
        UUID parsed = UUID.fromString(value);
        if (!parsed.toString().equals(value)) {
            throw new IllegalArgumentException("Invalid UUID");
        }
        return parsed;
    }

    private static boolean validReason(String reason) {
        return !reason.isEmpty() && reason.codePointCount(0, reason.length()) <= 128
            && reason.codePoints().noneMatch(ProjectModeration::invalidCharacter);
    }

    private static boolean invalidCharacter(int character) {
        int type = Character.getType(character);
        return character == 167 || type == Character.CONTROL || type == Character.FORMAT
            || type == Character.SURROGATE || type == Character.PRIVATE_USE;
    }
}
