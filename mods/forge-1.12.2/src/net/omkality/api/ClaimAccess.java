package net.omkality.api;

/** Opaque, server-thread ownership view for ONE native operation; never cache it. */
public interface ClaimAccess {
    Scope at(Object world, Object origin) throws Exception;
    interface Scope {
        boolean contains(Object world, Object target) throws Exception;
        boolean permitsWrite(Object world, Object target, boolean allowUnclaimed) throws Exception;
    }
}
