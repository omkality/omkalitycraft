package net.omkality.client.bootstrap;

import java.util.Collections;
import java.util.List;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.Side;
import zone.rong.mixinbooter.ILateMixinLoader;

/** Load the optional Inventory Tweaks integration after ordinary mod discovery. */
public final class ChestSortMixinLoader implements ILateMixinLoader {
    @Override
    public List<String> getMixinConfigs() {
        return FMLLaunchHandler.side() == Side.CLIENT
            ? Collections.singletonList("mixins.omkalityclient.chestsort.json")
            : Collections.emptyList();
    }
}
