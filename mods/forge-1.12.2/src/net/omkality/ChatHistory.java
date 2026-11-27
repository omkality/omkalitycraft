package net.omkality;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.CommandEvent;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.eventhandler.Event;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.common.gameevent.PlayerEvent;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Owner-only capture of reviewed Forge chat dispatch paths. */
public final class ChatHistory {
    private static final int TEXT_LIMIT = 768;
    private static final ThreadLocal<Dispatch> DISPATCH = new ThreadLocal<>();
    private static volatile ChatHistory active;
    private final PrivateJournal journal;
    private final Object server;
    private final Class<?> playerType, remoteConsole, translationType, chatPacket;
    private final Method profile, profileId, profileName, displayName, formatted, senderName, players, byId;
    private final Method packetText, translationKey, eventSender, eventCommand, eventParameters, sendMessage;
    private final Field networkPlayer, loginPlayer, chatComponent;
    private final Constructor<?> plainText;
    private final Logger logger;
    private final FtbChatProfiles ftb;

    static void install(Logger log, ServerProfile profile) {
        Map<String, String> env = System.getenv();
        String flag = env.getOrDefault("OMK_CHAT_HISTORY_ENABLED", "false");
        if ("false".equals(flag)) {
            CoreServices.report("core.chat_history", "disabled");
            return;
        }
        try {
            if (!"true".equals(flag) || !"enabled".equals(CoreServices.statuses().get("server.chat_dispatch")))
                throw new IllegalArgumentException("Unsupported server chat adapter");
            Path directory = Paths.get(env.getOrDefault("OMK_CHAT_HISTORY_DIRECTORY", "")).normalize();
            Path gameRoot = Paths.get(".").toAbsolutePath().normalize();
            if (!directory.isAbsolute() || directory.getParent() == null || directory.startsWith(gameRoot))
                throw new IllegalArgumentException("Dedicated chat history path required");
            String serverId = env.getOrDefault("OMK_CHAT_HISTORY_SERVER", "");
            if (!serverId.matches("[a-z0-9][a-z0-9_-]{0,47}"))
                throw new IllegalArgumentException("Valid chat history server ID required");
            int days = setting(env, "OMK_CHAT_HISTORY_DAYS", 90, 90);
            int mib = setting(env, "OMK_CHAT_HISTORY_MIB", 256, 256);
            active = new ChatHistory(log, serverId, profile.id, directory, days, mib);
            MinecraftForge.EVENT_BUS.register(active);
            CoreServices.report("core.chat_history", "enabled");
        } catch (Exception error) {
            log.warn("Omkality chat history unavailable ({})", error.getClass().getSimpleName());
            CoreServices.report("core.chat_history", "unavailable");
        }
    }

    static void stop() {
        ChatHistory instance = active;
        active = null;
        DISPATCH.remove();
        if (instance != null) {
            MinecraftForge.EVENT_BUS.unregister(instance);
            instance.journal.close();
        }
    }

    private static int setting(Map<String, String> env, String name, int fallback, int max) {
        String value = env.getOrDefault(name, Integer.toString(fallback));
        if (!value.matches("[1-9][0-9]{0,2}")) throw new IllegalArgumentException("Invalid chat history limit");
        int number = Integer.parseInt(value);
        if (number > max) throw new IllegalArgumentException("Invalid chat history limit");
        return number;
    }

    private ChatHistory(Logger log, String id, String profileIdValue, Path root, int days, int mib) throws Exception {
        logger = log;
        ftb = "enabled".equals(CoreServices.statuses().get("ftb.integration")) ? new FtbChatProfiles() : null;
        server = FMLCommonHandler.instance().getMinecraftServerInstance();
        playerType = Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        remoteConsole = Class.forName("net.minecraft.network.rcon.RConConsoleSource");
        translationType = Class.forName("net.minecraft.util.text.TextComponentTranslation");
        chatPacket = Class.forName("net.minecraft.network.play.server.SPacketChat");
        Class<?> gameProfile = Class.forName("com.mojang.authlib.GameProfile");
        Class<?> playerList = Class.forName("net.minecraft.server.management.PlayerList");
        Class<?> actor = Class.forName("net.minecraft.command.ICommandSender");
        Class<?> component = Class.forName("net.minecraft.util.text.ITextComponent");
        Class<?> connection = Class.forName("net.minecraft.network.NetHandlerPlayServer");
        Class<?> packet = Class.forName("net.minecraft.network.play.client.CPacketChatMessage");
        profile = playerType.getMethod("func_146103_bH");
        profileId = gameProfile.getMethod("getId");
        profileName = gameProfile.getMethod("getName");
        displayName = actor.getMethod("func_145748_c_");
        formatted = component.getMethod("func_150254_d");
        senderName = actor.getMethod("func_70005_c_");
        players = Class.forName("net.minecraft.server.MinecraftServer").getMethod("func_184103_al");
        byId = playerList.getMethod("func_177451_a", UUID.class);
        packetText = packet.getMethod("func_149439_c");
        // The chat component getter is absent from the dedicated server JAR.
        chatComponent = chatPacket.getDeclaredField("field_148919_a");
        chatComponent.setAccessible(true);
        networkPlayer = connection.getField("field_147369_b");
        translationKey = translationType.getMethod("func_150268_i");
        eventSender = CommandEvent.class.getMethod("getSender");
        eventCommand = CommandEvent.class.getMethod("getCommand");
        eventParameters = CommandEvent.class.getMethod("getParameters");
        loginPlayer = PlayerEvent.class.getField("player");
        sendMessage = actor.getMethod("func_145747_a", component);
        plainText = Class.forName("net.minecraft.util.text.TextComponentString").getConstructor(String.class);
        journal = new PrivateJournal(PrivateJournal.Stream.CHAT, root, id, profileIdValue, days, mib * 1024 * 1024, 0,
            problem -> log.warn("Omkality chat history unavailable ({})", problem));
    }

