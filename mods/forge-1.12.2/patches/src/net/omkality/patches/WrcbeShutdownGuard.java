package net.omkality.patches;

import java.lang.reflect.Method;
import net.minecraftforge.fml.common.gameevent.TickEvent;
import net.minecraftforge.fml.relauncher.Side;

/** Version-specific lifecycle guard; never hides faults during a running server. */
public final class WrcbeShutdownGuard {
    private static Method manager, getServer, running;
    private static Object common;
    private static org.apache.logging.log4j.Logger logger;
    private static boolean reported;

    public static void install(org.apache.logging.log4j.Logger log) throws Exception {
        VerifiedArtifacts.require("wrcbe");
        VerifiedArtifacts.require("mixinbooter");
        manager = Class.forName("codechicken.wirelessredstone.manager.RedstoneEtherAddons").getMethod("server");
        Class<?> handler = Class.forName("net.minecraftforge.fml.common.FMLCommonHandler");
        common = handler.getMethod("instance").invoke(null);
        getServer = handler.getMethod("getMinecraftServerInstance");
        Class<?> server = Class.forName("net.minecraft.server.MinecraftServer");
        try { running = server.getMethod("func_71278_l"); }
        catch (NoSuchMethodException error) { running = server.getMethod("isServerRunning"); }
        logger = log;
        reported = false;
        logger.info("Omkality WR-CBE shutdown guard initialized");
    }

    public static boolean shouldSkip(TickEvent.WorldTickEvent event) {
        if (event.side != Side.SERVER || event.phase != TickEvent.Phase.START) return false;
        if (manager == null) throw new IllegalStateException("WR-CBE shutdown guard was not initialized");
        try {
            if (manager.invoke(null) != null) return false;
            Object server = getServer.invoke(common);
            if (server == null || ((Boolean) running.invoke(server)).booleanValue()) return false;
            if (!reported) {
                reported = true;
                logger.info("Omkality skipped WR-CBE START tick after manager disposal during shutdown");
            }
            return true;
        } catch (ReflectiveOperationException error) {
            throw new IllegalStateException("WR-CBE shutdown guard could not inspect lifecycle", error);
        }
    }
}
