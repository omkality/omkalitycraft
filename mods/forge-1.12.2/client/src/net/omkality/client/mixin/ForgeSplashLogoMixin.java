package net.omkality.client.mixin;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.Constant;
import org.spongepowered.asm.mixin.injection.ModifyConstant;

/** Opt-in cosmetic resource selector; no change to the splash thread lifecycle. */
@Mixin(targets="net.minecraftforge.fml.client.SplashProgress", remap=false)
public abstract class ForgeSplashLogoMixin {
    @ModifyConstant(method="start", constant=@Constant(stringValue="textures/gui/title/mojang.png"),
        require=1, remap=false)
    private static String omkality$projectLogo(String original) {
        return "omkalityclient:appearance/loading.png";
    }
}
