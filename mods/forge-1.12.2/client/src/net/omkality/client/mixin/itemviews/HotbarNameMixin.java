package net.omkality.client.mixin.itemviews;

import net.minecraft.item.ItemStack;
import net.omkality.client.itemviews.ItemViewRuntime;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/** Presentation-only call site; canonical ItemStack naming remains unchanged. */
@Mixin(targets="net.minecraftforge.client.GuiIngameForge",remap=false)
public abstract class HotbarNameMixin {
    @Redirect(method="renderToolHighlight(Lnet/minecraft/client/gui/ScaledResolution;)V",at=@At(value="INVOKE",target="Lnet/minecraft/item/ItemStack;func_82833_r()Ljava/lang/String;"),require=1,allow=1,remap=false)
    private String omkality$name(ItemStack stack) {return ItemViewRuntime.hotbarName(stack);}
}
