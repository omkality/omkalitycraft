package net.omkality.dj2;

import java.util.Collections;
import java.util.List;
import java.util.Map;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.IFMLLoadingPlugin;
import net.minecraftforge.fml.relauncher.Side;
import zone.rong.mixinbooter.IEarlyMixinLoader;

/** Minecraft blocks load before mod late-mixins; keep this bootstrap free of game types. */
@IFMLLoadingPlugin.MCVersion("1.12.2")
@IFMLLoadingPlugin.TransformerExclusions({"net.omkality.dj2","net.omkality.patches"})
public final class OmkalityEarlyMixinPlugin implements IFMLLoadingPlugin, IEarlyMixinLoader {
    public String[] getASMTransformerClass() { return new String[0]; }
    public String getModContainerClass() { return null; }
    public String getSetupClass() { return null; }
    public void injectData(Map<String,Object> data) { }
    public String getAccessTransformerClass() { return null; }
    public List<String> getMixinConfigs() {
        return FMLLaunchHandler.side()==Side.SERVER
            ? Collections.singletonList("mixins.omkalitydj2fix.vanilla.json")
            : Collections.<String>emptyList();
    }
}
