package net.omkality;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.CommandEvent;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import org.apache.logging.log4j.Logger;

/** Console-only atomic view/drain of active AND pre-Forge login connections.
 * Credentials and authentication stay in Drasl. No player-visible command or cache.
 */
public final class RecoveryConnections {
    static String state = "not initialized";
    private final Object server;
    private final Class<?> rcon, login, play;
    private final Field connections, loginProfile, playPlayer;
    private final Method networkSystem, handler, open, close, playerProfile;
    private final Method profileId, profileName, disconnectPlay, disconnectLogin, sendMessage;
    private final Method eventSender, eventCommand, eventParameters, commandName;
    private final Constructor<?> text;
    private final Logger logger;

    public static void install(Logger log) throws Exception {
        MinecraftForge.EVENT_BUS.register(new RecoveryConnections(log));
        state = "enabled";
        log.info("Omkality account recovery connection adapter enabled (1.12.2)");
    }

    private static Method method(Class<?> type, String srg, String mcp, Class<?>... args) throws Exception {
        try { return type.getMethod(srg, args); }
        catch (NoSuchMethodException error) { return type.getMethod(mcp, args); }
    }

    private static Field field(Class<?> type, String srg, String mcp) throws Exception {
        Field value;
        try { value = type.getDeclaredField(srg); }
        catch (NoSuchFieldException error) { value = type.getDeclaredField(mcp); }
        value.setAccessible(true);
        return value;
    }

    private RecoveryConnections(Logger log) throws Exception {
        logger = log;
        server = FMLCommonHandler.class.getMethod("getMinecraftServerInstance").invoke(FMLCommonHandler.instance());
        Class<?> mcServer = Class.forName("net.minecraft.server.MinecraftServer");
        Class<?> network = Class.forName("net.minecraft.network.NetworkSystem");
        Class<?> manager = Class.forName("net.minecraft.network.NetworkManager");
        Class<?> component = Class.forName("net.minecraft.util.text.ITextComponent");
        Class<?> sender = Class.forName("net.minecraft.command.ICommandSender");
        Class<?> profile = Class.forName("com.mojang.authlib.GameProfile");
        rcon = Class.forName("net.minecraft.network.rcon.RConConsoleSource");
        login = Class.forName("net.minecraft.server.network.NetHandlerLoginServer");
        play = Class.forName("net.minecraft.network.NetHandlerPlayServer");
        networkSystem = method(mcServer, "func_147137_ag", "getNetworkSystem");
        connections = field(network, "field_151272_f", "networkManagers");
        handler = method(manager, "func_150729_e", "getNetHandler");
        open = method(manager, "func_150724_d", "isChannelOpen");
        close = method(manager, "func_150718_a", "closeChannel", component);
        loginProfile = field(login, "field_147337_i", "loginGameProfile");
        playPlayer = field(play, "field_147369_b", "player");
        playerProfile = method(Class.forName("net.minecraft.entity.player.EntityPlayer"), "func_146103_bH", "getGameProfile");
        profileId = profile.getMethod("getId");
        profileName = profile.getMethod("getName");
        disconnectPlay = method(play, "func_194028_b", "disconnect", component);
        disconnectLogin = method(login, "func_194026_b", "disconnect", component);
        sendMessage = method(sender, "func_145747_a", "sendMessage", component);
        text = Class.forName("net.minecraft.util.text.TextComponentString").getConstructor(String.class);
        eventSender = CommandEvent.class.getMethod("getSender");
        eventCommand = CommandEvent.class.getMethod("getCommand");
        eventParameters = CommandEvent.class.getMethod("getParameters");
        commandName = method(Class.forName("net.minecraft.command.ICommand"), "func_71517_b", "getName");
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public void command(CommandEvent event) {
        Object actor = null;
        try {
            if (!"list".equals(commandName.invoke(eventCommand.invoke(event)))) return;
            String[] args = (String[]) eventParameters.invoke(event);
            if (args.length == 0 || !"omk-recovery".equals(args[0])) return;
            event.setCanceled(true);
            actor = eventSender.invoke(event);
            if (!rcon.isInstance(actor)) {
                sendMessage.invoke(actor, text.newInstance("OMK_RECOVERY_ERROR console_only"));
                return;
            }
            if (args.length == 2 && "version".equals(args[1])) {
                sendMessage.invoke(actor, text.newInstance("OMK_RECOVERY_V1 {\"schema\":1,\"pending\":true}"));
                return;
            }
            if (args.length != 4 || !("inspect".equals(args[1]) || "drain".equals(args[1]))
                    || !args[2].matches("[0-9a-f-]{36}") || !args[3].matches("[A-Za-z0-9_]{3,16}")) {
                sendMessage.invoke(actor, text.newInstance("OMK_RECOVERY_ERROR invalid_request"));
                return;
            }
            UUID id = UUID.fromString(args[2]);
            boolean drain = "drain".equals(args[1]);
            int active = 0, pending = 0;
            Object source = connections.get(networkSystem.invoke(server));
            if (!(source instanceof List)) throw new IllegalStateException("Invalid connection collection");
            List<?> snapshot;
            synchronized (source) {
                if (((List<?>) source).size() > 10000) throw new IllegalStateException("Connection collection exceeded bound");
                snapshot = new ArrayList<Object>((List<?>) source);
            }
            for (Object connection : snapshot) {
                if (!Boolean.TRUE.equals(open.invoke(connection))) continue;
                Object listener = handler.invoke(connection);
                Object profile = login.isInstance(listener) ? loginProfile.get(listener)
                    : play.isInstance(listener) ? playerProfile.invoke(playPlayer.get(listener)) : null;
                if (profile == null) continue; // No LoginStart/authentication has happened yet.
                UUID actual = (UUID) profileId.invoke(profile);
                String name = (String) profileName.invoke(profile);
                if (!id.equals(actual) && !(actual == null && args[3].equalsIgnoreCase(name))) continue;
                if (login.isInstance(listener)) pending++; else active++;
                if (drain) {
                    Object reason = text.newInstance("omk_account_recovery");
                    if (play.isInstance(listener)) disconnectPlay.invoke(listener, reason);
                    else if (login.isInstance(listener)) disconnectLogin.invoke(listener, reason);
                    else close.invoke(connection, reason);
                }
            }
            sendMessage.invoke(actor, text.newInstance("OMK_RECOVERY_V1 {\"schema\":1,\"active\":"
                + active + ",\"pending\":" + pending + "}"));
        } catch (Exception error) {
            logger.error("Omkality account recovery connection operation failed", error);
            if (actor != null) try { sendMessage.invoke(actor, text.newInstance("OMK_RECOVERY_ERROR adapter_failure")); }
            catch (Exception ignored) { /* caller requires a valid structured response */ }
        }
    }
}
