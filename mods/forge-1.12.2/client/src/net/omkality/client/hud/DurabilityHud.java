package net.omkality.client.hud;

import net.minecraft.client.Minecraft;
import net.minecraft.client.entity.EntityPlayerSP;
import net.minecraft.client.gui.FontRenderer;
import net.minecraft.client.gui.ScaledResolution;
import net.minecraft.inventory.EntityEquipmentSlot;
import net.minecraft.item.ItemStack;
import net.minecraftforge.client.event.RenderGameOverlayEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.relauncher.Side;

/** Show remaining durability of the currently equipped gear beside the hotbar. */
@Mod.EventBusSubscriber(modid = "omkalityclient", value = Side.CLIENT)
public final class DurabilityHud {
    private static final EntityEquipmentSlot[] SLOTS = {
        EntityEquipmentSlot.HEAD, EntityEquipmentSlot.CHEST, EntityEquipmentSlot.LEGS,
        EntityEquipmentSlot.FEET, EntityEquipmentSlot.MAINHAND, EntityEquipmentSlot.OFFHAND
    };
    private static final int EDGE = 6;
    private static final int ROW_HEIGHT = 18;
    private static final int TEXT_OFFSET = 20;

    @SubscribeEvent
    public static void draw(RenderGameOverlayEvent.Post event) {
        if (event.getType() != RenderGameOverlayEvent.ElementType.ALL) {
            return;
        }
        Minecraft game = Minecraft.func_71410_x();
        EntityPlayerSP player = game.field_71439_g;
        if (player == null || player.func_175149_v() || game.field_71462_r != null
            || game.field_71474_y.field_74319_N || game.field_71474_y.field_74330_P) {
            return;
        }
        ItemStack[] equipment = new ItemStack[SLOTS.length];
        String[] labels = new String[SLOTS.length];
        int[] colors = new int[SLOTS.length];
        FontRenderer font = game.field_71466_p;
        int count = 0;
        int width = 0;
        for (EntityEquipmentSlot slot : SLOTS) {
            ItemStack stack = player.func_184582_a(slot);
            if (stack.func_190926_b() || !stack.func_77984_f()) {
                continue;
            }
            int maximum = stack.func_77958_k();
            if (maximum <= 0) {
                continue;
            }
            int remaining = Math.max(0, Math.min(maximum, maximum - stack.func_77952_i()));
            String label = remaining + "/" + maximum;
            equipment[count] = stack;
            labels[count] = label;
            colors[count] = remaining * 5L <= maximum ? 0xff7777
                : remaining * 2L <= maximum ? 0xffd271 : 0xf1f5f9;
            width = Math.max(width, font.func_78256_a(label));
            count++;
        }
        ScaledResolution area = event.getResolution();
        int x = area.func_78326_a() - EDGE - width - TEXT_OFFSET;
        int bottom = x >= area.func_78326_a() / 2 + 96 ? 24 : 46;
        int y = area.func_78328_b() - bottom - count * ROW_HEIGHT;
        for (int row = 0; row < count; row++) {
            game.func_175599_af().func_180450_b(equipment[row], x, y);
            font.func_175063_a(labels[row], x + TEXT_OFFSET, y + 4, colors[row]);
            y += ROW_HEIGHT;
        }
    }

    private DurabilityHud() {}
}
