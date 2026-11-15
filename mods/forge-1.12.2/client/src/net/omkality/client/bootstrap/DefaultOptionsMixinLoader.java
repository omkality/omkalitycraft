package net.omkality.client.bootstrap;

import java.util.Collections;
import java.util.List;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.Side;
import zone.rong.mixinbooter.ILateMixinLoader;

/** Optional compatibility for the reviewed legacy DefaultOptions target. */
public final class DefaultOptionsMixinLoader implements ILateMixinLoader {
    @Override public List<String> getMixinConfigs() {
        return FMLLaunchHandler.side() == Side.CLIENT
            && Boolean.getBoolean("omkality.defaults.persist.forge112")
            ? Collections.singletonList("mixins.omkalityclient.defaults.json")
            : Collections.<String>emptyList();
    }
}
