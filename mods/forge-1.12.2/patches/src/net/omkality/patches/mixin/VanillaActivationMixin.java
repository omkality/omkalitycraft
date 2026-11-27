package net.omkality.patches.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import net.omkality.patches.ActionDispatch;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Coerce;

@Mixin(targets = "net.minecraft.server.management.PlayerInteractionManager", remap = false)
public abstract class VanillaActivationMixin {
    @WrapOperation(method = "func_187251_a", at = @At(value = "INVOKE",
        target = "Lnet/minecraft/block/Block;func_180639_a(Lnet/minecraft/world/World;"
            + "Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/state/IBlockState;"
            + "Lnet/minecraft/entity/player/EntityPlayer;Lnet/minecraft/util/EnumHand;"
            + "Lnet/minecraft/util/EnumFacing;FFF)Z"), require = 1, allow = 1, remap = false)
    private boolean omkality$observeActivation(@Coerce Object block, @Coerce Object world, @Coerce Object pos,
            @Coerce Object state, @Coerce Object player, @Coerce Object hand, @Coerce Object face,
            float x, float y, float z, Operation<Boolean> activate) {
        boolean used = activate.call(block, world, pos, state, player, hand, face, x, y, z);
        if (used) ActionDispatch.activation(player, world, pos, state);
        return used;
    }
}
