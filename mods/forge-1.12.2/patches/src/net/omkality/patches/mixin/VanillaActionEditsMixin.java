package net.omkality.patches.mixin;

import net.omkality.patches.ActionDispatch;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Coerce;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.Slice;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(targets = "net.minecraft.network.NetHandlerPlayServer", remap = false)
public abstract class VanillaActionEditsMixin {
    private static final String CUSTOM_PAYLOAD =
        "func_147349_a(Lnet/minecraft/network/play/client/CPacketCustomPayload;)V";

    @Inject(method = "func_147343_a(Lnet/minecraft/network/play/client/CPacketUpdateSign;)V",
        at = @At(value = "INVOKE", target = "Lnet/minecraft/tileentity/TileEntitySign;func_70296_d()V",
            shift = At.Shift.AFTER), require = 1, allow = 1, remap = false)
    private void omkality$signSaved(@Coerce Object packet, CallbackInfo callback) {
        ActionDispatch.sign(this, packet);
    }

    @Inject(method = CUSTOM_PAYLOAD, slice = @Slice(
        from = @At(value = "CONSTANT", args = "stringValue=MC|BEdit"),
        to = @At(value = "CONSTANT", args = "stringValue=MC|BSign")),
        at = @At(value = "INVOKE", target = "Lnet/minecraft/item/ItemStack;"
            + "func_77983_a(Ljava/lang/String;Lnet/minecraft/nbt/NBTBase;)V", shift = At.Shift.AFTER),
        require = 1, allow = 1, remap = false)
    private void omkality$bookSaved(@Coerce Object packet, CallbackInfo callback) {
        ActionDispatch.book(this, "book_edit");
    }

    @Inject(method = CUSTOM_PAYLOAD, at = @At(value = "INVOKE",
        target = "Lnet/minecraft/entity/player/EntityPlayerMP;func_184201_a"
            + "(Lnet/minecraft/inventory/EntityEquipmentSlot;Lnet/minecraft/item/ItemStack;)V",
        shift = At.Shift.AFTER), require = 1, allow = 1, remap = false)
    private void omkality$bookSigned(@Coerce Object packet, CallbackInfo callback) {
        ActionDispatch.book(this, "book_sign");
    }
}
