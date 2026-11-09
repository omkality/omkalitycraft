package net.omkality;

import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.function.Function;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.CommandEvent;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import org.apache.logging.log4j.Logger;

/** Opt-in DJ2 RTP adapter. FTB owns permission, warmup, cooldown and history.
 * Search touches only already generated chunks, with bounded trials/chunk loads.
 * MC reflection is resolved once because the private build has no mapped stubs.
 */
public final class FtbRtpGuard {
    static String state = "not configured";
    private final Logger log;
    private final Map<Integer, int[]> worlds = new HashMap<Integer, int[]>();
    private final Map<Object, Long> attempts = new WeakHashMap<Object, Long>();
    private final Random random = new Random();
    private int minimum, maximum, percent, maxTrials, maxLoads, retrySeconds;
    private boolean failed;
    private final Class<?> player;
    private final Field dimension, world;
    private final Method sender, command, name, parameters, permission, alive;
    private final Method dataGet, forgePlayer, online, cooldown, teleport, rank, ticks, seconds;
    private final Method blockState, material, liquid, block, registry, full, air, generated, chunk;
    private final Method worldBorder, contains, centerX, centerZ, diameter, claimed, processQueue;
    private final Method sendMessage, nativeArgs, destination;
    private final Constructor<?> position, plain, translation, chunkPosition;
    private final Object timer, claims;

    public static void install(Path config, Logger log) throws Exception {
        Path file = config.resolve("omkalitycore-rtp.properties");
        if (!Files.exists(file, LinkOption.NOFOLLOW_LINKS)) return;
        FtbMuteGuard.requireVersion("ftbutilities", "5.4.1.131");
        FtbMuteGuard.requireVersion("ftblib", "5.4.7.2");
        MinecraftForge.EVENT_BUS.register(new FtbRtpGuard(file, log));
        state = "enabled";
        log.info("Omkality dimension RTP enabled (generated chunks only)");
    }

    private static Method m(Class<?> c, String srg, String dev, Class<?>... types) throws Exception {
        try { return c.getMethod(srg, types); }
        catch (NoSuchMethodException e) { return c.getMethod(dev, types); }
    }
    private static Field f(Class<?> c, String srg, String dev) throws Exception {
        try { return c.getField(srg); }
        catch (NoSuchFieldException e) { return c.getField(dev); }
    }
    private static Class<?> c(String type) throws Exception { return Class.forName(type); }

