package net.omkality.patches.mixin;

import java.util.Random;
import net.omkality.patches.TwilightSortingGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Coerce;
import org.spongepowered.asm.mixin.injection.Redirect;

/** Filter inventory candidates before native item counting, moving and merging. */
@Mixin(targets="twilightforest.block.BlockTFMagicLogSpecial", remap=false)
public abstract class TwilightSortingMixin {
    @Coerce
    @Redirect(method="doSortingTreeEffect", at=@At(value="INVOKE",
        target="Lnet/minecraft/block/BlockChest;func_189418_a(Lnet/minecraft/world/World;Lnet/minecraft/util/math/BlockPos;Z)Lnet/minecraft/world/ILockableContainer;",
        remap=false), require=1, remap=false)
    private Object omkality$filterSortingInventory(@Coerce Object block, @Coerce Object world,
            @Coerce Object target, boolean allowBlocked, @Coerce Object sourceWorld,
            @Coerce Object origin, Random random) {
        return TwilightSortingGuard.inventory(block, world, target, allowBlocked, sourceWorld, origin);
    }
}
