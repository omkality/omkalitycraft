package net.omkality.client.crates;

import java.lang.ref.WeakReference;
import java.lang.reflect.Field;
import net.minecraft.client.Minecraft;
import net.minecraft.client.network.NetHandlerPlayClient;
import net.minecraft.network.NetworkManager;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.common.network.FMLNetworkEvent;
import net.minecraftforge.fml.relauncher.Side;
import org.apache.logging.log4j.LogManager;

/** Use the server's full-crate sort when the active connection advertises the feature. */
@Mod.EventBusSubscriber(modid = "omkalityclient", value = Side.CLIENT)
public final class ServerCrateSort {
    private static final String AA = "de.ellpeck.actuallyadditions.mod.";
    private static final String CHANNEL = "omk:crate_sort";
    private static volatile WeakReference<NetworkManager> advertised = new WeakReference<>(null);
    private static boolean bindingsUnavailable;
    private static long nextRequest = System.nanoTime();

    /** Bind Forge's server announcement to this connection only. */
    @SubscribeEvent
    public static void register(FMLNetworkEvent.CustomPacketRegistrationEvent<?> event) {
        if (event.getSide() != Side.CLIENT || !event.getRegistrations().contains(CHANNEL)) {
            return;
        }
        NetworkManager manager = event.getManager();
        if ("REGISTER".equals(event.getOperation())) {
            advertised = new WeakReference<>(manager);
        } else {
            WeakReference<NetworkManager> current = advertised;
            if (current.get() == manager) {
                current.clear();
            }
        }
    }

    /** Return true when the standard client sort has been replaced by the crate request. */
    public static boolean request() {
        Minecraft game = Minecraft.func_71410_x();
        Object screen = game.field_71462_r;
        NetHandlerPlayClient connection = game.func_147114_u();
        if (bindingsUnavailable || screen == null || connection == null
            || advertised.get() != connection.func_147298_b()
            || !(AA + "inventory.gui.GuiGiantChest").equals(screen.getClass().getName())) {
            return false;
        }
        try {
            Object tile = Bindings.TILE.get(screen);
            String type = tile.getClass().getName();
            if (!type.equals(AA + "tile.TileEntityGiantChest")
                && !type.equals(AA + "tile.TileEntityGiantChestMedium")
                && !type.equals(AA + "tile.TileEntityGiantChestLarge")) {
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
        static final Field TILE = tileField();
        private static Field tileField() {
            try {
                Field tile = Class.forName(AA + "inventory.gui.GuiGiantChest").getDeclaredField("chest");
                tile.setAccessible(true);
                return tile;
            } catch (ReflectiveOperationException error) {
                throw new ExceptionInInitializerError(error);
            }
        }
    }

    private ServerCrateSort() {}
}
