package net.omkality.patches.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import java.util.Map;
import net.minecraft.command.ICommand;
import net.minecraft.command.ICommandSender;
import net.minecraft.server.MinecraftServer;
import net.minecraftforge.fml.common.eventhandler.Event;
import net.minecraftforge.fml.common.eventhandler.EventBus;
import net.omkality.patches.ChatDispatch;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Coerce;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(targets = "net.minecraft.command.CommandHandler", remap = false)
public abstract class VanillaChatCommandsMixin {
    @Shadow public abstract Map<String, ?> func_71555_a();

    @WrapOperation(method = "func_175786_a(Lnet/minecraft/command/ICommandSender;[Ljava/lang/String;"
            + "Lnet/minecraft/command/ICommand;Ljava/lang/String;)Z",
        at = @At(value = "INVOKE", target = "Lnet/minecraft/command/ICommand;"
            + "func_184881_a(Lnet/minecraft/server/MinecraftServer;Lnet/minecraft/command/ICommandSender;[Ljava/lang/String;)V"),
        require = 1, allow = 1, remap = false)
    private void omkality$scopeCommand(ICommand command, MinecraftServer server, ICommandSender sender,
            String[] arguments, Operation<Void> dispatch) {
        ChatDispatch.enterCommand(command, sender, arguments);
        boolean completed = false;
        try {
            dispatch.call(command, server, sender, arguments);
            completed = true;
        } finally {
            ChatDispatch.leaveDispatch(completed);
        }
    }

    @WrapOperation(method = "func_71556_a(Lnet/minecraft/command/ICommandSender;Ljava/lang/String;)I",
        at = @At(value = "INVOKE", target = "Lnet/minecraftforge/fml/common/eventhandler/EventBus;"
            + "post(Lnet/minecraftforge/fml/common/eventhandler/Event;)Z"), require = 1, allow = 1, remap = false)
    private boolean omkality$observeCommandEvent(EventBus bus, Event event, Operation<Boolean> dispatch) {
        boolean cancelled = dispatch.call(bus, event);
        if (cancelled) ChatDispatch.commandCancelled(event);
        return cancelled;
    }

    @Inject(method = "func_71556_a(Lnet/minecraft/command/ICommandSender;Ljava/lang/String;)I",
        at = @At("RETURN"), require = 1, remap = false)
    private void omkality$observeCommandFailure(@Coerce Object sender, String line,
            CallbackInfoReturnable<Integer> callback) {
        if (callback.getReturnValue() == 0) ChatDispatch.commandRejected(sender, line, func_71555_a());
    }
}
