package net.omkality.client;

import java.util.concurrent.Callable;
import java.util.function.BooleanSupplier;
import net.minecraft.network.INetHandler;
import net.minecraft.network.NetworkManager;
import net.minecraft.network.Packet;

/** Preserve the original packet call and its exception semantics. */
public final class NetworkPacketBridge {
    private NetworkPacketBridge() {}

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void process(final NetworkManager connection, final Packet packet, final INetHandler handler) throws Exception {
        ClientNetworkTasks.inNetworkScope(new BooleanSupplier() {
            @Override public boolean getAsBoolean() { return connection.func_150724_d(); }
        }, new Callable<Object>() {
            @Override public Object call() { packet.func_148833_a(handler); return null; }
        });
    }
}
