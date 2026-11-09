package net.omkality.patches.mixin;

import net.omkality.patches.AePlaneGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(targets="appeng.parts.automation.PartAnnihilationPlane",remap=false)
public abstract class AeAnnihilationMixin {
    @Inject(method="canHandleBlock",at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private void omkality$beforeBreak(@Coerce Object world,@Coerce Object target,CallbackInfoReturnable<Boolean> result) {
        if(!AePlaneGuard.permits(this)) result.setReturnValue(false);
    }
}
