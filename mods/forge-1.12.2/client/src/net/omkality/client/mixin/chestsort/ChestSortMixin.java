package net.omkality.client.mixin.chestsort;

import invtweaks.api.SortingMethod;
import invtweaks.container.ContainerSectionManager;
import net.minecraft.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Constant;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.ModifyConstant;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Complete the default Inventory Tweaks sort in one action for chest sections. */
@Pseudo
@Mixin(targets = "invtweaks.InvTweaksHandlerSorting", remap = false)
public abstract class ChestSortMixin {
    @Shadow private ContainerSectionManager containerMgr;
    @Shadow private SortingMethod algorithm;
    @Shadow private int size;

    @Shadow
    private static boolean canMergeStacks(ItemStack from, ItemStack to) {
        throw new AssertionError();
    }

    @Inject(method = "defaultSorting()V", at = @At("HEAD"), remap = false)
    private void omkality$mergePartialStacks(CallbackInfo callback) {
        if (algorithm != SortingMethod.DEFAULT) {
            return;
        }
        // The ordering pass can finish with matching partial stacks in different slots.
        // Merge them using the same slot-click path before choosing their final order.
        for (int to = 0; to < size - 1; to++) {
            ItemStack destination = containerMgr.getItemStack(to);
            if (destination.func_190926_b()) {
                continue;
            }
            for (int from = to + 1; from < size; from++) {
                if (canMergeStacks(containerMgr.getItemStack(from), destination)
                    && containerMgr.move(from, to)) {
                    destination = containerMgr.getItemStack(to);
                }
            }
        }
    }

    @ModifyConstant(method = "defaultSorting()V", constant = @Constant(intValue = 50), remap = false)
    private int omkality$allowLargerSections(int original) {
        // A large section can still have occupied slots awaiting placement on pass 50.
        return algorithm == SortingMethod.DEFAULT ? Math.max(original, size) : original;
    }
}
