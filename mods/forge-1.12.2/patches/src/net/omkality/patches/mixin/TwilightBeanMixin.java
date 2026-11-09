package net.omkality.patches.mixin;

import net.omkality.patches.TwilightBeanGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;

@Mixin(targets="twilightforest.item.ItemTFMagicBeans",remap=false)
public abstract class TwilightBeanMixin {
    @Redirect(method="func_180614_a",at=@At(value="INVOKE",
        target="Ltwilightforest/item/ItemTFMagicBeans;makeHugeStalk(Lnet/minecraft/world/World;Lnet/minecraft/util/math/BlockPos;II)V",remap=false),require=1,remap=false)
    private void omkality$playerScope(@Coerce Object item,@Coerce Object world,@Coerce Object origin,int min,int max,
        @Coerce Object actor,@Coerce Object callWorld,@Coerce Object callOrigin,@Coerce Object hand,@Coerce Object side,float x,float y,float z) throws Exception {
        TwilightBeanGuard.grow(item,actor,world,origin,min,max);
    }
    @Redirect(method={"tryToPlaceStalk","placeLeaves"},at=@At(value="INVOKE",
        target="Lnet/minecraft/world/World;func_175656_a(Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/state/IBlockState;)Z",remap=false),require=2,remap=false)
    private boolean omkality$write(@Coerce Object world,@Coerce Object position,@Coerce Object state) throws Exception {
        return TwilightBeanGuard.write(world,position,state,null);
    }
    @Redirect(method="tryToPlaceLeaves",at=@At(value="INVOKE",
        target="Lnet/minecraft/world/World;func_180501_a(Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/state/IBlockState;I)Z",remap=false),require=1,remap=false)
    private boolean omkality$writeFlags(@Coerce Object world,@Coerce Object position,@Coerce Object state,int flags) throws Exception {
        return TwilightBeanGuard.write(world,position,state,flags);
    }
}
