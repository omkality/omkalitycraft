package net.omkality.patches.mixin;

import net.omkality.patches.DisconnectContainerGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Coerce;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(targets="mod.acgaming.universaltweaks.bugfixes.entities.disconnectdupe.UTDisconnectDupe",remap=false)
public abstract class UniversalDisconnectDupeMixin implements DisconnectContainerGuard.DropInstalled {
    @Inject(method="utDisconnectDupe(Lnet/minecraftforge/event/entity/item/ItemTossEvent;)V",
        at=@At("HEAD"),cancellable=true,require=1,allow=1,remap=false)
    private static void omkality$allowNativeFinalization(@Coerce Object event,CallbackInfo callback) {
        // Skip this one handler, never clear cancellation from another mod.
        if(DisconnectContainerGuard.permitsNativeDrop(event))callback.cancel();
    }
}
