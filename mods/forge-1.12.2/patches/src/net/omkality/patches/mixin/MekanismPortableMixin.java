package net.omkality.patches.mixin;

import net.omkality.patches.MekanismPortableGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(targets="mekanism.common.network.PacketPortableTeleporter",remap=false)
public abstract class MekanismPortableMixin {
    // Validate inside the scheduled server task, not on Netty's receiving thread.
    @Inject(method="lambda$onMessage$0(Lnet/minecraft/entity/player/EntityPlayer;Lmekanism/common/network/PacketPortableTeleporter$PortableTeleporterMessage;)V",
        at=@At("HEAD"),cancellable=true,require=1,remap=false)
    private void omkality$beforePortable(@Coerce Object player,@Coerce Object message,CallbackInfo result) {
        if(!MekanismPortableGuard.permits(player,message)) result.cancel();
    }
}
