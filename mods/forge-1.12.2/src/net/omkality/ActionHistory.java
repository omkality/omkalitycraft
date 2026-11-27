package net.omkality;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.common.util.BlockSnapshot;
import net.minecraftforge.event.entity.item.ItemEvent;
import net.minecraftforge.event.entity.item.ItemTossEvent;
import net.minecraftforge.event.world.BlockEvent;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.eventhandler.Event;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.common.gameevent.PlayerEvent;
import net.minecraftforge.fml.common.gameevent.TickEvent;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Record selected effects from the authoritative server thread, without game content or disk I/O. */
public final class ActionHistory {
    private static final int PER_TICK = 128;
    private static final int MIB = 1024 * 1024;
    private static volatile ActionHistory active;

    private final Object server, players;
    private final Thread serverThread = Thread.currentThread();
    private final Class<?> realPlayer, fakePlayer;
    private final Field remote, provider, entityWorld, networkPlayer;
    private final Method dimension, byId, gameProfile, profileId, profileName;
    private final Method position, uniqueId, x, y, z, loaded, stateAt, block, blockId;
    private final Method packetPos, stackItem, itemId, count, entityStack;
    private final Method placeActor, breakActor, blockPos, blockWorld, breakState, snapshotPos, before, after;
    private final Method tossPlayer, tossEntity, pickupEntity, pickedStack;
    private final Field eventPlayer, craftedStack;
    private final List<Observation> pending = new ArrayList<>(PER_TICK);
    private final PrivateJournal journal;
    private long group;
    private int budget = PER_TICK;

    static void install(Logger log, ServerProfile profile) {
        Map<String, String> env = System.getenv();
        String enabled = env.getOrDefault("OMK_ACTION_HISTORY_ENABLED", "false");
        if ("false".equals(enabled)) {
            CoreServices.report("core.action_history", "disabled");
            return;
        }
        ActionHistory history = null;
        try {
            if (!"true".equals(enabled) || !"enabled".equals(CoreServices.statuses().get("server.action_dispatch")))
                throw new IllegalArgumentException("Unsupported action history adapter");
            Path path = Paths.get(env.getOrDefault("OMK_ACTION_HISTORY_DIRECTORY", "")).normalize();
            String id = env.getOrDefault("OMK_ACTION_HISTORY_SERVER", "");
            if (!path.isAbsolute() || path.getParent() == null || path.startsWith(Paths.get(".").toRealPath())
                    || !id.matches("[a-z0-9][a-z0-9_-]{0,47}"))
                throw new IllegalArgumentException("Dedicated action history directory and server ID required");
            int days = setting(env, "DAYS", 30, 90);
            int size = setting(env, "MIB", 128, 256);
            int reserve = setting(env, "RESERVE_MIB", 512, 8192);
            history = new ActionHistory(log, id, profile.id, path, days, size, reserve);
            MinecraftForge.EVENT_BUS.register(history);
            active = history;
            CoreServices.report("core.action_history", "enabled");
        } catch (Exception error) {
            if (history != null) history.journal.close();
            log.warn("Omkality action history unavailable ({})", error.getClass().getSimpleName());
            CoreServices.report("core.action_history", "unavailable");
        }
    }

    static void stop() {
        ActionHistory history = active;
        active = null;
        if (history != null) {
            MinecraftForge.EVENT_BUS.unregister(history);
            history.flush();
            history.journal.close();
        }
    }

    private static int setting(Map<String, String> env, String name, int fallback, int maximum) {
        String raw = env.getOrDefault("OMK_ACTION_HISTORY_" + name, Integer.toString(fallback));
        if (!raw.matches("[1-9][0-9]{0,3}") || Integer.parseInt(raw) > maximum)
            throw new IllegalArgumentException("Invalid action history limit");
        return Integer.parseInt(raw);
    }

