package net.omkality.client.mixin.books;

import net.omkality.client.books.BookLocaleText;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Does not modify Book.version or getSubtitle's zero/developer branches. */
@Pseudo
@Mixin(targets="vazkii.patchouli.client.book.BookContents", remap=false)
public abstract class PatchouliEditionMixin {
    @Inject(method="numberToOrdinal(I)Ljava/lang/String;",at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private static void omkality$russianEdition(int version,CallbackInfoReturnable<String> result) {
        String translated=BookLocaleText.ordinal(version);
        if (translated!=null) result.setReturnValue(translated);
    }
}
