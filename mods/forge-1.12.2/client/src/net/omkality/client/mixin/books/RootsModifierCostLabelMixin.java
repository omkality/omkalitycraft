package net.omkality.client.mixin.books;

import net.omkality.client.books.BookLocaleText;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.Constant;
import org.spongepowered.asm.mixin.injection.ModifyConstant;

/** Keep absent main cost distinct from zero; additional herb costs remain original. */
@Pseudo
@Mixin(targets="epicsquid.roots.integration.patchouli.SpellModifierProcessor", remap=false)
public abstract class RootsModifierCostLabelMixin {
    @ModifyConstant(method="process(Ljava/lang/String;)Ljava/lang/String;",
        constant=@Constant(stringValue="Invalid cost."),require=1,remap=false)
    private static String omkality$missingCost(String original) {
        return BookLocaleText.label("omkalityclient.books.modifier.missing_cost",original);
    }
}