    private ActionHistory(Logger log, String id, String profile, Path path, int days, int size, int reserve)
            throws Exception {
        server = FMLCommonHandler.class.getMethod("getMinecraftServerInstance").invoke(FMLCommonHandler.instance());
        players = server.getClass().getMethod("func_184103_al").invoke(server);
        byId = players.getClass().getMethod("func_177451_a", UUID.class);
        realPlayer = Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        fakePlayer = Class.forName("net.minecraftforge.common.util.FakePlayer");
        gameProfile = realPlayer.getMethod("func_146103_bH");
        profileId = gameProfile.getReturnType().getMethod("getId");
        profileName = gameProfile.getReturnType().getMethod("getName");
        Class<?> entity = Class.forName("net.minecraft.entity.Entity");
        entityWorld = entity.getField("field_70170_p");
        position = entity.getMethod("func_180425_c");
        uniqueId = entity.getMethod("func_110124_au");
        Class<?> pos = position.getReturnType();
        x = pos.getMethod("func_177958_n");
        y = pos.getMethod("func_177956_o");
        z = pos.getMethod("func_177952_p");
        Class<?> world = entityWorld.getType();
        remote = world.getField("field_72995_K");
        provider = world.getField("field_73011_w");
        dimension = provider.getType().getMethod("getDimension");
        loaded = world.getMethod("func_175667_e", pos);
        stateAt = world.getMethod("func_180495_p", pos);
        block = stateAt.getReturnType().getMethod("func_177230_c");
        blockId = block.getReturnType().getMethod("getRegistryName");
        Class<?> stack = Class.forName("net.minecraft.item.ItemStack");
        stackItem = stack.getMethod("func_77973_b");
        itemId = stackItem.getReturnType().getMethod("getRegistryName");
        count = stack.getMethod("func_190916_E");
        entityStack = Class.forName("net.minecraft.entity.item.EntityItem").getMethod("func_92059_d");
        networkPlayer = Class.forName("net.minecraft.network.NetHandlerPlayServer").getField("field_147369_b");
        packetPos = Class.forName("net.minecraft.network.play.client.CPacketUpdateSign").getMethod("func_179722_a");
        placeActor = BlockEvent.EntityPlaceEvent.class.getMethod("getEntity");
        breakActor = BlockEvent.BreakEvent.class.getMethod("getPlayer");
        blockWorld = BlockEvent.class.getMethod("getWorld");
        blockPos = BlockEvent.class.getMethod("getPos");
        breakState = BlockEvent.class.getMethod("getState");
        snapshotPos = BlockSnapshot.class.getMethod("getPos");
        before = BlockSnapshot.class.getMethod("getReplacedBlock");
        after = BlockSnapshot.class.getMethod("getCurrentBlock");
        tossPlayer = ItemTossEvent.class.getMethod("getPlayer");
        tossEntity = ItemEvent.class.getMethod("getEntityItem");
        eventPlayer = PlayerEvent.class.getField("player");
        pickupEntity = PlayerEvent.ItemPickupEvent.class.getMethod("getOriginalEntity");
        pickedStack = PlayerEvent.ItemPickupEvent.class.getMethod("getStack");
        craftedStack = PlayerEvent.ItemCraftedEvent.class.getField("crafting");
        journal = new PrivateJournal(PrivateJournal.Stream.ACTION, path, id, profile, days, size * MIB,
            (long) reserve * MIB, reason -> log.warn("Omkality action history unavailable ({})", reason));
    }

    private boolean eligible(Object world) throws IllegalAccessException {
        return Thread.currentThread() == serverThread && !remote.getBoolean(world);
    }

    private boolean reserve() {
        if (budget > 0) {
            budget--;
            return true;
        }
        journal.omitted();
        return false;
    }

    private Map<String, Object> actor(Object entity) throws ReflectiveOperationException {
        if (fakePlayer.isInstance(entity)) return Collections.singletonMap("kind", "fake_player");
        if (realPlayer.isInstance(entity)) {
            Object profile = gameProfile.invoke(entity);
            UUID uuid = (UUID) profileId.invoke(profile);
            if (uuid != null && byId.invoke(players, uuid) == entity) {
                String name = (String) profileName.invoke(profile);
                Map<String, Object> account = new LinkedHashMap<>();
                account.put("kind", "player");
                account.put("uuid", uuid.toString());
                account.put("name", name.substring(0, Math.min(32, name.length())));
                return account;
            }
        }
        return Collections.singletonMap("kind", "unassigned");
    }

