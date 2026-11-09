package net.omkality.patches.mixin;

import java.util.Random;
import net.omkality.patches.VanillaBoundaryGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;

@Mixin(targets="net.minecraft.block.BlockDynamicLiquid",remap=false)
public abstract class VanillaLiquidMixin {
    @Redirect(method="func_180650_b",at=@At(value="INVOKE",target="Lnet/minecraft/block/BlockDynamicLiquid;func_176375_a(Lnet/minecraft/world/World;Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/state/IBlockState;I)V",remap=false),require=1,remap=false)
    private void omkality$flow(@Coerce Object receiver,@Coerce Object world,@Coerce Object target,
            @Coerce Object targetState,int level,@Coerce Object callerWorld,@Coerce Object origin,
            @Coerce Object originalState,Random random) throws Exception {
        if(world!=callerWorld) throw new IllegalStateException("Unexpected fluid world identity");
        VanillaBoundaryGuard.flow(receiver,world,target,targetState,level,origin);
    }
    @Redirect(method="func_180650_b",at=@At(value="INVOKE",target="Lnet/minecraft/world/World;func_175656_a(Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/state/IBlockState;)Z",remap=false),require=1,remap=false)
    private boolean omkality$generation(@Coerce Object world,@Coerce Object target,@Coerce Object newState,
            @Coerce Object callerWorld,@Coerce Object origin,@Coerce Object originalState,Random random) throws Exception {
        if(world!=callerWorld) throw new IllegalStateException("Unexpected fluid world identity");
        return VanillaBoundaryGuard.generated(world,target,newState,origin);
    }
}
