package net.omkality.patches.mixin;

import net.omkality.patches.DisconnectContainerGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(targets="net.minecraft.entity.player.EntityPlayerMP",remap=false)
public abstract class VanillaPlayerDisconnectMixin implements DisconnectContainerGuard.Installed {
    @Inject(method="func_71123_m()V",at=@At("HEAD"),require=1,allow=1,remap=false)
    private void omkality$finishTransientSlots(CallbackInfo callback) {
        DisconnectContainerGuard.beforeDisconnect(this);
    }
}
