package net.omkality.patches.mixin;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.Charset;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import net.omkality.patches.BoundedModLog;
import net.omkality.patches.CraftTweakerLogGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(targets = "youyihj.zenutils.impl.runtime.ZenUtilsFileLogger", remap = false)
public abstract class ZenUtilsFileLogMixin implements CraftTweakerLogGuard.Installed {
    @Redirect(method = "openWriter()V",
        at = @At(value = "INVOKE",
            target = "Ljava/nio/file/Files;newBufferedWriter(Ljava/nio/file/Path;Ljava/nio/charset/Charset;[Ljava/nio/file/OpenOption;)Ljava/io/BufferedWriter;"),
        require = 1, allow = 1)
    private BufferedWriter omkality$boundFileWriter(Path path, Charset encoding, OpenOption[] options)
            throws IOException {
        return new BufferedWriter(new OutputStreamWriter(
            BoundedModLog.openCraftTweaker(path, options), encoding.newEncoder()));
    }
}