    private Map<String, Object> row(String action, Object world, Object pos, Map<String, Object> actor)
            throws ReflectiveOperationException {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("action", action);
        row.put("actor", actor);
        row.put("dimension", dimension.invoke(provider.get(world)));
        row.put("x", x.invoke(pos));
        row.put("y", y.invoke(pos));
        row.put("z", z.invoke(pos));
        return row;
    }

    private String blockKey(Object state) throws ReflectiveOperationException {
        return String.valueOf(blockId.invoke(block.invoke(state)));
    }

    @SubscribeEvent(priority = EventPriority.LOWEST, receiveCanceled = true)
    public void place(BlockEvent.EntityPlaceEvent event) {
        try {
            Object world = blockWorld.invoke(event);
            if (!eligible(world)) return;
            List<BlockSnapshot> snapshots;
            if (event instanceof BlockEvent.MultiPlaceEvent) {
                snapshots = ((BlockEvent.MultiPlaceEvent) event).getReplacedBlockSnapshots();
            } else if (event instanceof BlockEvent.EntityMultiPlaceEvent) {
                snapshots = ((BlockEvent.EntityMultiPlaceEvent) event).getReplacedBlockSnapshots();
            } else {
                snapshots = Collections.singletonList(event.getBlockSnapshot());
            }
            long at = System.currentTimeMillis();
            boolean multi = snapshots.size() > 1;
            Map<String, Object> owner = actor(placeActor.invoke(event));
            long placement = ++group;
            for (int index = 0; index < snapshots.size(); index++) {
                if (!reserve()) {
                    journal.omitted(snapshots.size() - index - 1);
                    break;
                }
                BlockSnapshot snapshot = snapshots.get(index);
                Object pos = snapshotPos.invoke(snapshot);
                if (!(Boolean) loaded.invoke(world, pos)) {
                    journal.omitted();
                    continue;
                }
                Object previous = before.invoke(snapshot), next = after.invoke(snapshot);
                Map<String, Object> row = row(multi ? "multi_place" : "place", world, pos, owner);
                row.put("registry", blockKey(next));
                row.put("previous", blockKey(previous));
                row.put("placement", placement);
                pending.add(new Observation(event, world, pos, previous, next, row, at));
            }
        } catch (ReflectiveOperationException | RuntimeException error) { journal.omitted(); }
    }

    @SubscribeEvent(priority = EventPriority.LOWEST, receiveCanceled = true)
    public void breakBlock(BlockEvent.BreakEvent event) {
        try {
            Object world = blockWorld.invoke(event);
            if (!eligible(world) || !reserve()) return;
            Object pos = blockPos.invoke(event), previous = breakState.invoke(event);
            Map<String, Object> row = row("break", world, pos, actor(breakActor.invoke(event)));
            row.put("registry", blockKey(previous));
            pending.add(new Observation(event, world, pos, previous, null, row, System.currentTimeMillis()));
        } catch (ReflectiveOperationException | RuntimeException error) { journal.omitted(); }
    }

    @SubscribeEvent(priority = EventPriority.LOWEST)
    public void toss(ItemTossEvent event) {
        try {
            Object entity = tossEntity.invoke(event);
            item("drop", tossPlayer.invoke(event), entity, entityStack.invoke(entity), event);
        } catch (ReflectiveOperationException | RuntimeException error) { journal.omitted(); }
    }

    @SubscribeEvent
    public void pickup(PlayerEvent.ItemPickupEvent event) {
        try {
            item("pickup", eventPlayer.get(event), pickupEntity.invoke(event), pickedStack.invoke(event), null);
        } catch (ReflectiveOperationException | RuntimeException error) { journal.omitted(); }
    }

    @SubscribeEvent
    public void craft(PlayerEvent.ItemCraftedEvent event) {
        try {
            item("craft", eventPlayer.get(event), null, craftedStack.get(event), null);
        } catch (ReflectiveOperationException | RuntimeException error) { journal.omitted(); }
    }

