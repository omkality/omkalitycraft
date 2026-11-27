package net.omkality.patches;

import net.omkality.ActionHistory;

/** Connect the early native patch classes only after the Core mod has loaded. */
public final class ActionDispatch {
    private static volatile boolean ready;

    private ActionDispatch() {}

    public static void ready() { ready = true; }

    public static void activation(Object player, Object world, Object pos, Object state) {
        if (ready) ActionHistory.activation(player, world, pos, state);
    }

    public static void piston(Object world, Object pos, Object state) {
        if (ready) ActionHistory.piston(world, pos, state);
    }

    public static void sign(Object handler, Object packet) {
        if (ready) ActionHistory.edit(handler, packet, null);
    }

    public static void book(Object handler, String action) {
        if (ready) ActionHistory.edit(handler, null, action);
    }
}
