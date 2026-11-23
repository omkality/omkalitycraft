package net.omkality.patches.mixin;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** The same FTB return values drive enforcement and the team map display. */
@Mixin(targets = "com.feed_the_beast.ftbutilities.data.FTBUtilitiesTeamData", remap = false)
public abstract class FtbChunkQuotaMixin {
    @Inject(method = "getMaxClaimChunks()I", at = @At("RETURN"), cancellable = true, require = 1)
    private void omkality$capClaims(CallbackInfoReturnable<Integer> result) {
        if (result.getReturnValue() > 100) result.setReturnValue(100);
    }

    @Inject(method = "getMaxChunkloaderChunks()I", at = @At("RETURN"), cancellable = true, require = 1)
    private void omkality$capChunkLoading(CallbackInfoReturnable<Integer> result) {
        if (result.getReturnValue() > 20) result.setReturnValue(20);
    }
}
