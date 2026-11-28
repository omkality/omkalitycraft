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
    public static class KeyboardInputEvent extends GuiScreenEvent {
        public static class Pre extends KeyboardInputEvent {}
    }
    public static class ActionPerformedEvent extends GuiScreenEvent {
        public static class Pre extends ActionPerformedEvent {}
        public net.minecraft.client.gui.GuiButton getButton() { throw new UnsupportedOperationException("ABI only"); }
    }
}
