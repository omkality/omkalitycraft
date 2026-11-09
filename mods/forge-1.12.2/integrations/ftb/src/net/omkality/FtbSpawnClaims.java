package net.omkality;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import com.feed_the_beast.ftblib.lib.data.ForgePlayer;
import com.feed_the_beast.ftblib.lib.data.ForgeTeam;
import com.feed_the_beast.ftblib.lib.data.TeamType;
import com.feed_the_beast.ftblib.lib.data.Universe;
import com.feed_the_beast.ftblib.lib.math.ChunkDimPos;
import com.feed_the_beast.ftblib.events.team.ForgeTeamCreatedEvent;
import org.apache.logging.log4j.Logger;

/** Explicit startup bootstrap of server-owned FTB claims. No player OP, world
 * generation, chunk loading, custom block protection or separate claim database.
 * Missing policy preserves compatibility; a present invalid/conflicting policy
 * aborts startup before accepting players. Never removes claims on radius shrink.
 */
public final class FtbSpawnClaims {
    private static final String TEAM = "omk_spawn";
    static String state = "not configured";

    public static void install(Path config, Logger log) throws Exception {
        Path file = config.resolve("omkalitycore-spawn.properties");
        if (!Files.exists(file, LinkOption.NOFOLLOW_LINKS)) return;
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || Files.size(file) > 4096)
            throw new IllegalArgumentException("Invalid spawn policy file");
        List<ChunkDimPos> positions = parse(Files.readAllLines(file, StandardCharsets.UTF_8));
        FtbMuteGuard.requireVersion("ftbutilities", "5.4.1.131");
        FtbMuteGuard.requireVersion("ftblib", "5.4.7.2");
        Class<?> claimsType = Class.forName("com.feed_the_beast.ftbutilities.data.ClaimedChunks");
        if (!Boolean.TRUE.equals(claimsType.getMethod("isActive").invoke(null)))
            throw new IllegalStateException("Spawn protection requires active FTB claims");
        Object claims = claimsType.getField("instance").get(null);
        Method queue = claimsType.getMethod("processQueue");
        Method owner = claimsType.getMethod("getChunkTeam", ChunkDimPos.class);
        Method claim = claimsType.getMethod("claimChunk", ForgePlayer.class, ChunkDimPos.class, boolean.class);
        Object worldConfig = Class.forName("com.feed_the_beast.ftbutilities.FTBUtilitiesConfig")
            .getField("world").get(null);
        Method blockedDimension = worldConfig.getClass().getMethod("blockDimension", int.class);
        Method registered = Class.forName("net.minecraftforge.common.DimensionManager")
            .getMethod("isDimensionRegistered", int.class);
        Universe universe = Universe.get();
        ForgeTeam team = universe.getTeam(TEAM);
        if (team.isValid()) validateTeam(team);
        queue.invoke(claims); // Loaded FTB claims are queued until the first tick.
        for (ChunkDimPos pos : positions) {
            if (!Boolean.TRUE.equals(registered.invoke(null, pos.dim))
                    || Boolean.TRUE.equals(blockedDimension.invoke(worldConfig, pos.dim)))
                throw new IllegalStateException("Spawn dimension unavailable or blocked");
            Object previous = owner.invoke(claims, pos);
            if (previous != null && (!team.isValid() || previous != team))
                throw new IllegalStateException("Spawn plan overlaps a foreign FTB claim");
        }
        // All conflicts/permissions checked before the first team/claim mutation.
        int previousCount = 0;
        for (ChunkDimPos pos : positions) if (owner.invoke(claims, pos) != null) previousCount++;
        log.info("Omkality spawn plan: {} chunks, {} existing, server team {}", positions.size(), previousCount, TEAM);
        if (!team.isValid()) {
            universe.clearCache();
            team = new ForgeTeam(universe, universe.generateTeamUID((short) 0), TEAM, TeamType.SERVER);
            team.setTitle("OmkalityCraft spawn");
            universe.addTeam(team);
            new ForgeTeamCreatedEvent(team).post();
            team.markDirty();
            validateTeam(team);
        }
        ForgePlayer virtual = new ForgePlayer(universe,
            UUID.nameUUIDFromBytes("OmkalitySpawnBootstrap".getBytes(StandardCharsets.UTF_8)), "OmkalitySpawnBootstrap");
        virtual.team = team; // Same FTB-supported mechanism as /chunks claim_as.
        for (ChunkDimPos pos : positions) {
            if (owner.invoke(claims, pos) == team) continue;
            Object result = claim.invoke(claims, virtual, pos, false);
            if (!"SUCCESS".equals(result.toString()))
                throw new IllegalStateException("FTB could not reserve a planned spawn chunk");
        }
        queue.invoke(claims);
        for (ChunkDimPos pos : positions) if (owner.invoke(claims, pos) != team)
            throw new IllegalStateException("Spawn claim verification failed");
        state = "enabled";
        log.info("Omkality spawn claims verified: {} (no force loading)", positions.size());
    }

    private static void validateTeam(ForgeTeam team) throws Exception {
        // Fail rather than silently repair an operator's altered permission data.
        if (!TEAM.equals(team.getId()) || team.type != TeamType.SERVER || team.owner != null
                || !team.players.isEmpty() || team.isFreeToJoin())
            throw new IllegalStateException("Spawn team has unexpected members or ownership");
        Class<?> dataType = Class.forName("com.feed_the_beast.ftbutilities.data.FTBUtilitiesTeamData");
        Object data = dataType.getMethod("get", ForgeTeam.class).invoke(null, team);
        if (Boolean.TRUE.equals(dataType.getMethod("hasExplosions").invoke(data)))
            throw new IllegalStateException("Spawn team permits explosions");
        for (String getter : new String[] {"getEditBlocksStatus", "getInteractWithBlocksStatus", "getUseItemsStatus"}) {
            String status = ((Enum<?>) dataType.getMethod(getter).invoke(data)).name();
            if (!"ALLY".equals(status) && !"MEMBER".equals(status) && !"OWNER".equals(status))
                throw new IllegalStateException("Spawn team has permissive block/item rights");
        }
    }

    private static List<ChunkDimPos> parse(List<String> lines) {
        String zones = null;
        boolean version = false;
        for (String line : lines) {
            if (line.isEmpty() || line.startsWith("#")) continue;
            if (line.equals("version=1") && !version) { version = true; continue; }
            if (line.startsWith("zones=") && zones == null) { zones = line.substring(6); continue; }
            throw new IllegalArgumentException("Unknown or duplicate spawn policy field");
        }
        if (!version || zones == null) throw new IllegalArgumentException("Incomplete spawn policy");
        List<ChunkDimPos> result = new ArrayList<ChunkDimPos>();
        Set<Integer> dimensions = new HashSet<Integer>();
        String[] entries = zones.split(";", -1);
        if (entries.length > 8) throw new IllegalArgumentException("Too many spawn dimensions");
        for (String entry : entries) {
            if (!entry.matches("-?[0-9]{1,7}:-?[0-9]{1,7}:-?[0-9]{1,7}:-?[0-9]{1,7}:-?[0-9]{1,7}"))
                throw new IllegalArgumentException("Invalid spawn zone");
            String[] parts = entry.split(":");
            int dim = Integer.parseInt(parts[0]);
            int x0 = Integer.parseInt(parts[1]), x1 = Integer.parseInt(parts[2]);
            int z0 = Integer.parseInt(parts[3]), z1 = Integer.parseInt(parts[4]);
            if (!dimensions.add(dim) || x0 > x1 || z0 > z1)
                throw new IllegalArgumentException("Duplicate or inverted spawn zone");
            long count = (long) ((x1 >> 4) - (x0 >> 4) + 1) * ((z1 >> 4) - (z0 >> 4) + 1);
            if (count + result.size() > 10000) throw new IllegalArgumentException("Spawn chunk budget exceeded");
            for (int x = x0 >> 4; x <= (x1 >> 4); x++)
                for (int z = z0 >> 4; z <= (z1 >> 4); z++) result.add(new ChunkDimPos(x, z, dim));
        }
        return result;
    }
}
