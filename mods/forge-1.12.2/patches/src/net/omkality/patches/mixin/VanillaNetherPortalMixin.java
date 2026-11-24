package net.omkality.patches.mixin;

import net.omkality.patches.NetherPortalBorder;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Coerce;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(targets = "net.minecraft.world.Teleporter", remap = false)
public abstract class VanillaNetherPortalMixin {
    @Inject(method = "func_180266_a", at = @At("HEAD"), remap = false)
    private void omkality$limitPortalSearch(@Coerce Object entity, float yaw, CallbackInfo info)
            throws ReflectiveOperationException {
        NetherPortalBorder.keepSearchInside(this, entity);
    }
}
