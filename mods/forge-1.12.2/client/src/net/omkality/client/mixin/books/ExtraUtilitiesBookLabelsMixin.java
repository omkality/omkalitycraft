package net.omkality.client.mixin.books;

import net.omkality.client.books.BookLocaleText;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.Constant;
import org.spongepowered.asm.mixin.injection.ModifyConstant;

/** Optional mod target. Original pagination, body, author and item stay intact. */
@Pseudo
@Mixin(targets="com.rwtema.extrautils2.book.BookHandler", remap=false)
public abstract class ExtraUtilitiesBookLabelsMixin {
    @ModifyConstant(method="newStack()Lnet/minecraft/item/ItemStack;",
        constant=@Constant(stringValue="Extra Utilities 2\nManual\n(temp GUI stand in)"),require=1,remap=false)
    private static String omkality$cover(String original) {
        return BookLocaleText.label("omkalityclient.books.xu2.cover",original);
    }
    @ModifyConstant(method="newStack()Lnet/minecraft/item/ItemStack;",
        constant=@Constant(stringValue="Table of Contents\n\n"),require=1,remap=false)
    private static String omkality$contents(String original) {
        return BookLocaleText.label("omkalityclient.books.xu2.contents",original);
    }
}
