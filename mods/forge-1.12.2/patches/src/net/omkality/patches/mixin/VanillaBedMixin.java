package net.omkality.patches.mixin;

import net.omkality.patches.VanillaBedGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;

@Mixin(targets="net.minecraft.item.ItemBed",remap=false)
public abstract class VanillaBedMixin {
    @Redirect(method="func_180614_a",at=@At(value="INVOKE",
        target="Lnet/minecraft/entity/player/EntityPlayer;func_175151_a(Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/util/EnumFacing;Lnet/minecraft/item/ItemStack;)Z",remap=false),
        require=2,allow=2,remap=false)
    private boolean omkality$edit(@Coerce Object actor,@Coerce Object position,@Coerce Object face,
            @Coerce Object stack) throws Exception {
        return VanillaBedGuard.permits(actor,position,face,stack);
    }
}
