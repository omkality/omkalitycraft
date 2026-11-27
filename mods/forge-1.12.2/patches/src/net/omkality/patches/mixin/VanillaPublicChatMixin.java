package net.omkality.patches.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import net.minecraft.network.NetHandlerPlayServer;
import net.minecraft.network.play.client.CPacketChatMessage;
import net.minecraft.server.management.PlayerList;
import net.minecraft.util.text.ITextComponent;
import net.omkality.patches.ChatDispatch;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Coerce;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(targets = "net.minecraft.network.NetHandlerPlayServer", remap = false)
public abstract class VanillaPublicChatMixin {
    @WrapOperation(method = "func_147354_a(Lnet/minecraft/network/play/client/CPacketChatMessage;)V",
        at = @At(value = "INVOKE", target = "Lnet/minecraftforge/common/ForgeHooks;onServerChatEvent"
            + "(Lnet/minecraft/network/NetHandlerPlayServer;Ljava/lang/String;Lnet/minecraft/util/text/ITextComponent;)"
            + "Lnet/minecraft/util/text/ITextComponent;"), require = 1, allow = 1, remap = false)
    private ITextComponent omkality$observeForgeChat(NetHandlerPlayServer network, String text,
            ITextComponent original, Operation<ITextComponent> dispatch, CPacketChatMessage packet) {
        ITextComponent result = dispatch.call(network, text, original);
        if (result == null) ChatDispatch.publicRejected(network, packet);
        return result;
    }

    @WrapOperation(method = "func_147354_a(Lnet/minecraft/network/play/client/CPacketChatMessage;)V",
        at = @At(value = "INVOKE", target = "Lnet/minecraft/server/management/PlayerList;"
            + "func_148544_a(Lnet/minecraft/util/text/ITextComponent;Z)V"),
        require = 1, allow = 1, remap = false)
    private void omkality$scopePublicDispatch(PlayerList players, ITextComponent component, boolean system,
            Operation<Void> dispatch, CPacketChatMessage packet) {
        ChatDispatch.enterPublic(this, packet);
        boolean completed = false;
        try {
            dispatch.call(players, component, system);
            completed = true;
        } finally {
            ChatDispatch.leaveDispatch(completed);
        }
    }

    @Inject(method = "func_147359_a(Lnet/minecraft/network/Packet;)V",
        at = @At(value = "INVOKE", target = "Lnet/minecraft/network/NetworkManager;"
            + "func_179290_a(Lnet/minecraft/network/Packet;)V", shift = At.Shift.AFTER),
        require = 1, allow = 1, remap = false)
    private void omkality$observeChatPacket(@Coerce Object packet, CallbackInfo callback) {
        ChatDispatch.packetSent(this, packet);
    }
}
