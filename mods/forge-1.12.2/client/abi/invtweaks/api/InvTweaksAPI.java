/** Compile-only ABI for Inventory Tweaks. */
package invtweaks.api;

import invtweaks.api.container.ContainerSection;

public interface InvTweaksAPI {
    void sort(ContainerSection section, SortingMethod method);
}
