package net.omkality.client.bootstrap;

import java.util.Collections;
import java.util.List;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.Side;
import zone.rong.mixinbooter.ILateMixinLoader;

/** Optional client-only mod targets; ordinary mod classes are not available early. */
public final class BookLocaleMixinLoader implements ILateMixinLoader {
    @Override public List<String> getMixinConfigs() {
        return FMLLaunchHandler.side() == Side.CLIENT
            && Boolean.getBoolean("omkality.books.locale.forge112")
            ? Collections.singletonList("mixins.omkalityclient.books.json")
            : Collections.<String>emptyList();
    }
}
