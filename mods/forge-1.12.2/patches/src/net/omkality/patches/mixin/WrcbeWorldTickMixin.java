package net.omkality.patches.mixin;

import net.omkality.patches.WrcbeShutdownGuard;
import net.minecraftforge.fml.common.gameevent.TickEvent;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Only the already-disposed WR manager's final shutdown START tick is skipped. */
@Mixin(targets = "codechicken.wirelessredstone.handler.WREventHandler", remap = false)
public abstract class WrcbeWorldTickMixin {
    @Inject(method = "worldTick(Lnet/minecraftforge/fml/common/gameevent/TickEvent$WorldTickEvent;)V",
            at = @At("HEAD"), cancellable = true, require = 1, remap = false)
    private void omkality$skipDisposedShutdownTick(TickEvent.WorldTickEvent event, CallbackInfo callback) {
        if (WrcbeShutdownGuard.shouldSkip(event)) callback.cancel();
    }
}
