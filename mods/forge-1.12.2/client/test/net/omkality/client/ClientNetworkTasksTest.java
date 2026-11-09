package net.omkality.client;

import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;

public final class ClientNetworkTasksTest {
    private static int checks;
    private static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        checks++;
    }
    private static BooleanSupplier flag(final AtomicBoolean value) {
        return new BooleanSupplier() { public boolean getAsBoolean() { return value.get(); } };
    }
    private static <V> Callable<V> captured(final BooleanSupplier connection, final Callable<V> task) throws Exception {
        return ClientNetworkTasks.inNetworkScope(connection, new Callable<Callable<V>>() {
            public Callable<V> call() { return ClientNetworkTasks.wrap(task); }
        });
    }
    public static void main(String[] args) throws Exception {
        final AtomicInteger effects = new AtomicInteger();
        final Callable<Integer> local = new Callable<Integer>() { public Integer call() { return effects.incrementAndGet(); } };
        check(ClientNetworkTasks.wrap(local) == local, "ordinary local work must keep identity");
        final AtomicBoolean old = new AtomicBoolean(true), next = new AtomicBoolean(true);
        Callable<Integer> stale = captured(flag(old), local);
        old.set(false);
        check(stale.call() == null && effects.get() == 0, "a queued old-session task must not touch an unloaded player");
        Callable<Integer> current = captured(flag(next), local);
        check(current.call() == 1, "new open connection must work after old connection closed");
        check(ClientNetworkTasks.wrap(local) == local, "network scope must not leak into GUI tasks");
        final Exception original = new Exception("test-open-task-failure");
        try {
            captured(flag(next), new Callable<Object>() { public Object call() throws Exception { throw original; } }).call();
            throw new AssertionError("open task exception hidden");
        } catch (Exception error) { check(error == original, "open task failure must be preserved exactly"); }
        try {
            ClientNetworkTasks.inNetworkScope(flag(next), new Callable<Object>() { public Object call() throws Exception { throw original; } });
            throw new AssertionError("dispatch exception hidden");
        } catch (Exception error) { check(error == original, "packet dispatch failure must be preserved exactly"); }
        check(ClientNetworkTasks.wrap(local) == local, "exception must clear thread-local network context");
        Callable<Integer> nested = ClientNetworkTasks.inNetworkScope(flag(next), new Callable<Callable<Integer>>() {
            public Callable<Integer> call() throws Exception {
                Callable<Integer> inner = captured(flag(old), local);
                check(inner.call() == null, "inner closed connection should be skipped");
                return ClientNetworkTasks.wrap(local);
            }
        });
        check(nested.call() == 2, "nested scope must restore the original open connection");
        final AtomicInteger inherited = new AtomicInteger();
        ClientNetworkTasks.inNetworkScope(flag(next), new Callable<Object>() {
            public Object call() throws Exception {
                final Callable<Integer> identity = local;
                Thread other = new Thread(new Runnable() { public void run() {
                    if (ClientNetworkTasks.wrap(identity) == identity) inherited.incrementAndGet();
                }});
                other.start();other.join();return null;
            }
        });
        check(inherited.get() == 1, "network scope must be isolated between threads");
        final AtomicBoolean parent = new AtomicBoolean(true);
        final Callable<?>[] descendant = new Callable<?>[1];
        Callable<Object> outer = captured(flag(parent), new Callable<Object>() {
            public Object call() { descendant[0] = ClientNetworkTasks.wrap(local); return null; }
        });
        outer.call();parent.set(false);
        check(descendant[0].call() == null && effects.get() == 2, "nested deferred work must retain the originating session");
        final RuntimeException stateError = new RuntimeException("test-channel-state-failure");
        Callable<Integer> badState = captured(new BooleanSupplier() { public boolean getAsBoolean() { throw stateError; } }, local);
        try { badState.call();throw new AssertionError("state failure hidden"); }
        catch (RuntimeException error) { check(error == stateError, "state-query bugs must not be silently ignored"); }
        check(ClientNetworkTasks.discardedCount() == 3, "only three deliberately stale tasks skipped");
        check(ClientNetworkTasks.wrap(local) == local, "all scopes cleaned after complete suite");
        System.out.println("Client network scope checks: " + checks);
    }
}
