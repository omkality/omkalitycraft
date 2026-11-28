package net.omkality.dj2;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import net.minecraft.command.CommandBase;
import net.minecraft.command.ICommand;
import net.minecraft.command.ICommandSender;
import net.minecraft.server.MinecraftServer;
import net.minecraftforge.fml.common.FMLCommonHandler;
import org.apache.logging.log4j.Logger;

/** Sort the authoritative inventory of the multiplayer crate the player has open. */
final class CrateSortCommand extends CommandBase {
    private static final String NAME = "omk_sort_crate";
    private static final String AA = "de.ellpeck.actuallyadditions.mod.";
    private final Logger log;
    private final Access access;

    static void install(Logger log) throws ReflectiveOperationException {
        Object server = FMLCommonHandler.instance().getMinecraftServerInstance();
        Object manager = server.getClass().getMethod("func_71187_D").invoke(server);
        manager.getClass().getMethod("func_71560_a", ICommand.class)
            .invoke(manager, new CrateSortCommand(log));
    }

    private CrateSortCommand(Logger log) throws ReflectiveOperationException {
        this.log = log;
        this.access = new Access();
    }

    @Override public String func_71517_b() { return NAME; }
    @Override public String func_71518_a(ICommandSender sender) { return "/" + NAME + " <window>"; }

    @Override public boolean func_184882_a(MinecraftServer server, ICommandSender sender) {
        return access.player.isInstance(sender);
    }

    @Override public void func_184881_a(MinecraftServer server, ICommandSender sender, String[] args) {
        if (!access.player.isInstance(sender) || args.length != 1 || !args[0].matches("[1-9][0-9]{0,2}")) {
            return;
        }
        try {
            Object open = access.open.get(sender);
            if (open == null || open.getClass() != access.container
                || access.window.getInt(open) != Integer.parseInt(args[0])
                || !(Boolean) access.canUse.invoke(open, sender)
                || (Boolean) access.spectator.invoke(sender)
                || !access.empty(access.cursor.invoke(access.playerInventory.get(sender)))) {
                return;
            }
            Object tile = access.tile.get(open);
            Object inventory = access.crateInventory.get(tile);
            int size = (Integer) access.slots.invoke(inventory);
            if (size == 117 || size == 234 || size == 351) {
                sort(inventory, size);
                access.detectChanges.invoke(open);
            }
        } catch (ReflectiveOperationException error) {
            log.error("Could not sort the open storage crate", error);
        }
    }

    private void sort(Object inventory, int size) throws ReflectiveOperationException {
        int limit = (Integer) access.slotLimit.invoke(inventory, 0);
        List<Object> before = new ArrayList<>(size);
        List<Stack> entries = new ArrayList<>(size);
        Map<Object, Stack> partials = new LinkedHashMap<>();
        Object empty = access.emptyStack.get(null);
        for (int slot = 0; slot < size; slot++) {
            Object source = access.get.invoke(inventory, slot);
            before.add(source);
            if (access.empty(source)) {
                continue;
            }
            Object copy = access.copy.invoke(source);
            int count = (Integer) access.count.invoke(copy);
            int maximum = Math.min(limit, (Integer) access.maxCount.invoke(copy));
            Object item = access.item.invoke(copy);
            String name = String.valueOf(access.registry.invoke(item));
            int damage = (Integer) access.damage.invoke(copy);
            Stack row = new Stack(copy, name, damage, count);
            if (maximum <= 1 || count >= maximum) {
                entries.add(row);
                continue;
            }
            // Stack serialization also covers Forge capabilities. Matching
            // registry names and metadata alone cannot establish stack equality.
            access.setCount.invoke(copy, 1);
            Object key = access.serialize.invoke(copy);
            access.setCount.invoke(copy, count);
            Stack previous = partials.get(key);
            if (previous != null) {
                int moved = Math.min(count, maximum - previous.count);
                previous.count += moved;
                row.count -= moved;
                access.setCount.invoke(previous.value, previous.count);
                if (previous.count == maximum) {
                    partials.remove(key);
                }
            }
            if (row.count > 0) {
                access.setCount.invoke(row.value, row.count);
                entries.add(row);
                partials.put(key, row);
            }
        }
        entries.sort(Comparator.comparing((Stack row) -> row.name)
            .thenComparingInt(row -> row.damage).thenComparingInt(row -> -row.count));
        for (int index = 0; index < size; index++) {
            Object sorted = index < entries.size() ? entries.get(index).value : empty;
            if (!(Boolean) access.equal.invoke(null, before.get(index), sorted)) {
                access.set.invoke(inventory, index, sorted);
            }
        }
    }

    private static final class Stack {
        final Object value;
        final String name;
        final int damage;
        int count;

        Stack(Object value, String name, int damage, int count) {
            this.value = value;
            this.name = name;
            this.damage = damage;
            this.count = count;
        }
    }

    private static final class Access {
        final Class<?> player = Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        final Class<?> container = Class.forName(AA + "inventory.ContainerGiantChest");
        final Field open = player.getField("field_71070_bA");
        final Field playerInventory = player.getField("field_71071_by");
        final Field window = container.getField("field_75152_c");
        final Field tile = container.getField("tileChest");
        final Field crateInventory = Class.forName(AA + "tile.TileEntityInventoryBase").getField("inv");
        final Method canUse = container.getMethod("func_75145_c", Class.forName("net.minecraft.entity.player.EntityPlayer"));
        final Method spectator = player.getMethod("func_175149_v");
        final Method cursor = playerInventory.getType().getMethod("func_70445_o");
        final Method detectChanges = container.getMethod("func_75142_b");
        final Class<?> inventory = Class.forName("net.minecraftforge.items.IItemHandlerModifiable");
        final Class<?> stack = Class.forName("net.minecraft.item.ItemStack");
        final Field emptyStack = stack.getField("field_190927_a");
        final Method slots = inventory.getMethod("getSlots");
        final Method slotLimit = inventory.getMethod("getSlotLimit", int.class);
        final Method get = inventory.getMethod("getStackInSlot", int.class);
        final Method set = inventory.getMethod("setStackInSlot", int.class, stack);
        final Method isEmpty = stack.getMethod("func_190926_b");
        final Method copy = stack.getMethod("func_77946_l");
        final Method count = stack.getMethod("func_190916_E");
        final Method setCount = stack.getMethod("func_190920_e", int.class);
        final Method maxCount = stack.getMethod("func_77976_d");
        final Method item = stack.getMethod("func_77973_b");
        final Method damage = stack.getMethod("func_77952_i");
        final Method serialize = stack.getMethod("serializeNBT");
        final Method equal = stack.getMethod("func_77989_b", stack, stack);
        final Method registry = item.getReturnType().getMethod("getRegistryName");

        Access() throws ReflectiveOperationException {}

        boolean empty(Object value) throws ReflectiveOperationException {
            return (Boolean) isEmpty.invoke(value);
        }
    }
}
