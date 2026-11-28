package net.minecraftforge.fml.common.network;

import com.google.common.collect.ImmutableSet;
import net.minecraft.network.NetworkManager;
import net.minecraftforge.fml.common.eventhandler.Event;
import net.minecraftforge.fml.relauncher.Side;

/** Compile-only Forge API with the runtime-mapped Minecraft type. */
public class FMLNetworkEvent<T> extends Event {
    public NetworkManager getManager() { return null; }

    public static class CustomPacketRegistrationEvent<T> extends FMLNetworkEvent<T> {
        public ImmutableSet<String> getRegistrations() { return null; }
        public String getOperation() { return null; }
        public Side getSide() { return null; }
    }
}
