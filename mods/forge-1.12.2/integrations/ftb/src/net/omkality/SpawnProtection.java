package net.omkality;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.WeakHashMap;
import com.feed_the_beast.ftblib.lib.data.ForgeTeam;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.event.world.BlockEvent;
import net.minecraftforge.fml.common.eventhandler.Event;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import org.apache.logging.log4j.Logger;

/** Use FTB ownership for denial and send a short, throttled hint to the player. */
public final class SpawnProtection {
    private final ForgeTeam team;
    private final Logger log;
    private final Class<?> playerType, fakePlayer;
    private final Method breakPlayer, clickPlayer, breakWorld, clickWorld, breakPos, clickPos, send;
    private final Constructor<?> message;
    private final Map<Object, Long> lastHint = new WeakHashMap<Object, Long>();
    private boolean reported;

    SpawnProtection(ForgeTeam team, Logger log) throws Exception {
        this.team = team;
        this.log = log;
        playerType = Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        fakePlayer = Class.forName("net.minecraftforge.common.util.FakePlayer");
        breakPlayer = BlockEvent.BreakEvent.class.getMethod("getPlayer");
        clickPlayer = PlayerInteractEvent.class.getMethod("getEntityPlayer");
        breakWorld = BlockEvent.class.getMethod("getWorld");
        clickWorld = PlayerInteractEvent.class.getMethod("getWorld");
        breakPos = BlockEvent.class.getMethod("getPos");
        clickPos = PlayerInteractEvent.class.getMethod("getPos");
        send = playerType.getMethod("func_145747_a", Class.forName("net.minecraft.util.text.ITextComponent"));
        message = Class.forName("net.minecraft.util.text.TextComponentString").getConstructor(String.class);
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST, receiveCanceled = true)
    public void onBreak(BlockEvent.BreakEvent event) {
        protect(event, breakPlayer, breakWorld, breakPos);
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST, receiveCanceled = true)
    public void onClick(PlayerInteractEvent.LeftClickBlock event) {
        protect(event, clickPlayer, clickWorld, clickPos);
    }

    private void protect(Event event, Method actor, Method level, Method position) {
        try {
            Object player = actor.invoke(event);
            if (!playerType.isInstance(player) || fakePlayer.isInstance(player)) return;
            Object world = level.invoke(event), pos = position.invoke(event);
            if (FtbClaimDomains.owner(FtbClaimDomains.flush(), world, pos) != team) return;
            event.setCanceled(true);
            long now = System.nanoTime();
            Long last = lastHint.get(player);
            if (last == null || now - last >= 3000000000L) {
                lastHint.put(player, now);
                send.invoke(player, message.newInstance(
                    "Вы на территории спавна. Чтобы найти место для игры, введите /rtp."));
            }
        } catch (Exception failure) {
            if (!reported) log.error("Could not show the spawn protection hint", failure);
            reported = true;
        }
    }
}
