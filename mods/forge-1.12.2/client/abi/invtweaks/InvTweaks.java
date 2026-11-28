/** Compile-only ABI for Inventory Tweaks. */
package invtweaks;

import invtweaks.container.IContainerManager;

public class InvTweaks {
    public static IContainerManager getCurrentContainerManager() { throw new UnsupportedOperationException("ABI only"); }
}
