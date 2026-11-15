package net.omkality.client.mixin.controls;

import net.omkality.client.books.BookLocaleText;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Existing sort modes and keybinding logic remain in the original mod. */
@Pseudo
@Mixin(targets="io.enderdev.endermodpacktweaks.features.keybinds.EnumSorting",remap=false)
public abstract class ControlSortLabelMixin {
    @Inject(method="getName()Ljava/lang/String;",at=@At("RETURN"),cancellable=true,require=1,remap=false)
    private void omkality$sortLabel(CallbackInfoReturnable<String> result) {
        String original=result.getReturnValue(),key;
        if("Default".equals(original))key="sortnone";
        else if("A->Z".equals(original))key="sortaz";
        else if("Z->A".equals(original))key="sortza";
        else return;
        String translated=BookLocaleText.label("endermodpacktweaks.options."+key,original);
        if(!original.equals(translated))result.setReturnValue(translated);
    }
}
