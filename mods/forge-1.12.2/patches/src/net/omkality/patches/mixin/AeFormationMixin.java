package net.omkality.patches.mixin;

import net.omkality.patches.AePlaneGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(targets="appeng.parts.automation.PartFormationPlane",remap=false)
public abstract class AeFormationMixin {
    @Inject(method="injectItems(Lappeng/api/storage/data/IAEItemStack;Lappeng/api/config/Actionable;Lappeng/api/networking/security/IActionSource;)Lappeng/api/storage/data/IAEItemStack;",
        at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private void omkality$beforePlace(@Coerce Object input,@Coerce Object action,@Coerce Object source,CallbackInfoReturnable<Object> result) {
        if(input!=null && !AePlaneGuard.permits(this)) result.setReturnValue(input);
    }
}
