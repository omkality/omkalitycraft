package net.omkality.client.mixin;

import net.minecraft.network.INetHandler;
import net.minecraft.network.NetworkManager;
import net.minecraft.network.Packet;
import net.omkality.client.NetworkPacketBridge;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(targets="net.minecraft.network.NetworkManager", remap=false)
public abstract class NetworkManagerScopeMixin {
    @Redirect(method="channelRead0(Lio/netty/channel/ChannelHandlerContext;Lnet/minecraft/network/Packet;)V",
        at=@At(value="INVOKE", target="Lnet/minecraft/network/Packet;func_148833_a(Lnet/minecraft/network/INetHandler;)V"),
        require=1, remap=false)
    private void omkality$dispatchInOriginatingConnection(Packet<?> packet, INetHandler handler) throws Exception {
        NetworkPacketBridge.process((NetworkManager)(Object)this, packet, handler);
    }
}
