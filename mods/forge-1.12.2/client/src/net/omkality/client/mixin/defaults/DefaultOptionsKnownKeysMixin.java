package net.omkality.client.mixin.defaults;

import java.util.List;
import java.util.Set;
import net.omkality.client.defaults.KnownKeySnapshot;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.Redirect;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** DefaultOptions 9.2.8: do not mark unsaved bindings as permanently initialized. */
@Pseudo
@Mixin(targets="net.blay09.mods.defaultoptions.DefaultOptions", remap=false)
public abstract class DefaultOptionsKnownKeysMixin {
    @Unique private Set<String> omkality$saved;

    @Inject(method="reloadDefaultMappings()V", at=@At("HEAD"), require=1, remap=false)
    private void omkality$snapshot(CallbackInfo ci) {
        omkality$saved = KnownKeySnapshot.current();
    }

    @Redirect(method="reloadDefaultMappings()V",
        at=@At(value="INVOKE", target="Ljava/util/List;add(Ljava/lang/Object;)Z"),
        require=2, allow=2, remap=false)
    private boolean omkality$record(List<Object> keys, Object key) {
        return KnownKeySnapshot.record(keys, key, omkality$saved);
    }

    @Inject(method="reloadDefaultMappings()V", at=@At("RETURN"), require=1, remap=false)
    private void omkality$clear(CallbackInfo ci) {
        omkality$saved = null;
    }
}
