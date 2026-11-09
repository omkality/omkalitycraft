package net.omkality;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.CommandEvent;
import org.apache.logging.log4j.Logger;
import net.minecraftforge.fml.common.Loader;
import net.minecraftforge.fml.common.ModContainer;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;

/** Narrow, version-pinned server adapter. FTB still owns mute state and permissions.
 * Reflection is confined here because the minimal private build has no mapped MC
 * classes. Resolve once at startup, fail closed on API mismatch, never parse chat.
 */
public final class FtbMuteGuard {
    static String state = "not initialized";
    private final Class<?> player;
    private final Method sender, command, commandName, persisted, boolTag, speak, sendMessage;
    private final Constructor<?> message;
    private final Logger log;
    private final Set<String> chatCommands = new HashSet<String>(Arrays.asList("me", "tell", "msg", "w", "say"));
    private boolean failed;

    public static void install(Logger log) throws Exception {
        state = "initializing";
        if (!Loader.isModLoaded("ftbutilities")) { state = "ftb absent"; return; }
        requireVersion("ftbutilities", "5.4.1.131");
        requireVersion("ftblib", "5.4.7.2");
        MinecraftForge.EVENT_BUS.register(new FtbMuteGuard(log));
        state = "enabled";
        log.info("Omkality FTB mute command guard enabled (1.12.2 adapter)");
    }

    static void requireVersion(String id, String version) {
        ModContainer mod = Loader.instance().getIndexedModList().get(id);
        if (mod == null || !version.equals(mod.getVersion())) {
            throw new IllegalStateException("Unsupported FTB mute adapter version: " + id);
        }
    }

    private static Method method(Class<?> type, String srg, String mcp, Class<?>... args) throws Exception {
        try { return type.getMethod(srg, args); }
        catch (NoSuchMethodException e) { return type.getMethod(mcp, args); }
    }

    private FtbMuteGuard(Logger logger) throws Exception {
        log = logger;
        player = Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        Class<?> basePlayer = Class.forName("net.minecraft.entity.player.EntityPlayer");
        sender = CommandEvent.class.getMethod("getSender");
        command = CommandEvent.class.getMethod("getCommand");
        commandName = method(Class.forName("net.minecraft.command.ICommand"), "func_71517_b", "getName");
        persisted = Class.forName("com.feed_the_beast.ftblib.lib.util.NBTUtils")
            .getMethod("getPersistedData", basePlayer, boolean.class);
        boolTag = method(Class.forName("net.minecraft.nbt.NBTTagCompound"), "func_74767_n", "getBoolean", String.class);
        speak = Class.forName("net.minecraftforge.server.permission.PermissionAPI")
            .getMethod("hasPermission", basePlayer, String.class);
        message = Class.forName("net.minecraft.util.text.TextComponentTranslation")
            .getConstructor(String.class, Object[].class);
        sendMessage = method(Class.forName("net.minecraft.command.ICommandSender"), "func_145747_a", "sendMessage",
            Class.forName("net.minecraft.util.text.ITextComponent"));
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public void onCommand(CommandEvent event) {
        try {
            Object actor = sender.invoke(event);
            if (!player.isInstance(actor)) return; // Console/command blocks keep their own policy.
            String name = commandName.invoke(command.invoke(event)).toString();
            if (!chatCommands.contains(name)) return; // Commands such as home/claims keep working.
            Object data = persisted.invoke(null, actor, false);
            boolean muted = data != null && Boolean.TRUE.equals(boolTag.invoke(data, "muted"));
            if (failed || muted || !Boolean.TRUE.equals(speak.invoke(null, actor, "ftbutilities.chat.speak"))) {
                cancel(event, "ftbutilities.lang.commands.mute.muted");
            }
        } catch (Exception error) {
            if (!failed) log.error("Omkality FTB mute adapter failed; message commands are blocked", error);
            failed = true;
            // A reflection failure cannot silently restore a muted command.
            event.setCanceled(true);
            try { cancel(event, "Omkality chat protection is unavailable"); }
            catch (Exception ignored) { /* Already cancelled, no command execution. */ }
        }
    }

    private void cancel(CommandEvent event, String key) throws Exception {
        event.setCanceled(true);
        // Forge 1.12 deliberately ignores a checked CommandException attached
        // to a cancelled event. Send feedback explicitly, then keep it cancelled.
        sendMessage.invoke(sender.invoke(event), message.newInstance(key, new Object[0]));
    }
}