    /** Show the chat rule when the player enters an archiving server. */
    @SubscribeEvent
    public void login(PlayerEvent.PlayerLoggedInEvent event) {
        try {
            Object player = loginPlayer.get(event);
            if (playerType.isInstance(player))
                sendMessage.invoke(player, plainText.newInstance(
                    "Общий и личный чат сохраняются для разбора жалоб. Доступ к истории есть у владельца сервера."));
        } catch (ReflectiveOperationException | RuntimeException error) {
            logger.warn("Omkality chat history notice unavailable ({})", error.getClass().getSimpleName());
        }
    }

    private static String clip(String text, int maximum) {
        if (text.codePointCount(0, text.length()) <= maximum) return text;
        return text.substring(0, text.offsetByCodePoints(0, maximum));
    }

    private Map<String, Object> identity(Object source) throws ReflectiveOperationException {
        Map<String, Object> result = new LinkedHashMap<>();
        String nickname = "";
        if (playerType.isInstance(source)) {
            Object game = profile.invoke(source);
            UUID id = (UUID) profileId.invoke(game);
            if (id == null || byId.invoke(players.invoke(server), id) != source) return null;
            result.put("kind", "player");
            result.put("uuid", id.toString());
            result.put("name", clip((String) profileName.invoke(game), 32));
            if (ftb != null) nickname = ftb.nickname(id);
        } else if (source == server || remoteConsole.isInstance(source)) {
            result.put("kind", "console");
            result.put("uuid", null);
            result.put("name", clip((String) senderName.invoke(source), 32));
        } else {
            return null;
        }
        result.put("display", clip((String) formatted.invoke(displayName.invoke(source)), 128));
        result.put("nickname", nickname.isEmpty() ? null : clip(nickname, 128));
        return result;
    }

    private void record(Dispatch frame, String outcome, Object recipient) {
        if (frame.channel == null || frame.text.isEmpty()) return;
        try {
            Map<String, Object> actor = identity(frame.source);
            if (actor == null) return;
            Map<String, Object> destination = recipient == null ? null : identity(recipient);
            if ("sent".equals(outcome) && frame.channel.direct && destination == null) {
                journal.omitted();
                return;
            }
            String body = clip(frame.text, TEXT_LIMIT);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("channel", frame.channel.name().toLowerCase(Locale.ROOT));
            row.put("outcome", outcome);
            row.put("actor", actor);
            row.put("recipient", destination);
            row.put("target", frame.target != null && destination == null ? clip(frame.target, 128) : null);
            row.put("text", body);
            row.put("truncated", body.length() < frame.text.length());
            journal.record(row);
        } catch (ReflectiveOperationException | RuntimeException error) { journal.omitted(); }
    }

    private Dispatch publicLine(Object network, Object packet) throws ReflectiveOperationException {
        return new Dispatch(DISPATCH.get(), Channel.PUBLIC, networkPlayer.get(network),
            (String) packetText.invoke(packet), null);
    }

    /** Observe a public message cancelled by the complete Forge event chain. */
    public static void publicRejected(Object network, Object packet) {
        ChatHistory current = active;
        if (current == null) return;
        try { current.record(current.publicLine(network, packet), "rejected", null); }
        catch (ReflectiveOperationException | RuntimeException error) { current.journal.omitted(); }
    }

