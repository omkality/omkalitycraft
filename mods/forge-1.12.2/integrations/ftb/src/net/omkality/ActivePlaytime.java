package net.omkality;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;
import java.util.WeakHashMap;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.common.gameevent.TickEvent;
import org.apache.logging.log4j.Logger;

/** Save time between server-observed player actions in the player's normal save. */
public final class ActivePlaytime {
    private static final String KEY = "omkality_active_millis";
    private static final long IDLE_MILLIS = 5 * 60 * 1000L;
    private final Method players, getPlayers, activity, persisted, getTime, setTime;
    private final Field x, z, yaw, pitch;
    private final Logger log;
    private final Map<Object, Sample> last = new WeakHashMap<Object, Sample>();
    private int ticks;
    private boolean failed;

    static void install(Logger log) throws Exception {
        MinecraftForge.EVENT_BUS.register(new ActivePlaytime(log));
    }

    private ActivePlaytime(Logger log) throws Exception {
        this.log = log;
        Class<?> server = Class.forName("net.minecraft.server.MinecraftServer");
        Class<?> player = Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        Class<?> nbt = Class.forName("net.minecraft.nbt.NBTTagCompound");
        players = server.getMethod("func_184103_al");
        getPlayers = players.getReturnType().getMethod("func_181057_v");
        activity = player.getMethod("func_154331_x");
        x = player.getField("field_70165_t");
        z = player.getField("field_70161_v");
        yaw = player.getField("field_70177_z");
        pitch = player.getField("field_70125_A");
        persisted = Class.forName("com.feed_the_beast.ftblib.lib.util.NBTUtils")
            .getMethod("getPersistedData", Class.forName("net.minecraft.entity.player.EntityPlayer"), boolean.class);
        getTime = nbt.getMethod("func_74763_f", String.class);
        setTime = nbt.getMethod("func_74772_a", String.class, long.class);
    }

    @SubscribeEvent
    public void onTick(TickEvent.ServerTickEvent event) {
        if (failed || event.phase != TickEvent.Phase.END || ++ticks < 20) return;
        ticks = 0;
        try {
            Object server = FMLCommonHandler.instance().getMinecraftServerInstance();
            for (Object player : (List<?>) getPlayers.invoke(players.invoke(server))) sample(player);
        } catch (ReflectiveOperationException error) {
            failed = true;
            log.error("Could not record active play time", error);
        }
    }

    private void sample(Object player) throws ReflectiveOperationException {
        Sample current = new Sample(x.getDouble(player), z.getDouble(player),
                yaw.getFloat(player), pitch.getFloat(player), (Long) activity.invoke(player));
        Sample previous = last.put(player, current);
        if (previous != null) {
            if (current.movedFrom(previous)) current.action = System.currentTimeMillis();
            if (current.action <= previous.action) {
                current.action = previous.action;
                return;
            }
        }
        Object data = persisted.invoke(null, player, true);
        long total = (Long) getTime.invoke(data, KEY);
        long gap = previous == null ? 0 : current.action - previous.action;
        if (gap > 0 && gap < IDLE_MILLIS) total += gap;
        setTime.invoke(data, KEY, total);
    }

    private static final class Sample {
        final double x, z;
        final float yaw, pitch;
        long action;

        Sample(double x, double z, float yaw, float pitch, long action) {
            this.x = x;
            this.z = z;
            this.yaw = yaw;
            this.pitch = pitch;
            this.action = action;
        }

        boolean movedFrom(Sample previous) {
            return Math.abs(x - previous.x) > 0.04 || Math.abs(z - previous.z) > 0.04
                || Math.abs(yaw - previous.yaw) > 0.5f || Math.abs(pitch - previous.pitch) > 0.5f;
        }
    }
}
