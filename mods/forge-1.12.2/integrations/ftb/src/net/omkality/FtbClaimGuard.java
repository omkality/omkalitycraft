package net.omkality;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;
import com.feed_the_beast.ftblib.events.team.ForgeTeamConfigSavedEvent;
import com.feed_the_beast.ftblib.events.team.ForgeTeamPlayerLeftEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.entity.player.PlayerContainerEvent;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.Loader;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.common.gameevent.TickEvent;
import net.minecraftforge.fml.relauncher.Side;
import org.apache.logging.log4j.Logger;

/** DJ2 adapter: FTB owns every claim/permission decision. Only supported chest
 * inventories are inspected, not arbitrary mod machines or remote inventories.
 * Resolve MC reflection once because this private build has no mapped MC stubs.
 */
public final class FtbClaimGuard {
    static String state = "not initialized";
    private final Class<?> player, normalChest, ironChest, largeInventory, chestBlock;
    private final Class<?> vanillaContainer, ironContainer;
    private final Field world, openContainer, slots, slotInventory, tickPlayer;
    private final List<Field> halves = new ArrayList<Field>();
    private final Method eventPlayer, eventContainer, interactPos, getState, getBlock;
    private final Method getPos, getX, getY, getZ, blocked, close;
    private final Method ftbEventPlayer, nullablePlayer, playerList, players;
    private final Constructor<?> position;
    private final Object server;
    private final Logger log;
    private boolean failed;

    public static void install(Logger log) throws Exception {
        state = "initializing";
        if (!Loader.isModLoaded("ftbutilities")) { state = "ftb absent"; return; }
        FtbMuteGuard.requireVersion("ftbutilities", "5.4.1.131");
        FtbMuteGuard.requireVersion("ftblib", "5.4.7.2");
        if(Loader.isModLoaded("ironchest")) FtbMuteGuard.requireVersion("ironchest", "1.12.2-7.0.67.844");
        MinecraftForge.EVENT_BUS.register(new FtbClaimGuard(log));
        state = "enabled";
        log.info("Omkality FTB chest claim guard enabled (DJ2 adapter)");
    }

    private static Method method(Class<?> type, String srg, String mcp, Class<?>... args) throws Exception {
        try { return type.getMethod(srg, args); }
        catch (NoSuchMethodException error) { return type.getMethod(mcp, args); }
    }
    private static Field field(Class<?> type, String srg, String mcp) throws Exception {
        try { return type.getField(srg); }
        catch (NoSuchFieldException error) { return type.getField(mcp); }
    }

    private FtbClaimGuard(Logger logger) throws Exception {
        log = logger;
        player = Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        Class<?> base = Class.forName("net.minecraft.entity.player.EntityPlayer");
        Class<?> pos = Class.forName("net.minecraft.util.math.BlockPos");
        Class<?> blockState = Class.forName("net.minecraft.block.state.IBlockState");
        Class<?> inventory = Class.forName("net.minecraft.inventory.IInventory");
        normalChest = Class.forName("net.minecraft.tileentity.TileEntityChest");
        ironChest = Loader.isModLoaded("ironchest") ? Class.forName("cpw.mods.ironchest.common.tileentity.chest.TileEntityIronChest") : null;
        largeInventory = Class.forName("net.minecraft.inventory.InventoryLargeChest");
        chestBlock = Class.forName("net.minecraft.block.BlockChest");
        vanillaContainer = Class.forName("net.minecraft.inventory.ContainerChest");
        ironContainer = ironChest==null ? null : Class.forName("cpw.mods.ironchest.common.gui.chest.ContainerIronChest");
        world = field(Class.forName("net.minecraft.entity.Entity"), "field_70170_p", "world");
        openContainer = field(base, "field_71070_bA", "openContainer");
        slots = field(Class.forName("net.minecraft.inventory.Container"), "field_75151_b", "inventorySlots");
        slotInventory = field(Class.forName("net.minecraft.inventory.Slot"), "field_75224_c", "inventory");
        tickPlayer = TickEvent.PlayerTickEvent.class.getField("player");
        eventPlayer = Class.forName("net.minecraftforge.event.entity.player.PlayerEvent").getMethod("getEntityPlayer");
        eventContainer = PlayerContainerEvent.class.getMethod("getContainer");
        interactPos = PlayerInteractEvent.class.getMethod("getPos");
        getState = method(world.getType(), "func_180495_p", "getBlockState", pos);
        getBlock = method(blockState, "func_177230_c", "getBlock");
        getPos = method(Class.forName("net.minecraft.tileentity.TileEntity"), "func_174877_v", "getPos");
        getX = method(pos, "func_177958_n", "getX");
        getY = method(pos, "func_177956_o", "getY");
        getZ = method(pos, "func_177952_p", "getZ");
        position = pos.getConstructor(int.class, int.class, int.class);
        blocked = Class.forName("com.feed_the_beast.ftbutilities.data.ClaimedChunks")
            .getMethod("blockBlockInteractions", base, pos, blockState);
        close = method(player, "func_71053_j", "closeScreen");
        for (Field f : largeInventory.getDeclaredFields()) {
            if (inventory.isAssignableFrom(f.getType()) && !Modifier.isStatic(f.getModifiers())) {
                f.setAccessible(true); halves.add(f);
            }
        }
        if (halves.size() != 2) throw new IllegalStateException("Unknown vanilla compound chest layout");
        ftbEventPlayer = ForgeTeamPlayerLeftEvent.class.getMethod("getPlayer");
        nullablePlayer = ftbEventPlayer.getReturnType().getMethod("getNullablePlayer");
        server = FMLCommonHandler.class.getMethod("getMinecraftServerInstance").invoke(FMLCommonHandler.instance());
        playerList = method(server.getClass(), "func_184103_al", "getPlayerList");
        players = method(playerList.getReturnType(), "func_181057_v", "getPlayers");
    }

