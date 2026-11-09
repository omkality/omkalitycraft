package net.omkality.patches;

import java.lang.reflect.*;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Native machine effects use current FTB domains, never a shared fake player's OP. */
public final class AePlaneGuard {
    private static Method host,tile,world,position,side,facing,offset,x,z;
    private static Field remote;
    private static boolean enabled,failed;
    private static Logger log;
    public static void install(Logger logger) throws Exception {
        log=logger;CoreServices.claims();
        VerifiedArtifacts.requireClass("appeng.parts.automation.PartAnnihilationPlane","ae2.planes.0.56.4");
        VerifiedArtifacts.requireClass("shadows.PlaneFix","planefix.1.0.0");
        Class<?> part=Class.forName("appeng.parts.AEBasePart"),te=Class.forName("net.minecraft.tileentity.TileEntity");
        Class<?> wt=Class.forName("net.minecraft.world.World"),pt=Class.forName("net.minecraft.util.math.BlockPos");
        Class<?> face=Class.forName("net.minecraft.util.EnumFacing");
        host=part.getMethod("getHost");tile=part.getMethod("getTile");side=part.getMethod("getSide");
        world=te.getMethod("func_145831_w");position=te.getMethod("func_174877_v");
        facing=Class.forName("appeng.api.util.AEPartLocation").getMethod("getFacing");
        offset=pt.getMethod("func_177972_a",face);x=pt.getMethod("func_177958_n");z=pt.getMethod("func_177952_p");
        remote=wt.getField("field_72995_K");enabled=true;
        CoreServices.report("fix.ae2.planes","enabled");
        log.info("Omkality native AE2 plane claim guard enabled (DJ2 adapter)");
    }
    private static boolean fault(Exception error) {
        if(!failed) {
            failed=true;CoreServices.report("fix.ae2.planes","failed closed");
            log.error("Omkality AE2 plane permission adapter failed; world operations denied",error);
        }
        return false;
    }
    public static boolean permits(Object part) {
        // Existing grids can load before the FML server-started callback. They
        // must not mutate before the permission provider has been installed.
        if(!enabled || failed) return false;
        try {
            if(host.invoke(part)==null) return false; // Removed/unloaded part, no new operation.
            Object sourceTile=tile.invoke(part);
            if(sourceTile==null) return false;
            Object sourceWorld=world.invoke(sourceTile);
            if(sourceWorld==null) return false;
            if(remote.getBoolean(sourceWorld)) return true;
            Object origin=position.invoke(sourceTile);
            Object target=offset.invoke(origin,facing.invoke(side.invoke(part)));
            if(((Number)x.invoke(origin)).intValue()>>4 == ((Number)x.invoke(target)).intValue()>>4
                && ((Number)z.invoke(origin)).intValue()>>4 == ((Number)z.invoke(target)).intValue()>>4) return true;
            return CoreServices.claims().at(sourceWorld,origin).permitsWrite(sourceWorld,target,true);
        } catch(Exception error) {return fault(error);}
    }
    public static Object idle() {
        try{return Class.forName("appeng.api.networking.ticking.TickRateModulation").getField("IDLE").get(null);}
        catch(Exception error){throw new IllegalStateException("Native AE2 tick result unavailable",error);}
    }
}
