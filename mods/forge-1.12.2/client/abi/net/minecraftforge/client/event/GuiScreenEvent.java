package net.minecraftforge.client.event;
/** Compile-only deobfuscated ABI. Never included in the runtime JAR. */
public class GuiScreenEvent extends net.minecraftforge.fml.common.eventhandler.Event {
    public net.minecraft.client.gui.GuiScreen getGui(){throw new UnsupportedOperationException("ABI only");}
    public static class InitGuiEvent extends GuiScreenEvent {
        public static class Post extends InitGuiEvent {}
    }
    public static class DrawScreenEvent extends GuiScreenEvent {
        public static class Pre extends DrawScreenEvent {}
    }
}
