package invtweaks.container;

import net.minecraft.item.ItemStack;

/** Compile-only ABI for the Inventory Tweaks section being sorted. */
public class ContainerSectionManager {
    public ItemStack getItemStack(int index) {
        throw new UnsupportedOperationException("ABI only");
    }

    public boolean move(int source, int destination) {
        throw new UnsupportedOperationException("ABI only");
    }
}