    private void item(String action, Object player, Object item, Object stack, Event cancellable)
            throws ReflectiveOperationException {
        Object where = item == null ? player : item;
        Object world = entityWorld.get(where);
        if (!eligible(world) || !reserve()) return;
        int quantity = (Integer) count.invoke(stack);
        if (quantity <= 0) return;
        Map<String, Object> row = row(action, world, position.invoke(where), actor(player));
        row.put("registry", String.valueOf(itemId.invoke(stackItem.invoke(stack))));
        row.put("count", quantity);
        if (item != null) row.put("item_entity", uniqueId.invoke(item).toString());
        pending.add(new Observation(cancellable, null, null, null, null, row, System.currentTimeMillis()));
    }

    /** An accepted interaction escaped all native and Forge checks and activated its target. */
    public static void activation(Object player, Object world, Object pos, Object state) {
        ActionHistory history = active;
        if (history == null) return;
        try {
            if (history.eligible(world) && history.reserve())
                history.effect("activate", world, pos, history.actor(player), history.blockKey(state));
        } catch (ReflectiveOperationException | RuntimeException error) { history.journal.omitted(); }
    }

    /** Piston event accepted by the world. It carries no authenticated player. */
    public static void piston(Object world, Object pos, Object state) {
        ActionHistory history = active;
        if (history == null) return;
        try {
            if (history.eligible(world) && history.reserve())
                history.effect("piston", world, pos, Collections.singletonMap("kind", "automation"), history.blockKey(state));
        } catch (ReflectiveOperationException | RuntimeException error) { history.journal.omitted(); }
    }

    /** Observe committed vanilla edits. The adapter never receives book pages or sign lines. */
    public static void edit(Object handler, Object signPacket, String book) {
        ActionHistory history = active;
        if (history == null) return;
        try {
            Object player = history.networkPlayer.get(handler);
            Object world = history.entityWorld.get(player);
            if (!history.eligible(world) || !history.reserve()) return;
            Map<String, Object> actor = history.actor(player);
            if (signPacket == null) {
                history.effect(book, world, history.position.invoke(player), actor,
                    "book_sign".equals(book) ? "minecraft:written_book" : "minecraft:writable_book");
            } else {
                Object pos = history.packetPos.invoke(signPacket);
                history.effect("sign_edit", world, pos, actor, history.blockKey(history.stateAt.invoke(world, pos)));
            }
        } catch (ReflectiveOperationException | RuntimeException error) { history.journal.omitted(); }
    }

    private void effect(String action, Object world, Object pos, Map<String, Object> actor, String registry)
            throws ReflectiveOperationException {
        Map<String, Object> row = row(action, world, pos, actor);
        row.put("registry", registry);
        pending.add(new Observation(null, null, null, null, null, row, System.currentTimeMillis()));
    }

    @SubscribeEvent
    public void tick(TickEvent.ServerTickEvent tick) {
        if (tick.phase == TickEvent.Phase.END) flush();
    }

    private void flush() {
        for (Observation observation : pending) {
            try {
                String status = "accepted";
                if (observation.event != null && observation.event.isCanceled()) {
                    status = "cancelled";
                } else if (observation.world != null) {
                    status = "observed";
                    if ((Boolean) loaded.invoke(observation.world, observation.pos)) {
                        Object current = stateAt.invoke(observation.world, observation.pos);
                        if (!current.equals(observation.before)
                                && (observation.after == null || current.equals(observation.after))) status = "changed";
                    }
                } else if (observation.event != null) {
                    status = "observed"; // A toss is signalled before its entity is added to the world.
                }
                observation.row.put("outcome", status);
                journal.record(observation.row, observation.at);
            } catch (ReflectiveOperationException | RuntimeException error) { journal.omitted(); }
        }
        pending.clear();
        budget = PER_TICK;
    }

    private static final class Observation {
        final Event event;
        final Object world, pos, before, after;
        final Map<String, Object> row;
        final long at;

        Observation(Event event, Object world, Object pos, Object before, Object after, Map<String, Object> row, long at) {
            this.event = event;
            this.world = world;
            this.pos = pos;
            this.before = before;
            this.after = after;
            this.row = row;
            this.at = at;
        }
    }
}
