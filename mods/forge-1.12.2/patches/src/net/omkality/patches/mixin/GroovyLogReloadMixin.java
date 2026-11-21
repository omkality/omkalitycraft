package net.omkality.patches.mixin;

import java.io.IOException;
import java.io.OutputStream;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import net.omkality.patches.BoundedModLog;
import net.omkality.patches.GroovyLogReloadGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.ModifyArg;
import org.spongepowered.asm.mixin.injection.Redirect;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(targets = "com.cleanroommc.groovyscript.sandbox.GroovyLogImpl", remap = false)
public abstract class GroovyLogReloadMixin implements GroovyLogReloadGuard.Installed {
    @Unique private Writer omkality$ownedLogWriter;

    @Redirect(method = "setupLog(Ljava/io/File;)Ljava/io/PrintWriter;",
        at = @At(value = "INVOKE",
            target = "Ljava/nio/file/Files;newOutputStream(Ljava/nio/file/Path;[Ljava/nio/file/OpenOption;)Ljava/io/OutputStream;"),
        require = 1, allow = 1, remap = false)
    private OutputStream omkality$boundFile(Path path, OpenOption[] options) throws IOException {
        return BoundedModLog.wrap(path, Files.newOutputStream(path, options));
    }

    // Only the successful file branch uses PrintWriter(Writer, boolean).
    // The IOException fallback uses PrintWriter(System.out) and is never owned.
    @ModifyArg(method = "setupLog(Ljava/io/File;)Ljava/io/PrintWriter;",
        at = @At(value = "INVOKE", target = "Ljava/io/PrintWriter;<init>(Ljava/io/Writer;Z)V", remap = false),
        index = 0, require = 1, allow = 1, remap = false)
    private Writer omkality$rememberFileWriter(Writer writer) {
        omkality$ownedLogWriter = writer;
        return writer;
    }

    @Inject(method = "cleanLog()V", at = @At("HEAD"), require = 1, allow = 1, remap = false)
    private void omkality$closePreviousFileWriter(CallbackInfo callback) {
        Writer previous = omkality$ownedLogWriter;
        omkality$ownedLogWriter = null;
        GroovyLogReloadGuard.closeOwned(previous);
    }
}
