package vazkii.quark.management.feature;

/** Compile-only API for Quark's configured workbench destination. */
public final class BetterCraftShifting {
    private BetterCraftShifting() {}

    public static native int getMinInventoryBoundaryCrafting(int start, int end);
}
