package net.omkality;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;
import net.omkality.api.CoreServices;

/** Read-only diagnostic export, enabled only by an explicit lab JVM property. */
final class CommandCatalog {
    private static Object call(Object target, String name, Class<?>[] types, Object... args) throws Exception {
        Method method = target.getClass().getMethod(name, types);
        method.setAccessible(true);
        return method.invoke(target, args);
    }
    private static Object call(Object target, String name) throws Exception {
        return call(target, name, new Class<?>[0]);
    }
    private static Object field(Object target, String name) throws Exception {
        Field field = target.getClass().getField(name);
        field.setAccessible(true);
        return field.get(target);
    }
    private static Object singleton(String type) throws Exception {
        return Class.forName(type).getField("INSTANCE").get(null);
    }
    private static Object optional(Object target, String name) {
        try { return call(target, name); } catch (Exception error) { return null; }
    }
    private static Object optionalField(Object target, String name) {
        try { return field(target, name); } catch (Exception error) { return null; }
    }

    static void write(ServerProfile profile) throws Exception {
        Object common = Class.forName("net.minecraftforge.fml.common.FMLCommonHandler").getMethod("instance").invoke(null);
        Object server = call(common, "getMinecraftServerInstance");
        Object manager = call(server, "func_71187_D");
        Map<?, ?> registered = (Map<?, ?>) call(manager, "func_71555_a");
        Map<Object, List<String>> aliases = new IdentityHashMap<Object, List<String>>();
        for (Map.Entry<?, ?> entry : registered.entrySet()) {
            Object command = entry.getValue();
            if (!aliases.containsKey(command)) aliases.put(command, new ArrayList<String>());
            aliases.get(command).add(entry.getKey().toString());
        }
        boolean ftb="enabled".equals(CoreServices.statuses().get("ftb.integration"));
        Object ranks = ftb ? singleton("com.feed_the_beast.ftbutilities.ranks.Ranks") : null;
        Map<?, ?> wrappers = ftb ? (Map<?, ?>) field(ranks, "commands") : Collections.emptyMap();
        Map<Object, String> nodes = new IdentityHashMap<Object, String>();
        for (Map.Entry<?, ?> entry : wrappers.entrySet()) {
            nodes.put(field(entry.getValue(), "mirrored"), entry.getKey().toString());
            nodes.put(entry.getValue(), entry.getKey().toString());
        }
        List<Map<String, Object>> commands = new ArrayList<Map<String, Object>>();
        Set<Object> visited = Collections.newSetFromMap(new IdentityHashMap<Object, Boolean>());
        for (Object command : aliases.keySet()) describe(command, "", server, aliases, nodes, visited, commands, 0);
        Collections.sort(commands, new Comparator<Map<String, Object>>() {
            public int compare(Map<String, Object> a, Map<String, Object> b) { return a.get("path").toString().compareTo(b.get("path").toString()); }
        });
        Map<String, Object> output = new LinkedHashMap<String, Object>();
        output.put("schema", 1);
        output.put("minecraft", "1.12.2");
        output.put("profile",profile.id);
        output.put("required_capabilities",profile.capabilities);
        output.put("required_extensions",profile.extensions);
        output.put("account_recovery_connections", RecoveryConnections.state);
        Map<String, String> serverMods = new TreeMap<String, String>();
        for (net.minecraftforge.fml.common.ModContainer mod : net.minecraftforge.fml.common.Loader.instance().getIndexedModList().values()) {
            serverMods.put(mod.getModId(), mod.getVersion());
        }
        output.put("core", serverMods.get("omkalitycore"));
        output.put("server_mods", serverMods);
        Map<String,String> states=CoreServices.statuses();
        output.put("extensions",CoreServices.extensions());
        output.put("capabilities",states);
        output.put("vanilla_boundary_guard",states.get("fix.vanilla"));
        output.put("autonomous_inventory_guard",states.get("fix.twilight.inventory"));
        output.put("autonomous_world_effect_guard",states.get("fix.twilight.world"));
        output.put("ftb_mute_guard",states.get("ftb.mute"));
        output.put("ftb_claim_guard",states.get("ftb.containers"));
        output.put("ftb_spawn_claims",states.get("ftb.spawn"));
        output.put("ftb_dimension_rtp",states.get("ftb.rtp"));
        output.put("commands", commands);
        output.put("rank_configs", ftb ? rankConfigs(ranks) : Collections.emptyList());
        output.put("permissions", permissions());
        Files.write(Paths.get("omk-command-catalog.json"), json(output).getBytes(StandardCharsets.UTF_8));
    }

