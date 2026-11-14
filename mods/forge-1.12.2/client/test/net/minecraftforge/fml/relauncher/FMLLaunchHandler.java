package net.minecraftforge.fml.relauncher;

/** Controllable side selection for the late-loader fixture, never packaged. */
public final class FMLLaunchHandler {
    public static Side selected = Side.CLIENT;
    public static Side side() { return selected; }
}
