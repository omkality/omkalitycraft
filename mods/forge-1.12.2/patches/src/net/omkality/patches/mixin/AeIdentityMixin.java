package net.omkality.patches.mixin;

import net.omkality.patches.AePlaneGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** PlaneFix overrides the permission method; it does not inherit the AE2 method. */
@Mixin(targets="shadows.PartRealIdentityAnnihilationPlane",remap=false)
public abstract class AeIdentityMixin {
    @Inject(method="canHandleBlock",at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private void omkality$beforeSilkBreak(@Coerce Object world,@Coerce Object target,CallbackInfoReturnable<Boolean> result) {
        if(!AePlaneGuard.permits(this)) result.setReturnValue(false);
    }
}
