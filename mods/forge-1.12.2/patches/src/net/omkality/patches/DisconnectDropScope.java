package net.omkality.patches;

/** Identity-only permission for native finalization drops on the calling thread. */
public final class DisconnectDropScope implements AutoCloseable {
    private static final ThreadLocal<DisconnectDropScope> ACTIVE=new ThreadLocal<DisconnectDropScope>();
    private final Object actor;
    private final Object[] sources;
    private final DisconnectDropScope previous;
    private final Thread thread;

    private DisconnectDropScope(Object player,Object[] stacks) {
        if(player==null||stacks==null||stacks.length>14)throw new IllegalArgumentException("Invalid native disconnect drop scope");
        actor=player;sources=stacks.clone();previous=ACTIVE.get();thread=Thread.currentThread();ACTIVE.set(this);
    }
    public static DisconnectDropScope enter(Object actor,Object[] stacks) {return new DisconnectDropScope(actor,stacks);}
    public static boolean active() {return ACTIVE.get()!=null;}
    public static boolean permits(Object actor,Object stack) {
        DisconnectDropScope current=ACTIVE.get();
        if(current==null||actor==null||stack==null||current.actor!=actor)return false;
        for(Object source:current.sources)if(source==stack)return true;
        return false;
    }
    @Override public void close() {
        if(Thread.currentThread()!=thread||ACTIVE.get()!=this)throw new IllegalStateException("Native disconnect drop scope closed out of order");
        if(previous==null)ACTIVE.remove();else ACTIVE.set(previous);
    }
}
