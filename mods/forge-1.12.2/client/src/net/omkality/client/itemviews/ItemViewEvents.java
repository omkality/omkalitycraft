package net.omkality.client.itemviews;

import net.minecraft.client.gui.GuiScreenBook;
import net.minecraftforge.client.event.GuiScreenEvent;
import net.minecraftforge.event.entity.player.ItemTooltipEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.relauncher.Side;

@Mod.EventBusSubscriber(modid="omkalityclient",value=Side.CLIENT)
public final class ItemViewEvents {
    private ItemViewEvents() {}
    @SubscribeEvent(priority=EventPriority.LOWEST)
    public static void tooltip(ItemTooltipEvent event) {
        ItemViewRuntime.tooltip(event.getItemStack(),event.getToolTip());
    }
    @SubscribeEvent
    public static void init(GuiScreenEvent.InitGuiEvent.Post event) {
        if(event.getGui() instanceof GuiScreenBook)ItemViewRuntime.book((GuiScreenBook)event.getGui());
    }
}
