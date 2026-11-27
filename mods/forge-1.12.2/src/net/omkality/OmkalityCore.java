package net.omkality;

import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Properties;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.event.FMLPreInitializationEvent;
import net.minecraftforge.fml.common.event.FMLServerStartedEvent;
import net.minecraftforge.fml.common.event.FMLServerStoppingEvent;
import net.minecraftforge.fml.common.event.FMLServerStoppedEvent;
import net.minecraftforge.fml.common.event.FMLPostInitializationEvent;
import net.omkality.api.CoreServices;
import net.minecraftforge.fml.common.network.NetworkCheckHandler;
import net.minecraftforge.fml.relauncher.Side;

/** Server-side policy over the declared FML mod list; not proof of client integrity. */
@Mod(modid = "omkalitycore", name = "Omkality Core", version = "0.3.18", dependencies = "after:ftbutilities;after:justenoughdimensions",
     acceptedMinecraftVersions = "[1.12.2]", serverSideOnly = true,
     acceptableRemoteVersions = "*")
public final class OmkalityCore {
    public static final String VERSION = "0.3.18";
    private volatile ClientModPolicy expected;
    private org.apache.logging.log4j.Logger logger;
    private Path configDirectory;
    private ServerProfile profile;

    @Mod.EventHandler
    public void ready(FMLPostInitializationEvent event) {
        CoreServices.requireExtensions(profile.extensions);
    }

    @Mod.EventHandler
    public void started(FMLServerStartedEvent event) {
        try { RecoveryConnections.install(logger); }
        catch (Exception error) { throw new IllegalStateException("Account recovery connection adapter could not initialize", error); }
        CoreServices.report("core.connections",RecoveryConnections.state);
        try {
            CoreServices.prepare(logger);
            OptionalIntegrations.install(configDirectory,logger);
            CoreServices.start(logger);
            MaintenanceBridge.install(logger);
            OwnerModeration.install(configDirectory,logger);
            GameMetrics.install(logger,profile.id);
            ChatHistory.install(logger,profile);
            ActionHistory.install(logger,profile);
            WelcomeChat.install(configDirectory,logger);
            CoreServices.requireCapabilities(profile.capabilities);
        } catch(Exception error) { throw new IllegalStateException("Omkality server profile could not initialize",error); }
        if (Boolean.getBoolean("omkality.lab.commandCatalog")) {
            try { CommandCatalog.write(profile); }
            catch (Exception error) { throw new IllegalStateException("Lab command catalog export failed", error); }
        }
    }

    @Mod.EventHandler
    public void stopping(FMLServerStoppingEvent event) { WelcomeChat.stop(); GameMetrics.stop(); ChatHistory.stop(); ActionHistory.stop(); }

    @Mod.EventHandler
    public void stopped(FMLServerStoppedEvent event) { WelcomeChat.stop(); GameMetrics.stop(); ChatHistory.stop(); ActionHistory.stop(); }

    @Mod.EventHandler
    public void load(FMLPreInitializationEvent event) {
        logger = event.getModLog();
        configDirectory = event.getModConfigurationDirectory().toPath();
        try { profile=ServerProfile.read(configDirectory); }
        catch(Exception error) { throw new IllegalStateException("Invalid Omkality server profile",error); }
        Path path = event.getModConfigurationDirectory().toPath().resolve("omkalitycore-mods.properties");
        try {
            if (!Files.isRegularFile(path) || Files.size(path) > 65536) {
                throw new IllegalArgumentException("Missing or oversized client mod policy");
            }
            Properties values = new Properties();
            try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                values.load(reader);
            }
            ClientModPolicy policy = new ClientModPolicy(values);
            expected = policy;
            event.getModLog().info("Loaded strict client mod policy: {} required, {} optional",
                policy.requiredCount(), policy.optionalCount());
        } catch (Exception error) {
            throw new IllegalStateException("Omkality Core requires a valid explicit client mod policy", error);
        }
    }

    @NetworkCheckHandler
    public boolean accept(Map<String, String> remote, Side remoteSide) {
        ClientModPolicy policy = expected;
        return remoteSide != Side.CLIENT || (policy != null && policy.accepts(remote));
    }
}
