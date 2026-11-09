package net.omkality.client.mixin;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

/** Forge tints the central logo with its background color. Keep its own colors. */
@Mixin(targets="net.minecraftforge.fml.client.SplashProgress$2", remap=false)
public abstract class ForgeSplashTintMixin {
    @ModifyArg(method="run", at=@At(value="INVOKE",
        target="Lnet/minecraftforge/fml/client/SplashProgress$2;setColor(I)V"),
        index=0, require=1, remap=false)
    private int omkality$neutralLogoTint(int backgroundColor) {
        return 0xFFFFFF;
    }
}
