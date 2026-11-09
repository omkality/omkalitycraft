package net.omkality.api;

/** Server-thread permission view for ONE player's native operation. */
public interface PlayerPlacementAccess {
    Scope at(Object player,Object world) throws Exception;
    interface Scope {
        boolean permits(Object target,Object placedState) throws Exception;
    }
}
