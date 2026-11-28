package net.omkality.patches.mixin;

import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.inventory.ContainerWorkbench;
import net.minecraftforge.fml.common.Loader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.ModifyArgs;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import org.spongepowered.asm.mixin.injection.invoke.arg.Args;
import vazkii.quark.management.feature.BetterCraftShifting;

/** Apply Quark's crafting-grid destination to the workbench's hotbar slots. */
@Mixin(targets = "net.minecraft.inventory.ContainerWorkbench", remap = false)
public abstract class WorkbenchHotbarMixin {
    @Unique private static final int GRID_FIRST = 1;
    @Unique private static final int INVENTORY_FIRST = 10;
    @Unique private static final int HOTBAR_FIRST = 37;
    @Unique private static final int HOTBAR_END = 46;
    @Unique private static final String TRANSFER = "func_82846_b"
        + "(Lnet/minecraft/entity/player/EntityPlayer;I)Lnet/minecraft/item/ItemStack;";

    @ModifyArgs(method = TRANSFER, at = @At(value = "INVOKE",
        target = "Lnet/minecraft/inventory/ContainerWorkbench;"
            + "func_75135_a(Lnet/minecraft/item/ItemStack;IIZ)Z", remap = false),
        require = 4, allow = 4, remap = false)
    private void omkality$routeHotbarToGrid(Args args) {
        if ((int) args.get(1) == INVENTORY_FIRST && (int) args.get(2) == HOTBAR_FIRST
            && omkality$craftShiftingEnabled()) {
            args.set(1, GRID_FIRST);
            args.set(2, INVENTORY_FIRST);
        }
    }

    @Inject(method = TRANSFER, at = @At("RETURN"), remap = false)
    private void omkality$syncHotbarShift(EntityPlayer player, int slot,
                                         CallbackInfoReturnable<?> result) {
        if (slot >= HOTBAR_FIRST && slot < HOTBAR_END && player instanceof EntityPlayerMP
            && omkality$craftShiftingEnabled()) {
            // An accepted quick move normally assumes that the client predicted the
            // same slots. The older client can also predict a move with a full grid.
            ((EntityPlayerMP) player).func_71120_a((ContainerWorkbench) (Object) this);
        }
    }

    @Unique
    private boolean omkality$craftShiftingEnabled() {
        return ((Object) this).getClass() == ContainerWorkbench.class
            && Loader.isModLoaded("quark")
            && BetterCraftShifting.getMinInventoryBoundaryCrafting(HOTBAR_FIRST, HOTBAR_END)
                == GRID_FIRST;
    }
}
