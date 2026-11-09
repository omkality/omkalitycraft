package net.omkality.patches.mixin;

import net.omkality.patches.AePlaneGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(targets="appeng.fluids.parts.PartFluidAnnihilationPlane",remap=false)
public abstract class AeFluidAnnihilationMixin {
    @Inject(method="pickupFluid",at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private void omkality$beforeDrain(CallbackInfoReturnable<Object> result) {
        if(!AePlaneGuard.permits(this)) result.setReturnValue(AePlaneGuard.idle());
    }
}