    private FtbRtpGuard(Path file, Logger logger) throws Exception {
        log = logger;
        parse(file);
        player = c("net.minecraft.entity.player.EntityPlayerMP");
        Class<?> base = c("net.minecraft.entity.player.EntityPlayer"), entity = c("net.minecraft.entity.Entity");
        Class<?> level = c("net.minecraft.world.World"), pos = c("net.minecraft.util.math.BlockPos");
        Class<?> state = c("net.minecraft.block.state.IBlockState"), mat = c("net.minecraft.block.material.Material");
        Class<?> source = c("net.minecraft.command.ICommandSender");
        dimension = f(entity, "field_71093_bK", "dimension");
        world = f(entity, "field_70170_p", "world");
        alive = m(entity, "func_70089_S", "isEntityAlive");
        sender = CommandEvent.class.getMethod("getSender");
        command = CommandEvent.class.getMethod("getCommand");
        parameters = CommandEvent.class.getMethod("getParameters");
        name = m(c("net.minecraft.command.ICommand"), "func_71517_b", "getName");
        permission = c("net.minecraftforge.server.permission.PermissionAPI").getMethod("hasPermission", base, String.class);
        forgePlayer = c("com.feed_the_beast.ftblib.lib.command.CommandUtils").getMethod("getForgePlayer", source);
        online = forgePlayer.getReturnType().getMethod("getNullablePlayer");
        Class<?> data = c("com.feed_the_beast.ftbutilities.data.FTBUtilitiesPlayerData");
        Class<?> timers = c("com.feed_the_beast.ftbutilities.data.FTBUtilitiesPlayerData$Timer");
        timer = timers.getField("RTP").get(null);
        dataGet = data.getMethod("get", c("com.feed_the_beast.ftblib.lib.data.ForgePlayer"));
        cooldown = data.getMethod("checkTeleportCooldown", source, timers);
        teleport = timers.getMethod("teleport", player, Function.class, c("com.feed_the_beast.ftblib.lib.util.misc.IScheduledTask"));
        rank = c("com.feed_the_beast.ftblib.lib.config.RankConfigAPI").getMethod("get", player, String.class);
        ticks = c("com.feed_the_beast.ftblib.lib.config.ConfigValue").getMethod("getTimer");
        seconds = ticks.getReturnType().getMethod("seconds");
        position = pos.getConstructor(int.class, int.class, int.class);
        blockState = m(level, "func_180495_p", "getBlockState", pos);
        air = m(level, "func_175623_d", "isAirBlock", pos);
        generated = m(level, "func_190526_b", "isChunkGeneratedAt", int.class, int.class);
        chunk = m(level, "func_72964_e", "getChunkFromChunkCoords", int.class, int.class);
        material = m(state, "func_185904_a", "getMaterial");
        liquid = m(mat, "func_76224_d", "isLiquid");
        full = m(state, "func_185913_b", "isFullCube");
        block = m(state, "func_177230_c", "getBlock");
        registry = c("net.minecraft.block.Block").getMethod("getRegistryName");
        worldBorder = m(level, "func_175723_af", "getWorldBorder");
        Class<?> border = worldBorder.getReturnType();
        contains = m(border, "func_177746_a", "contains", pos);
        centerX = m(border, "func_177731_f", "getCenterX");
        centerZ = m(border, "func_177721_g", "getCenterZ");
        diameter = m(border, "func_177741_h", "getDiameter");
        Class<?> claimType = c("com.feed_the_beast.ftbutilities.data.ClaimedChunks");
        if (!Boolean.TRUE.equals(claimType.getMethod("isActive").invoke(null)))
            throw new IllegalStateException("RTP requires active FTB claims");
        claims = claimType.getField("instance").get(null);
        chunkPosition = c("com.feed_the_beast.ftblib.lib.math.ChunkDimPos").getConstructor(int.class, int.class, int.class);
        claimed = claimType.getMethod("getChunk", chunkPosition.getDeclaringClass());
        processQueue = claimType.getMethod("processQueue");
        destination = c("com.feed_the_beast.ftblib.lib.math.TeleporterDimPos")
            .getMethod("of", double.class, double.class, double.class, int.class);
        sendMessage = m(source, "func_145747_a", "sendMessage", c("net.minecraft.util.text.ITextComponent"));
        plain = c("net.minecraft.util.text.TextComponentString").getConstructor(String.class);
        translation = c("net.minecraft.util.text.TextComponentTranslation").getConstructor(String.class, Object[].class);
        nativeArgs = m(c("net.minecraft.command.CommandException"), "func_74844_a", "getErrorObjects");
    }

