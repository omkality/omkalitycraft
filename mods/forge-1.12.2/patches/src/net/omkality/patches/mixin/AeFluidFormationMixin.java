package net.omkality.patches.mixin;

import net.omkality.patches.AePlaneGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(targets="appeng.fluids.parts.PartFluidFormationPlane",remap=false)
public abstract class AeFluidFormationMixin {
    @Inject(method="injectItems(Lappeng/api/storage/data/IAEFluidStack;Lappeng/api/config/Actionable;Lappeng/api/networking/security/IActionSource;)Lappeng/api/storage/data/IAEFluidStack;",
        at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private void omkality$beforePour(@Coerce Object input,@Coerce Object action,@Coerce Object source,CallbackInfoReturnable<Object> result) {
        if(input!=null && !AePlaneGuard.permits(this)) result.setReturnValue(input);
    }
}
