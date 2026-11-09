package net.omkality.client;

import java.util.ArrayDeque;
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.BooleanSupplier;

/** Capture the originating connection, never the next world's player or connection. */
public final class ClientNetworkTasks {
    private static final ThreadLocal<ArrayDeque<BooleanSupplier>> SCOPES = new ThreadLocal<ArrayDeque<BooleanSupplier>>();
    private static final AtomicLong WRAPPED = new AtomicLong();
    private static final AtomicLong EXECUTED = new AtomicLong();
    private static final AtomicLong DISCARDED = new AtomicLong();

    private ClientNetworkTasks() {}

    public static <V> V inNetworkScope(BooleanSupplier connectionOpen, Callable<V> body) throws Exception {
        if (connectionOpen == null || body == null) throw new NullPointerException();
        ArrayDeque<BooleanSupplier> scopes = SCOPES.get();
        if (scopes == null) {
            scopes = new ArrayDeque<BooleanSupplier>();
            SCOPES.set(scopes);
        }
        scopes.push(connectionOpen);
        try { return body.call(); }
        finally {
            scopes.pop();
            if (scopes.isEmpty()) SCOPES.remove();
        }
    }

    public static <V> Callable<V> wrap(final Callable<V> body) {
        if (body == null) throw new NullPointerException();
        ArrayDeque<BooleanSupplier> scopes = SCOPES.get();
        if (scopes == null || scopes.isEmpty()) return body;
        final BooleanSupplier originatingConnection = scopes.peek();
        WRAPPED.incrementAndGet();
        return new Callable<V>() {
            @Override public V call() throws Exception {
                if (!originatingConnection.getAsBoolean()) {
                    DISCARDED.incrementAndGet();
                    return null;
                }
                EXECUTED.incrementAndGet();
                return inNetworkScope(originatingConnection, body);
            }
        };
    }

    public static long wrappedCount() { return WRAPPED.get(); }
    public static long executedCount() { return EXECUTED.get(); }
    public static long discardedCount() { return DISCARDED.get(); }
}
