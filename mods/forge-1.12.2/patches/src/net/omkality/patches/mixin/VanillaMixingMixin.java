package net.omkality.patches.mixin;

import net.omkality.patches.VanillaBoundaryGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;

@Mixin(targets="net.minecraft.block.BlockLiquid",remap=false)
public abstract class VanillaMixingMixin {
    @Coerce
    @Redirect(method="func_176365_e",at=@At(value="INVOKE",target="Lnet/minecraft/world/World;func_180495_p(Lnet/minecraft/util/math/BlockPos;)Lnet/minecraft/block/state/IBlockState;",remap=false),require=1,remap=false)
    private Object omkality$mix(@Coerce Object world,@Coerce Object neighbor,@Coerce Object callerWorld,
            @Coerce Object origin,@Coerce Object originalState) throws Exception {
        if(world!=callerWorld) throw new IllegalStateException("Unexpected mixing world identity");
        return VanillaBoundaryGuard.mixingNeighbor(world,neighbor,origin);
    }
}
