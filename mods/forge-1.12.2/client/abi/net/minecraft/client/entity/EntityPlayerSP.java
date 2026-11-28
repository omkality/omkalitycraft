/** Compile-only ABI; never included in a runtime JAR. */
package net.minecraft.client.entity;

import net.minecraft.entity.player.InventoryPlayer;
import net.minecraft.inventory.Container;
import net.minecraft.inventory.EntityEquipmentSlot;
import net.minecraft.item.ItemStack;

public class EntityPlayerSP {
    public InventoryPlayer field_71071_by;
    public Container field_71070_bA;
    public ItemStack func_184582_a(EntityEquipmentSlot slot) { throw new UnsupportedOperationException("ABI only"); }
    public boolean func_175149_v() { throw new UnsupportedOperationException("ABI only"); }
    public void func_71165_d(String message) { throw new UnsupportedOperationException("ABI only"); }
}