    private static void describe(Object command, String prefix, Object server, Map<Object, List<String>> aliases,
            Map<Object, String> nodes, Set<Object> visited, List<Map<String, Object>> result, int depth) throws Exception {
        if (!visited.add(command)) return;
        if (depth > 8 || result.size() > 4096) throw new IllegalStateException("Command tree exceeds diagnostic bounds");
        Object original = optionalField(command, "mirrored");
        if (original == null) original = command;
        String name = call(command, "func_71517_b").toString();
        String path = prefix.isEmpty() ? "/" + name : prefix + " " + name;
        Map<String, Object> row = new LinkedHashMap<String, Object>();
        row.put("path", path);
        row.put("class", original.getClass().getName());
        row.put("aliases", optional(command, "func_71514_a"));
        row.put("registry_keys", aliases.get(command));
        row.put("permission_node", nodes.get(command));
        row.put("base_level", optional(original, "func_82362_a"));
        Class<?> sender = Class.forName("net.minecraft.command.ICommandSender");
        try { row.put("usage", call(command, "func_71518_a", new Class<?>[]{sender}, server)); }
        catch (Exception error) { row.put("usage", null); }
        Object mod = optionalField(command, "modContainer");
        row.put("mod_id", mod == null ? null : optional(mod, "getModId"));
        row.put("mod_version", mod == null ? null : optional(mod, "getVersion"));
        result.add(row);
        Object children = optional(original, "getSubCommands");
        if (children instanceof Collection) {
            for (Object child : (Collection<?>) children) describe(child, path, server, aliases, nodes, visited, result, depth + 1);
        }
    }

    private static List<Map<String, Object>> rankConfigs(Object ranks) throws Exception {
        Class<?> api = Class.forName("com.feed_the_beast.ftblib.lib.config.RankConfigAPI");
        Object handler = api.getMethod("getHandler").invoke(null);
        Collection<?> values = (Collection<?>) call(handler, "getRegisteredConfigs");
        Object player = call(ranks, "getDefaultPlayerRank");
        Object op = call(ranks, "getDefaultOPRank");
        List<Map<String, Object>> rows = new ArrayList<Map<String, Object>>();
        for (Object info : values) {
            String node = field(info, "node").toString();
            Map<String, Object> row = new LinkedHashMap<String, Object>();
            row.put("node", node);
            row.put("default_player", call(field(info, "defaultValue"), "getString"));
            row.put("default_op", call(field(info, "defaultOPValue"), "getString"));
            row.put("lab_player_override", call(player, "getPermission", new Class<?>[]{String.class}, node));
            row.put("lab_op_override", call(op, "getPermission", new Class<?>[]{String.class}, node));
            rows.add(row);
        }
        return rows;
    }

    private static List<Map<String, Object>> permissions() throws Exception {
        Object handler = singleton("net.minecraftforge.server.permission.DefaultPermissionHandler");
        Collection<?> nodes = (Collection<?>) call(handler, "getRegisteredNodes");
        List<Map<String, Object>> rows = new ArrayList<Map<String, Object>>();
        for (Object node : nodes) {
            Map<String, Object> row = new LinkedHashMap<String, Object>();
            row.put("node", node.toString());
            row.put("default", call(handler, "getDefaultPermissionLevel", new Class<?>[]{String.class}, node).toString());
            row.put("description", call(handler, "getNodeDescription", new Class<?>[]{String.class}, node));
            rows.add(row);
        }
        return rows;
    }

    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map) {
            List<String> values = new ArrayList<String>();
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) values.add(json(entry.getKey().toString()) + ":" + json(entry.getValue()));
            return "{" + String.join(",", values) + "}";
        }
        if (value instanceof Collection) {
            List<String> values = new ArrayList<String>();
            for (Object entry : (Collection<?>) value) values.add(json(entry));
            return "[" + String.join(",", values) + "]";
        }
        StringBuilder text = new StringBuilder("\"");
        for (char c : value.toString().toCharArray()) {
            if (c == '"' || c == '\\') text.append('\\').append(c);
            else if (c < 32) text.append(String.format("\\u%04x", (int)c));
            else text.append(c);
        }
        return text.append('"').toString();
    }
}
