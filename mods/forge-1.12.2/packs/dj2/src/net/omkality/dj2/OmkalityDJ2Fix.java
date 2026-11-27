package net.omkality.dj2;

import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.event.FMLPreInitializationEvent;
import net.minecraftforge.fml.common.event.FMLServerStoppingEvent;
import net.minecraftforge.fml.common.event.FMLServerStoppedEvent;
import net.omkality.api.CoreServices;
import net.omkality.api.ServerExtension;
import net.omkality.patches.*;
import org.apache.logging.log4j.Logger;

/** Reviewed patch composition for DJ2; reusable implementations live in patches/. */
@Mod(modid="omkalitydj2fix",name="Omkality DJ2 Fix",version="0.1.13",
    acceptedMinecraftVersions="[1.12.2]",serverSideOnly=true,acceptableRemoteVersions="*",
    dependencies="required-after:omkalitycore@[0.3.17,0.4.0);required-after:mixinbooter")
public final class OmkalityDJ2Fix {
    @Mod.EventHandler
    public void load(FMLPreInitializationEvent event) {
        CoreServices.register("omkalitydj2fix",1,new ServerExtension() {
            public void prepare(Logger log) throws Exception {
                WrcbeShutdownGuard.install(log);
                GroovyLogReloadGuard.install(log);
                CraftTweakerLogGuard.install(log);
                ResourceGenerationGuard.install(event.getModConfigurationDirectory().toPath(),log);
            }
            public void start(Logger log) throws Exception {
                CoreServices.claims();
                VanillaBoundaryGuard.install(log);
                VanillaBedGuard.install(log);
                NetherPortalBorder.install();
                DisconnectContainerGuard.install(log);
                TwilightSortingGuard.install(log);
                TwilightWorldEffectGuard.install(log);
                TwilightBeanGuard.install(log);
                AePlaneGuard.install(log);
                MekanismPortableGuard.install(log);
                ChatDispatch.ready();
                CoreServices.report("server.chat_dispatch","enabled");
                CoreServices.report("dj2fix","enabled");
                CoreServices.report("fix.vanilla","enabled");
                CoreServices.report("fix.twilight.inventory","enabled");
                CoreServices.report("fix.twilight.world","enabled");
                CoreServices.report("fix.wrcbe","enabled");
            }
        });
    }
    @Mod.EventHandler public void stopping(FMLServerStoppingEvent event) { DisconnectContainerGuard.beforeStop(); }
    @Mod.EventHandler public void stopped(FMLServerStoppedEvent event) { DisconnectContainerGuard.stop(); }
}
