package net.omkality;

import java.lang.reflect.InvocationTargetException;
import java.nio.file.Path;
import java.nio.file.Files;
import net.minecraftforge.fml.common.Loader;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** No FTB classes are resolved unless both reviewed FTB mods are installed. */
final class OptionalIntegrations {
    static void install(Path config,Logger log) throws Exception {
        if(!Loader.isModLoaded("ftbutilities") && !Loader.isModLoaded("ftblib")) {
            if(Files.exists(config.resolve("omkalitycore-territories.properties"))||Files.exists(config.resolve("omkalitycore-resource.properties")))throw new IllegalStateException("Configured FTB policy requires reviewed active FTB claims");
            CoreServices.report("ftb.integration","absent");return;
        }
        String utilities=version("ftbutilities"),library=version("ftblib");
        boolean supportedChest=!Loader.isModLoaded("ironchest") || "1.12.2-7.0.67.844".equals(version("ironchest"));
        if(!"5.4.1.131".equals(utilities) || !"5.4.7.2".equals(library) || !supportedChest) {
            if(Files.exists(config.resolve("omkalitycore-territories.properties"))||Files.exists(config.resolve("omkalitycore-resource.properties")))throw new IllegalStateException("Configured FTB policy requires reviewed FTB versions");
            CoreServices.report("ftb.integration","unsupported");
            log.warn("No reviewed Core FTB integration for the installed versions");return;
        }
        try {
            Class.forName("net.omkality.FtbIntegration").getMethod("install",Path.class,Logger.class).invoke(null,config,log);
        } catch(InvocationTargetException error) {
            Throwable cause=error.getCause();
            if(cause instanceof Exception) throw (Exception)cause;
            throw new IllegalStateException("Optional integration initialization failed",cause);
        }
    }
    private static String version(String id) {
        return Loader.isModLoaded(id)?Loader.instance().getIndexedModList().get(id).getVersion():"absent";
    }
}
