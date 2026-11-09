package net.omkality.patches.mixin;

import net.omkality.patches.VanillaBoundaryGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(targets="net.minecraft.block.BlockPistonBase",remap=false)
public abstract class VanillaPistonMixin {
    @Inject(method="func_189539_a",at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private void omkality$event(@Coerce Object state,@Coerce Object world,@Coerce Object pos,int id,int param,
            CallbackInfoReturnable<Boolean> cir) {
        if(!VanillaBoundaryGuard.event(this,state,world,pos,id)) cir.setReturnValue(false);
    }
    @Inject(method="func_176319_a",at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private void omkality$head(@Coerce Object world,@Coerce Object pos,@Coerce Object facing,boolean extending,
            CallbackInfoReturnable<Boolean> cir) {
        if(!VanillaBoundaryGuard.beginMove(world,pos,facing)) cir.setReturnValue(false);
    }
    @Redirect(method="func_176319_a",at=@At(value="INVOKE",target="Lnet/minecraft/block/state/BlockPistonStructureHelper;func_177253_a()Z",remap=false),require=1,remap=false)
    private boolean omkality$movement(@Coerce Object helper,@Coerce Object world,@Coerce Object pos,
            @Coerce Object facing,boolean extending) throws Exception {
        return VanillaBoundaryGuard.move(helper,world,pos,facing,extending);
    }
}
