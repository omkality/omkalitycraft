/** Compile-only ABI for Forge 2860's runtime remapped resolution type. */
package net.minecraftforge.client.event;

import net.minecraft.client.gui.ScaledResolution;
import net.minecraftforge.fml.common.eventhandler.Event;

public class RenderGameOverlayEvent extends Event {
    public enum ElementType { ALL }
    public static class Post extends RenderGameOverlayEvent {}
    public ElementType getType() { throw new UnsupportedOperationException("ABI only"); }
    public ScaledResolution getResolution() { throw new UnsupportedOperationException("ABI only"); }
}
