package net.omkality.client.crates;

import invtweaks.InvTweaks;
import invtweaks.api.InvTweaksAPI;
import invtweaks.api.SortingMethod;
import invtweaks.api.container.ContainerSection;
import net.minecraft.client.Minecraft;
import net.minecraft.client.entity.EntityPlayerSP;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.gui.inventory.GuiContainer;
import net.minecraftforge.client.event.GuiScreenEvent;
import net.minecraftforge.fml.common.Loader;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.ModContainer;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.relauncher.Side;
import org.lwjgl.input.Keyboard;

/** Route the storage-screen Z shortcut to sorting without invoking Quark's transfer buttons. */
@Mod.EventBusSubscriber(modid = "omkalityclient", value = Side.CLIENT)
public final class StorageSortInput {
    @SubscribeEvent(priority = EventPriority.LOWEST)
    public static void keyboard(GuiScreenEvent.KeyboardInputEvent.Pre event) {
        if (Keyboard.getEventKey() != Keyboard.KEY_Z || !Keyboard.getEventKeyState()
            || !storage(event.getGui())) {
            return;
        }
        event.setCanceled(true);
        if (!Keyboard.isRepeatEvent() && cursorIsEmpty()) {
            ModContainer mod = Loader.instance().getIndexedModList().get("inventorytweaks");
            if (mod.getMod() instanceof InvTweaksAPI) {
                ((InvTweaksAPI) mod.getMod()).sort(ContainerSection.CHEST, SortingMethod.DEFAULT);
            }
        }
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void quarkShortcut(GuiScreenEvent.ActionPerformedEvent.Pre event) {
        if (Keyboard.isKeyDown(Keyboard.KEY_Z)
            && "vazkii.quark.management.client.gui.GuiButtonChest".equals(event.getButton().getClass().getName())
            && storage(event.getGui())) {
            event.setCanceled(true);
        }
    }

    /** Sorting must never place a stack held on the cursor into a free player slot. */
    public static boolean cursorIsEmpty() {
        EntityPlayerSP player = Minecraft.func_71410_x().field_71439_g;
        return player != null && player.field_71071_by.func_70445_o().func_190926_b();
    }

    private static boolean storage(GuiScreen screen) {
        return screen instanceof GuiContainer && Loader.isModLoaded("inventorytweaks")
            && Minecraft.func_71410_x().field_71439_g != null
            && InvTweaks.getCurrentContainerManager().hasSection(ContainerSection.CHEST);
    }

    private StorageSortInput() {}
}
