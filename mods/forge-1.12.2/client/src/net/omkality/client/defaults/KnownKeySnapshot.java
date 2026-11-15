package net.omkality.client.defaults;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Read-only compatibility view: a key is persisted only when options.txt contains it. */
public final class KnownKeySnapshot {
    public static final int MAX_BYTES = 8 * 1024 * 1024;
    private static final int MAX_KEYS = 4096;
    private static final Pattern LINE = Pattern.compile("^key_(.{1,160}):(-?[0-9]{1,5})(?::(?:NONE|SHIFT|CONTROL|ALT))?$");
    private static final AtomicBoolean warned = new AtomicBoolean();
    private KnownKeySnapshot() {}

    /** Null is a deliberate fallback to the original mod on an unreadable settings file. */
    public static Set<String> current() {
        try {
            Class<?> type = Class.forName("net.minecraft.client.Minecraft");
            Object mc = type.getMethod("func_71410_x").invoke(null);
            File directory = (File)type.getField("field_71412_D").get(mc);
            return read(directory.toPath().resolve("options.txt"));
        } catch (Exception | LinkageError error) {
            if (warned.compareAndSet(false, true)) {
                System.err.println("[OmkalityClient] Default-key persistence uses original behavior: " + error.getClass().getSimpleName());
            }
            return null;
        }
    }

    public static Set<String> read(Path file) throws IOException {
        if (Files.notExists(file, LinkOption.NOFOLLOW_LINKS)) return Collections.emptySet();
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(file)) {
            throw new IOException("Non-regular settings file");
        }
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (InputStream input = Files.newInputStream(file)) {
            byte[] buffer = new byte[4096];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (count > MAX_BYTES - output.size()) throw new IOException("Settings file limit");
                output.write(buffer, 0, count);
            }
        }
        return parse(output.toByteArray());
    }

    public static Set<String> parse(byte[] bytes) throws IOException {
        if (bytes.length > MAX_BYTES) throw new IOException("Settings file limit");
        String text = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes)).toString();
        Set<String> keys = new HashSet<String>();
        for (String line : text.split("\\r?\\n")) {
            Matcher match = LINE.matcher(line);
            if (match.matches()) {
                keys.add(match.group(1));
                if (keys.size() > MAX_KEYS) throw new IOException("Settings key limit");
            }
        }
        return Collections.unmodifiableSet(keys);
    }

    /** Both original List.add sites use this: old records and newly imported defaults. */
    public static boolean record(List<Object> list, Object key, Set<String> saved) {
        return (saved == null || saved.contains(key)) && list.add(key);
    }
}
