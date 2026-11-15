package net.omkality.client.bootstrap;

import java.util.Collections;
import java.util.List;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.Side;
import zone.rong.mixinbooter.ILateMixinLoader;

/** Optional appearance integration; absent mod targets are handled by @Pseudo. */
public final class ControlsLocaleMixinLoader implements ILateMixinLoader {
    @Override public List<String> getMixinConfigs() {
        return FMLLaunchHandler.side() == Side.CLIENT
            && Boolean.getBoolean("omkality.appearance.forge112")
            ? Collections.singletonList("mixins.omkalityclient.controls.json")
            : Collections.<String>emptyList();
    }
}
