package net.omkality.dj2;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.Side;
import zone.rong.mixinbooter.ILateMixinLoader;

/** Required, version-pinned server adapters over installed mod behavior. */
public final class OmkalityMixinLoader implements ILateMixinLoader {
    @Override
    public List<String> getMixinConfigs() {
        return FMLLaunchHandler.side() == Side.SERVER
            ? Arrays.asList("mixins.omkalitydj2fix.wrcbe.json", "mixins.omkalitydj2fix.twilight.json", "mixins.omkalitydj2fix.ae2.json", "mixins.omkalitydj2fix.mekanism.json")
            : Collections.<String>emptyList();
    }
}
