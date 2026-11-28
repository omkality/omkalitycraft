/** Compile-only ABI; never included in a runtime JAR. */
package net.minecraft.client;

import net.minecraft.client.audio.SoundHandler;
import net.minecraft.client.entity.EntityPlayerSP;
import net.minecraft.client.gui.FontRenderer;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.network.NetHandlerPlayClient;
import net.minecraft.client.renderer.RenderItem;
import net.minecraft.client.settings.GameSettings;

public class Minecraft {
    public FontRenderer field_71466_p;
    public EntityPlayerSP field_71439_g;
    public GuiScreen field_71462_r;
    public GameSettings field_71474_y;

    public static Minecraft func_71410_x() { throw new UnsupportedOperationException("ABI only"); }
    public SoundHandler func_147118_V() { throw new UnsupportedOperationException("ABI only"); }
    public RenderItem func_175599_af() { throw new UnsupportedOperationException("ABI only"); }
    public NetHandlerPlayClient func_147114_u() { throw new UnsupportedOperationException("ABI only"); }
}
