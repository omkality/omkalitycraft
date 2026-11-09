package net.omkality.client.mixin;

import java.util.concurrent.Callable;
import net.omkality.client.ClientNetworkTasks;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

@Mixin(targets="net.minecraft.client.Minecraft", remap=false)
public abstract class MinecraftTaskMixin {
    @ModifyVariable(method="func_152343_a(Ljava/util/concurrent/Callable;)Lcom/google/common/util/concurrent/ListenableFuture;",
        at=@At("HEAD"), argsOnly=true, ordinal=0, require=1, remap=false)
    private Callable<?> omkality$guardOriginatingConnection(Callable<?> task) {
        return ClientNetworkTasks.wrap(task);
    }
}