    private void parse(Path file) throws Exception {
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || Files.size(file) > 4096)
            throw new IllegalArgumentException("Invalid RTP policy file");
        Map<String, String> fields = new HashMap<String, String>();
        for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
            if (line.isEmpty() || line.startsWith("#")) continue;
            String[] parts = line.split("=", -1);
            if (parts.length != 2 || fields.put(parts[0], parts[1]) != null)
                throw new IllegalArgumentException("Duplicate or invalid RTP field");
        }
        if (fields.size() != 8 || !"1".equals(fields.get("version")))
            throw new IllegalArgumentException("Incomplete RTP policy");
        minimum = number(fields.get("minimum"), 0, 100000);
        maximum = number(fields.get("maximum"), 1, 100000);
        percent = number(fields.get("border_percent"), 10, 90);
        maxTrials = number(fields.get("attempts"), 1, 256);
        maxLoads = number(fields.get("chunk_loads"), 1, 16);
        retrySeconds = number(fields.get("retry_seconds"), 2, 60);
        if (minimum >= maximum) throw new IllegalArgumentException("Inverted RTP range");
        String rows = fields.get("worlds");
        if (rows == null || rows.split(";", -1).length > 8) throw new IllegalArgumentException("Invalid RTP worlds");
        for (String row : rows.split(";", -1)) {
            String[] parts = row.split(":", -1);
            if (parts.length != 4 || !parts[0].matches("-?[0-9]{1,7}")
                    || !(parts[1].equals("surface") || parts[1].equals("cave")))
                throw new IllegalArgumentException("Invalid RTP dimension");
            int id = Integer.parseInt(parts[0]);
            int low = number(parts[2], 1, 252), high = number(parts[3], 2, 253);
            if (low > high || worlds.put(id, new int[] {low, high, parts[1].equals("cave") ? 1 : 0}) != null)
                throw new IllegalArgumentException("Invalid RTP vertical range");
        }
    }
    private static int number(String text, int low, int high) {
        if (text == null || !text.matches("[0-9]{1,6}")) throw new IllegalArgumentException("Invalid RTP number");
        int value = Integer.parseInt(text);
        if (value < low || value > high) throw new IllegalArgumentException("RTP number out of range");
        return value;
    }
    private void tell(Object actor, String text) throws Exception { sendMessage.invoke(actor, plain.newInstance(text)); }

    @SubscribeEvent(priority = EventPriority.HIGH)
    public void onCommand(CommandEvent event) {
        Object actor = null;
        boolean ours = false;
        try {
            if (!"rtp".equals(name.invoke(command.invoke(event)))) return;
            ours = true;
            event.setCanceled(true); // Never fall back to FTB's spawn-dimension search.
            actor = sender.invoke(event);
            if (!player.isInstance(actor)) return;
            if (failed) { tell(actor, "Случайная телепортация временно недоступна."); return; }
            if (!Boolean.TRUE.equals(permission.invoke(null, actor, "command.ftbutilities.rtp"))) {
                tell(actor, "Команда недоступна."); return;
            }
            if (((String[]) parameters.invoke(event)).length != 0) { tell(actor, "Используйте /rtp"); return; }
            int dim = dimension.getInt(actor);
            if (!worlds.containsKey(dim)) { tell(actor, "RTP недоступен в этом мире."); return; }
            long now = System.currentTimeMillis();
            if (attempts.containsKey(actor) && attempts.get(actor) > now) {
                tell(actor, "Дождитесь завершения предыдущего RTP."); return;
            }
            Object data = dataGet.invoke(null, forgePlayer.invoke(null, actor));
            cooldown.invoke(data, actor, timer);
            long warmup = ((Number) seconds.invoke(ticks.invoke(rank.invoke(null, actor, "ftbutilities.rtp.warmup")))).longValue();
            attempts.put(actor, now + Math.max(retrySeconds * 1000L, warmup * 1000L + 1000L));
            final Object original = actor, level = world.get(actor);
            Function<Object, Object> search = current -> {
                try {
                    if (current != original || !Boolean.TRUE.equals(alive.invoke(current))
                            || online.invoke(forgePlayer.invoke(null, current)) != current
                            || dimension.getInt(current) != dim || world.get(current) != level) return null;
                    cooldown.invoke(dataGet.invoke(null, forgePlayer.invoke(null, current)), current, timer);
                    Object result = find(level, dim);
                    if (result == null) tell(current, "Безопасная точка RTP не найдена. Попробуйте позже.");
                    return result;
                } catch (InvocationTargetException error) {
                    if (!nativeError(current, error)) failure(error);
                    return null;
                } catch (Exception error) { failure(error); return null; }
            };
            teleport.invoke(timer, actor, search, null);
        } catch (InvocationTargetException error) {
            if (!nativeError(actor, error)) failure(error);
        } catch (Exception error) {
            if (ours) { event.setCanceled(true); failure(error); }
        }
    }
    private void failure(Exception error) {
        if (!failed) log.error("Omkality RTP adapter failed; RTP stays blocked", error);
        failed = true;
    }
    private boolean nativeError(Object actor, InvocationTargetException error) {
        Throwable reason = error.getCause();
        try {
            if (actor != null && nativeArgs.getDeclaringClass().isInstance(reason)) {
                sendMessage.invoke(actor, translation.newInstance(reason.getMessage(), nativeArgs.invoke(reason)));
                return true;
            }
        } catch (Exception ignored) { /* Caller logs and blocks a broken adapter. */ }
        return false;
    }

    private Object find(Object level, int dim) throws Exception {
        processQueue.invoke(claims); // Include claims queued earlier in the same tick.
        Object border = worldBorder.invoke(level);
        double limit = Math.min(maximum, ((Number) diameter.invoke(border)).doubleValue() * percent / 200.0 - 2);
        if (limit <= minimum) return null;
        double cx = ((Number) centerX.invoke(border)).doubleValue(), cz = ((Number) centerZ.invoke(border)).doubleValue();
        Set<Long> loaded = new HashSet<Long>();
        int[] vertical = worlds.get(dim);
        for (int trial = 0; trial < maxTrials; trial++) {
            double radius = Math.sqrt(minimum * (double) minimum + random.nextDouble() * (limit * limit - minimum * (double) minimum));
            double angle = random.nextDouble() * Math.PI * 2;
            int x = (int) Math.floor(cx + Math.cos(angle) * radius), z = (int) Math.floor(cz + Math.sin(angle) * radius);
            double actual = (x + 0.5 - cx) * (x + 0.5 - cx) + (z + 0.5 - cz) * (z + 0.5 - cz);
            if (actual < minimum * (double) minimum || actual > limit * limit) continue;
            if (!prepare(level, border, loaded, x, z, dim)) continue;
            for (int y = vertical[1]; y >= vertical[0]; y--) {
                Object floor = position.newInstance(x, y, z);
                if (Boolean.TRUE.equals(air.invoke(level, floor))) continue;
                Object state = blockState.invoke(level, floor);
                if (Boolean.TRUE.equals(full.invoke(state)) && !hazard(state)
                        && Boolean.TRUE.equals(air.invoke(level, position.newInstance(x, y + 1, z)))
                        && Boolean.TRUE.equals(air.invoke(level, position.newInstance(x, y + 2, z)))
                        && clearNeighbors(level, x, y, z))
                    return destination.invoke(null, x + 0.5, y + 1.01, z + 0.5, dim);
                if (vertical[2] == 0) break; // Surface worlds never tunnel under an unsafe surface.
            }
        }
        return null;
    }
    private boolean prepare(Object level, Object border, Set<Long> loaded, int x, int z, int dim) throws Exception {
        List<int[]> needed = new ArrayList<int[]>();
        for (int a = (x - 1) >> 4; a <= ((x + 1) >> 4); a++) {
            for (int b = (z - 1) >> 4; b <= ((z + 1) >> 4); b++) {
                if (claimed.invoke(claims, chunkPosition.newInstance(a, b, dim)) != null
                        || !Boolean.TRUE.equals(generated.invoke(level, a, b))) return false;
                long key = ((long) a << 32) ^ (b & 0xffffffffL);
                if (!loaded.contains(key)) needed.add(new int[] {a, b});
            }
        }
        if (loaded.size() + needed.size() > maxLoads) return false;
        for (int dx : new int[] {-1, 1}) for (int dz : new int[] {-1, 1})
            if (!Boolean.TRUE.equals(contains.invoke(border, position.newInstance(x + dx, 64, z + dz)))) return false;
        for (int[] p : needed) {
            chunk.invoke(level, p[0], p[1]);
            loaded.add(((long) p[0] << 32) ^ (p[1] & 0xffffffffL));
        }
        return true;
    }
    private boolean hazard(Object state) throws Exception {
        if (Boolean.TRUE.equals(liquid.invoke(material.invoke(state)))) return true;
        String id = registry.invoke(block.invoke(state)).toString();
        return id.equals("minecraft:fire") || id.equals("minecraft:cactus") || id.equals("minecraft:web")
            || id.equals("minecraft:portal") || id.equals("minecraft:end_portal");
    }
    private boolean clearNeighbors(Object level, int x, int y, int z) throws Exception {
        for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
            for (int dy = 0; dy <= 2; dy++)
                if (hazard(blockState.invoke(level, position.newInstance(x + dx, y + dy, z + dz)))) return false;
        return true;
    }
}
