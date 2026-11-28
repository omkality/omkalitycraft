package net.minecraft.entity.player;

import net.minecraft.inventory.Container;

/** Compile-only ABI for sending the authoritative container contents to a client. */
public abstract class EntityPlayerMP extends EntityPlayer {
    public abstract void func_71120_a(Container container);
}
