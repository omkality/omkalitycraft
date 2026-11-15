package net.omkality.patches.mixin;

import net.omkality.patches.PlaneOperatorGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Coerce;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** The exact pinned started method only calls PlayerList.addOp for its fake profile. */
@Mixin(targets="shadows.PlaneFix",remap=false)
public abstract class PlaneOperatorMixin {
    @Inject(method="started",at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private void omkality$withoutAutomaticOperator(@Coerce Object event,CallbackInfo result) throws Exception {
        PlaneOperatorGuard.beforeGrant();
        result.cancel();
    }
}