    private boolean selected(Object container) {
        return vanillaContainer.isInstance(container) || (ironContainer!=null && ironContainer.isInstance(container));
    }
    private boolean denied(Object actor, Object inventory, int depth) throws Exception {
        if (normalChest.isInstance(inventory) || (ironChest!=null && ironChest.isInstance(inventory))) {
            return Boolean.TRUE.equals(blocked.invoke(null, actor, getPos.invoke(inventory), null));
        }
        if (largeInventory.isInstance(inventory)) {
            if (depth > 2) throw new IllegalStateException("Unexpected nested chest inventory");
            for (Field half : halves) if (denied(actor, half.get(inventory), depth + 1)) return true;
        }
        return false; // Personal/virtual inventories are outside this adapter.
    }
    private void validate(Object actor, Object container) throws Exception {
        if (!player.isInstance(actor) || !selected(container)) return;
        List<?> contents = (List<?>) slots.get(container);
        if (contents.isEmpty()) throw new IllegalStateException("Supported chest has no inventory slots");
        if (failed || denied(actor, slotInventory.get(contents.get(0)), 0)) close.invoke(actor);
    }
    private void failure(Object actor, Exception error) {
        if (!failed) log.error("Omkality chest claim adapter failed; supported chest windows will close", error);
        failed = true;
        try { if (player.isInstance(actor) && selected(openContainer.get(actor))) close.invoke(actor); }
        catch (Exception ignored) { /* Primary error logged once; no inventory mutation here. */ }
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public void onRightClick(PlayerInteractEvent.RightClickBlock event) {
        Object actor = null;
        try {
            actor = eventPlayer.invoke(event);
            if (!player.isInstance(actor)) return;
            Object level = world.get(actor), pos = interactPos.invoke(event);
            Object block = getBlock.invoke(getState.invoke(level, pos));
            if (!chestBlock.isInstance(block)) return;
            if (failed) { event.setCanceled(true); return; }
            int x = ((Number) getX.invoke(pos)).intValue();
            int y = ((Number) getY.invoke(pos)).intValue();
            int z = ((Number) getZ.invoke(pos)).intValue();
            for (int[] offset : new int[][] {{-1,0}, {1,0}, {0,-1}, {0,1}}) {
                Object adjacent = position.newInstance(x + offset[0], y, z + offset[1]);
                if (getBlock.invoke(getState.invoke(level, adjacent)) == block
                        && Boolean.TRUE.equals(blocked.invoke(null, actor, adjacent, null))) {
                    event.setCanceled(true); return;
                }
            }
        } catch (Exception error) { failure(actor, error); event.setCanceled(true); }
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public void onOpen(PlayerContainerEvent.Open event) {
        Object actor = null;
        try { actor = eventPlayer.invoke(event); validate(actor, eventContainer.invoke(event)); }
        catch (Exception error) { failure(actor, error); }
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public void onTeamLeft(ForgeTeamPlayerLeftEvent event) {
        Object actor = null;
        try {
            actor = nullablePlayer.invoke(ftbEventPlayer.invoke(event));
            // FTBLib posts this BEFORE removing membership. Close unconditionally,
            // not by testing permissions which are still valid inside this callback.
            if (player.isInstance(actor) && selected(openContainer.get(actor))) close.invoke(actor);
        } catch (Exception error) { failure(actor, error); }
    }

    @SubscribeEvent(priority = EventPriority.LOWEST)
    public void onTeamConfig(ForgeTeamConfigSavedEvent event) {
        try {
            for (Object actor : (List<?>) players.invoke(playerList.invoke(server))) {
                try { validate(actor, openContainer.get(actor)); }
                catch (Exception error) { failure(actor, error); }
            }
        } catch (Exception error) { failure(null, error); }
    }

    @SubscribeEvent
    public void onTick(TickEvent.PlayerTickEvent event) {
        if (event.side != Side.SERVER || event.phase != TickEvent.Phase.END) return;
        Object actor = null;
        try { actor = tickPlayer.get(event); validate(actor, openContainer.get(actor)); }
        catch (Exception error) { failure(actor, error); }
    }
}
