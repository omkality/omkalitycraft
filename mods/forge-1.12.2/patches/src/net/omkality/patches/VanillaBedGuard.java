package net.omkality.patches;

import java.lang.reflect.*;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Extend both native edit checks before ItemBed performs either world write. */
public final class VanillaBedGuard {
    private static volatile Method nativeEdit;
    private static Field actorWorld;
    private static Object bed;
    private static Logger log;
    private static volatile boolean enabled,failed;

    private static Method editMethod() throws Exception {
        return Class.forName("net.minecraft.entity.player.EntityPlayer").getMethod("func_175151_a",
            Class.forName("net.minecraft.util.math.BlockPos"),Class.forName("net.minecraft.util.EnumFacing"),
            Class.forName("net.minecraft.item.ItemStack"));
    }
    public static void install(Logger logger) throws Exception {
        log=logger;
        VerifiedArtifacts.requireClass("net.minecraft.item.ItemBed","minecraft.1.12.2.server");
        VerifiedArtifacts.requireClass("net.minecraftforge.fml.common.FMLCommonHandler","forge.1.12.2-14.23.5.2860");
        VerifiedArtifacts.require("mixinbooter");CoreServices.playerPlacement();
        nativeEdit=editMethod();
        actorWorld=Class.forName("net.minecraft.entity.Entity").getField("field_70170_p");
        Object block=Class.forName("net.minecraft.init.Blocks").getField("field_150324_C").get(null);
        bed=Class.forName("net.minecraft.block.Block").getMethod("func_176223_P").invoke(block);
        failed=false;enabled=true;CoreServices.report("fix.vanilla.beds","enabled");
        log.info("Omkality native bed placement pre-write guard enabled (DJ2 adapter)");
    }
    public static boolean permits(Object actor,Object position,Object face,Object stack) throws Exception {
        Method method=nativeEdit;
        if(method==null) { method=editMethod();nativeEdit=method; }
        // Keep native restrictions and failures. Only the added authority check is fail-latched.
        final boolean editable;
        try { editable=Boolean.TRUE.equals(method.invoke(actor,position,face,stack)); }
        catch(InvocationTargetException error) {
            Throwable cause=error.getCause();
            if(cause instanceof RuntimeException) throw (RuntimeException)cause;
            if(cause instanceof Error) throw (Error)cause;
            throw new IllegalStateException("Native bed edit check failed",cause);
        }
        if(!editable || !enabled) return editable;
        if(failed) return false;
        try {
            return CoreServices.playerPlacement().at(actor,actorWorld.get(actor)).permits(position,bed);
        } catch(Exception error) {
            if(!failed) {
                failed=true;CoreServices.report("fix.vanilla.beds","failed closed");
                log.error("Omkality bed placement permission adapter failed; bed placement denied",error);
            }
            return false;
        }
    }
}
