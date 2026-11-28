package net.omkality.client.crates;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Map;
import net.minecraft.client.Minecraft;
import net.minecraft.client.network.NetHandlerPlayClient;
import net.minecraft.network.NetworkManager;
import net.minecraftforge.fml.common.versioning.DefaultArtifactVersion;
import net.minecraftforge.fml.common.versioning.VersionParser;
import net.minecraftforge.fml.common.versioning.VersionRange;
import org.apache.logging.log4j.LogManager;

/** Use the server's full-crate sort when the active connection advertises the feature. */
public final class ServerCrateSort {
    private static final String AA = "de.ellpeck.actuallyadditions.mod.";
    private static final VersionRange SERVER = VersionParser.parseRange("[0.1.15,0.2.0)");
    private static boolean bindingsUnavailable;
    private static long nextRequest = System.nanoTime();

    /** Return true when the standard client sort has been replaced by the crate request. */
    public static boolean request() {
        Minecraft game = Minecraft.func_71410_x();
        Object screen = game.field_71462_r;
        NetHandlerPlayClient connection = game.func_147114_u();
        if (bindingsUnavailable || screen == null || connection == null
            || !(AA + "inventory.gui.GuiGiantChest").equals(screen.getClass().getName())) {
            return false;
        }
        try {
            Bindings fields = Bindings.INSTANCE;
            Object tile = fields.tile.get(screen);
            String type = tile.getClass().getName();
            if (!type.equals(AA + "tile.TileEntityGiantChest")
                && !type.equals(AA + "tile.TileEntityGiantChestMedium")
                && !type.equals(AA + "tile.TileEntityGiantChestLarge")) {
                return false;
            }
            Object fml = fields.dispatcher.invoke(null, connection.func_147298_b());
            Map<?, ?> mods = fml == null ? null : (Map<?, ?>) fields.mods.invoke(fml);
            Object version = mods == null ? null : mods.get("omkalitydj2fix");
            if (!(version instanceof String) || !SERVER.containsVersion(new DefaultArtifactVersion((String) version))) {
                return false;
            }
            long now = System.nanoTime();
            // The request uses the normal command path, which has a chat-spam
            // budget. Coalesce repeated presses so they cannot consume it.
            if (now - nextRequest >= 0) {
                nextRequest = now + 1_100_000_000L;
                game.field_71439_g.func_71165_d("/omk_sort_crate " + game.field_71439_g.field_71070_bA.field_75152_c);
            }
            return true;
        } catch (ReflectiveOperationException | LinkageError error) {
            bindingsUnavailable = true;
            LogManager.getLogger("OmkalityClient").warn("Multiplayer crate sort is unavailable", error);
            return false;
        }
    }

    private static final class Bindings {
        static final Bindings INSTANCE = new Bindings();
        final Field tile;
        final Method dispatcher;
        final Method mods;

        Bindings() {
            try {
                tile = Class.forName(AA + "inventory.gui.GuiGiantChest").getDeclaredField("chest");
                tile.setAccessible(true);
                Class<?> handshake = Class.forName("net.minecraftforge.fml.common.network.handshake.NetworkDispatcher");
                dispatcher = handshake.getMethod("get", NetworkManager.class);
                mods = handshake.getMethod("getModList");
            } catch (ReflectiveOperationException error) {
                throw new ExceptionInInitializerError(error);
            }
        }
    }

    private ServerCrateSort() {}
}