    /** Bind the original message to a call to the native broadcast. */
    public static void enterPublic(Object network, Object packet) {
        ChatHistory current = active;
        if (current == null) return;
        try {
            DISPATCH.set(current.publicLine(network, packet));
        } catch (ReflectiveOperationException | RuntimeException error) {
            DISPATCH.set(new Dispatch(DISPATCH.get(), null, null, "", null));
            current.journal.omitted();
        }
    }

    /** Open a scope around exactly one native command execution. */
    public static void enterCommand(Object command, Object source, String[] args) {
        ChatHistory current = active;
        if (current != null) DISPATCH.set(commandLine(current.channel(command), source, args));
    }

    /** Clear sender and arguments even when the native operation throws. */
    public static void leaveDispatch(boolean completed) {
        Dispatch frame = DISPATCH.get();
        if (frame == null) return;
        if (frame.parent == null) DISPATCH.remove();
        else DISPATCH.set(frame.parent);
        ChatHistory current = active;
        if (current != null && completed && !frame.forwarded) current.record(frame, "accepted", null);
    }

    /** Observe a chat packet submitted for network delivery after native visibility checks. */
    public static void packetSent(Object network, Object packet) {
        ChatHistory current = active;
        if (current == null) return;
        Dispatch frame = DISPATCH.get();
        if (frame == null || frame.channel == null || !current.chatPacket.isInstance(packet)) return;
        try {
            if (frame.channel == Channel.PRIVATE) {
                Object component = current.chatComponent.get(packet);
                // Vanilla /tell sends a separate outgoing echo to the sender.
                if (!current.translationType.isInstance(component)
                        || !"commands.message.display.incoming".equals(current.translationKey.invoke(component))) return;
            }
            if (!frame.forwarded || frame.channel.direct)
                current.record(frame, "sent", frame.channel.direct ? current.networkPlayer.get(network) : null);
            frame.forwarded = true;
        } catch (ReflectiveOperationException | RuntimeException error) { current.journal.omitted(); }
    }

    /** Record recognized messaging commands cancelled by Forge, regardless of its return code. */
    public static void commandCancelled(Event event) {
        ChatHistory current = active;
        if (current == null || !(event instanceof CommandEvent)) return;
        try {
            Channel channel = current.channel(current.eventCommand.invoke(event));
            if (channel != null) current.record(commandLine(channel, current.eventSender.invoke(event),
                (String[]) current.eventParameters.invoke(event)), "rejected", null);
        } catch (ReflectiveOperationException | RuntimeException error) { current.journal.omitted(); }
    }

    /** Native command failure before a completed dispatch, including permission and target lookup. */
    public static void commandRejected(Object source, String input, Map<String, ?> commands) {
        ChatHistory current = active;
        if (current == null) return;
        String line = input.trim();
        if (line.startsWith("/")) line = line.substring(1);
        int split = line.indexOf(' ');
        if (split <= 0 || split > 64) return;
        Channel channel = current.channel(commands.get(line.substring(0, split)));
        if (channel != null) current.record(commandLine(channel, source, line.substring(split + 1).split(" ")),
            "rejected", null);
    }

    private static Dispatch commandLine(Channel channel, Object source, String[] args) {
        if (channel == null) return new Dispatch(DISPATCH.get(), null, source, "", null);
        int start = channel.direct ? 1 : 0;
        String text = args.length > start ? String.join(" ", Arrays.copyOfRange(args, start, args.length)) : "";
        return new Dispatch(DISPATCH.get(), channel, source, text,
            channel.direct && args.length > 0 ? args[0] : null);
    }

    private Channel channel(Object command) {
        try {
            return Channel.of(ftb == null ? command : ftb.original(command));
        } catch (IllegalAccessException error) {
            journal.omitted();
            return null;
        }
    }

    private enum Channel {
        PUBLIC(false), PRIVATE(true), EMOTE(false), BROADCAST(false), TELLRAW(true);

        final boolean direct;

        Channel(boolean direct) { this.direct = direct; }

        static Channel of(Object command) {
            if (command == null) return null;
            switch (command.getClass().getName()) {
                case "net.minecraft.command.server.CommandMessage": return PRIVATE;
                case "net.minecraft.command.server.CommandEmote": return EMOTE;
                case "net.minecraft.command.server.CommandBroadcast": return BROADCAST;
                case "net.minecraft.command.server.CommandMessageRaw": return TELLRAW;
                default: return null;
            }
        }
    }

    private static final class Dispatch {
        final Dispatch parent;
        final Channel channel;
        final Object source;
        final String text, target;
        boolean forwarded;

        Dispatch(Dispatch parent, Channel channel, Object source, String text, String target) {
            this.parent = parent;
            this.channel = channel;
            this.source = source;
            this.text = text;
            this.target = target;
        }
    }
}
