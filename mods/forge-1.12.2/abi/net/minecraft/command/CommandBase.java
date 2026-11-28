/** Compile-only ABI; never included in a runtime JAR. */
package net.minecraft.command;

import net.minecraft.server.MinecraftServer;

public abstract class CommandBase implements ICommand {
    public abstract String func_71517_b();
    public abstract String func_71518_a(ICommandSender sender);
    public abstract void func_184881_a(MinecraftServer server, ICommandSender sender, String[] args);
    public boolean func_184882_a(MinecraftServer server, ICommandSender sender) {
        throw new UnsupportedOperationException("ABI only");
    }
}
