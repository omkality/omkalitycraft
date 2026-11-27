package net.omkality.patches;

import java.util.Map;
import net.minecraftforge.fml.common.eventhandler.Event;
import net.omkality.ChatHistory;

/** Keep the early mixins linkable before Forge adds the Core mod to the classpath. */
public final class ChatDispatch {
    private static volatile boolean ready;

    private ChatDispatch() {}

    /** Enable forwarding once Core and the server extension have loaded. */
    public static void ready() { ready = true; }

    /** Bind the native broadcast to its authenticated origin and original packet. */
    public static void enterPublic(Object network, Object packet) {
        if (ready) ChatHistory.enterPublic(network, packet);
    }

    /** Forward cancellation after the Forge event chain. */
    public static void publicRejected(Object network, Object packet) {
        if (ready) ChatHistory.publicRejected(network, packet);
    }

    /** Bind dispatch to the native command's sender and arguments. */
    public static void enterCommand(Object command, Object sender, String[] args) {
        if (ready) ChatHistory.enterCommand(command, sender, args);
    }

    /** End a native dispatch, recording messages admitted without a queued packet. */
    public static void leaveDispatch(boolean completed) {
        if (ready) ChatHistory.leaveDispatch(completed);
    }

    /** Forward an outbound packet after the native chat visibility check. */
    public static void packetSent(Object network, Object packet) {
        if (ready) ChatHistory.packetSent(network, packet);
    }

    /** Forward cancellation of a chat command after Forge listeners. */
    public static void commandCancelled(Event event) {
        if (ready) ChatHistory.commandCancelled(event);
    }

    /** Forward native lookup and permission failures. */
    public static void commandRejected(Object sender, String input, Map<String, ?> commands) {
        if (ready) ChatHistory.commandRejected(sender, input, commands);
    }
}
