package omk.lab.trace;

import java.nio.file.*;
import net.minecraftforge.fml.common.asm.transformers.ItemBlockTransformer;

public final class ReplayItemBlock {
    public static void main(String[] args) throws Exception {
        byte[] raw = Files.readAllBytes(Paths.get(args[0]));
        byte[] deobfuscated = Files.readAllBytes(Paths.get(args[1]));
        boolean failedAsExpected = false;
        try {
            new ItemBlockTransformer().transform("ahb", "net.minecraft.item.ItemBlock", raw);
        } catch (RuntimeException expected) {
            failedAsExpected = expected.getMessage().contains("no holder field declared");
        }
        if (!failedAsExpected) throw new AssertionError("Expected the original no-holder failure on unmapped bytes");
        byte[] output = new ItemBlockTransformer().transform("ahb", "net.minecraft.item.ItemBlock", deobfuscated);
        if (output == null || output.length == 0) throw new AssertionError("Mapped class did not transform");
        System.out.println("{\"raw_input_reproduces_no_holder\":true,\"mapped_input_passes_actual_forge_transformer\":true}");
    }
}
