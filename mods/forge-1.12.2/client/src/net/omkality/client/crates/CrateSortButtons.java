package net.omkality.client.crates;

import java.lang.reflect.Field;
import java.util.List;
import net.minecraftforge.client.event.GuiScreenEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.relauncher.Side;

/** Align the native Inventory Tweaks controls outside the Actually Additions crate grid. */
@Mod.EventBusSubscriber(modid = "omkalityclient", value = Side.CLIENT)
public final class CrateSortButtons {
    private static final String CRATE = "de.ellpeck.actuallyadditions.mod.inventory.gui.GuiGiantChest";
    private static final String SETTINGS = "invtweaks.InvTweaksGuiSettingsButton";
    private static final String SORT = "invtweaks.InvTweaksGuiSortingButton";
    private static final int SETTINGS_ID = 54696386;

    @SubscribeEvent
    public static void align(GuiScreenEvent.DrawScreenEvent.Pre event) {
        Object gui = event.getGui();
        if (!CRATE.equals(gui.getClass().getName())) {
            return;
        }
        try {
            int top = Fields.TOP.getInt(gui);
            int right = Fields.LEFT.getInt(gui) + Fields.WIDTH.getInt(gui);
            // The title sits above the grid. Short screens have room to the
            // right of the player inventory, below the crate's paging arrows.
            int y = top >= 12 ? top - 12 : top + 196;
            for (Object button : (List<?>) Fields.BUTTONS.get(gui)) {
                int id = Fields.ID.getInt(button);
                String type = button.getClass().getName();
                if (id == SETTINGS_ID && SETTINGS.equals(type)) {
                    move(button, right - 17, y);
                } else if (id == SETTINGS_ID + 1 && SORT.equals(type)) {
                    move(button, right - 29, y);
                }
            }
        } catch (IllegalAccessException error) {
            throw new IllegalStateException("Unable to position storage crate sort buttons", error);
        }
    }

    private static void move(Object button, int x, int y) throws IllegalAccessException {
        Fields.X.setInt(button, x);
        Fields.Y.setInt(button, y);
    }

    private static final class Fields {
        private static final String GUI = "net.minecraft.client.gui.";
        private static final String CONTAINER = GUI + "inventory.GuiContainer";
        private static final String BUTTON = GUI + "GuiButton";
        private static final Field LEFT = field(CONTAINER, "field_147003_i");
        private static final Field TOP = field(CONTAINER, "field_147009_r");
        private static final Field WIDTH = field(CONTAINER, "field_146999_f");
        private static final Field BUTTONS = field(GUI + "GuiScreen", "field_146292_n");
        private static final Field ID = field(BUTTON, "field_146127_k");
        private static final Field X = field(BUTTON, "field_146128_h");
        private static final Field Y = field(BUTTON, "field_146129_i");

        private static Field field(String owner, String name) {
            try {
                Field field = Class.forName(owner).getDeclaredField(name);
                field.setAccessible(true);
                return field;
            } catch (ReflectiveOperationException error) {
                throw new IllegalStateException("Unsupported Forge crate layout", error);
            }
        }
    }

    private CrateSortButtons() {}
}
