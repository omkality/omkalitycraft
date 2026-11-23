package net.omkality;

import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

/** Exact required mods plus named, version-pinned optional client mods. */
final class ClientModPolicy {
    private final Map<String, String> required = new HashMap<>();
    private final Map<String, String> optional = new HashMap<>();

    ClientModPolicy(Properties properties) {
        if (properties.isEmpty() || properties.size() > 1000) {
            throw new IllegalArgumentException("Invalid client mod count");
        }
        for (String entry : properties.stringPropertyNames()) {
            boolean optionalMod = entry.startsWith("?");
            String id = optionalMod ? entry.substring(1) : entry;
            String version = properties.getProperty(entry);
            // Some legacy coremods legitimately declare an empty version.
            if (!id.matches("[A-Za-z0-9_.-]{1,100}") || version.length() > 100) {
                throw new IllegalArgumentException("Invalid client mod entry");
            }
            (optionalMod ? optional : required).put(id, version);
        }
        if (required.isEmpty() || optional.keySet().stream().anyMatch(required::containsKey)) {
            throw new IllegalArgumentException("Invalid set of required and optional client mods");
        }
    }

    boolean accepts(Map<String, String> remote) {
        if (remote == null || !remote.entrySet().containsAll(required.entrySet())) {
            return false;
        }
        return remote.entrySet().stream().allMatch(entry -> required.containsKey(entry.getKey())
            || (optional.containsKey(entry.getKey()) && optional.get(entry.getKey()).equals(entry.getValue())));
    }

    int requiredCount() { return required.size(); }

    int optionalCount() { return optional.size(); }
}
