package net.omkality.client.mixin.books;

import net.omkality.client.books.BookLocaleText;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.Constant;
import org.spongepowered.asm.mixin.injection.ModifyConstant;

/** Localize prefixes only; the original processor still reads live ritual costs. */
@Pseudo
@Mixin(targets="com.bewitchment.common.integration.patchouli.ProcessorRitual", remap=false)
public abstract class BewitchmentRitualLabelsMixin {
    @ModifyConstant(method="process(Ljava/lang/String;)Ljava/lang/String;",
        constant=@Constant(stringValue="Starting Cost: "),require=1,remap=false)
    private static String omkality$startingCost(String original) {
        String translated = BookLocaleText.label("omkalityclient.books.ritual.starting",original);
        return original.equals(translated) ? original : translated + " ";
    }

    @ModifyConstant(method="process(Ljava/lang/String;)Ljava/lang/String;",
        constant=@Constant(stringValue="Running Cost: "),require=1,remap=false)
    private static String omkality$runningCost(String original) {
        String translated = BookLocaleText.label("omkalityclient.books.ritual.running",original);
        return original.equals(translated) ? original : translated + " ";
    }
}
