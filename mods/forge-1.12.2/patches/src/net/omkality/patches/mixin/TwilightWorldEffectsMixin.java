package net.omkality.patches.mixin;

import java.util.Random;
import net.omkality.patches.TwilightWorldEffectGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;

/** Native selection remains unchanged; denied candidates cannot mutate a world. */
@Mixin(targets="twilightforest.block.BlockTFMagicLogSpecial",remap=false)
public abstract class TwilightWorldEffectsMixin {
    @Coerce
    @Redirect(method="doTreeOfTimeEffect",at=@At(value="INVOKE",
        target="Ltwilightforest/util/WorldUtil;randomOffset(Ljava/util/Random;Lnet/minecraft/util/math/BlockPos;I)Lnet/minecraft/util/math/BlockPos;",remap=false),require=1,remap=false)
    private Object omkality$filterTicks(Random random,@Coerce Object pos,int range,
            @Coerce Object world,@Coerce Object origin,Random originalRandom) throws Exception {
        return TwilightWorldEffectGuard.offset(random,pos,range,world,origin);
    }
    @Coerce
    @Redirect(method="doTreeOfTransformationEffect",at=@At(value="INVOKE",
        target="Ltwilightforest/util/WorldUtil;randomOffset(Ljava/util/Random;Lnet/minecraft/util/math/BlockPos;III)Lnet/minecraft/util/math/BlockPos;",remap=false),require=1,remap=false)
    private Object omkality$filterBiomes(Random random,@Coerce Object pos,int rx,int ry,int rz,
            @Coerce Object world,@Coerce Object origin,Random originalRandom) throws Exception {
        return TwilightWorldEffectGuard.offset(random,pos,rx,ry,rz,world,origin);
    }
}
