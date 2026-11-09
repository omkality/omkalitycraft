package net.omkality.client.bootstrap;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.IFMLLoadingPlugin;
import net.minecraftforge.fml.relauncher.Side;
import zone.rong.mixinbooter.IEarlyMixinLoader;

@IFMLLoadingPlugin.Name("OmkalityClient")
@IFMLLoadingPlugin.MCVersion("1.12.2")
@IFMLLoadingPlugin.SortingIndex(1001)
@IFMLLoadingPlugin.TransformerExclusions({"net.omkality.client.bootstrap"})
public final class OmkalityClientLoader implements IFMLLoadingPlugin, IEarlyMixinLoader {
    @Override public List<String> getMixinConfigs() {
        if (FMLLaunchHandler.side() != Side.CLIENT) return Collections.emptyList();
        verifyMinecraft();
        if (Boolean.getBoolean("omkality.appearance.forge112")) {
            return Arrays.asList("mixins.omkalityclient.network.json", "mixins.omkalityclient.appearance.json");
        }
        return Collections.singletonList("mixins.omkalityclient.network.json");
    }

    private static void verifyMinecraft() {
        // GameRunner always sets cwd to the portable instance, on every OS.
        Path path = Paths.get("versions", "1.12.2", "1.12.2.jar");
        try {
            if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.size(path) > 64L * 1024L * 1024L) {
                throw new IllegalArgumentException("Missing or oversized reviewed Minecraft client");
            }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream stream = Files.newInputStream(path)) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = stream.read(buffer)) != -1) digest.update(buffer, 0, count);
            }
            StringBuilder hex = new StringBuilder();
            for (byte value : digest.digest()) hex.append(String.format("%02x", value & 255));
            if (!hex.toString().equals("8ada07da5ee77dad3527bd7278fbd05ee1fc8a597813b216a871a2d7d64cc64f")) {
                throw new IllegalArgumentException("Unreviewed Minecraft client artifact");
            }
        } catch (Exception error) { throw new IllegalStateException("Omkality client network guard input check failed", error); }
    }

    @Override public String[] getASMTransformerClass() { return new String[0]; }
    @Override public String getModContainerClass() { return null; }
    @Override public String getSetupClass() { return null; }
    @Override public void injectData(Map<String, Object> data) {}
    @Override public String getAccessTransformerClass() { return null; }
}
