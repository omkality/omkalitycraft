package net.omkality.patches;

import java.lang.reflect.*;
import java.util.Random;
import org.apache.logging.log4j.Logger;
import net.omkality.api.CoreServices;

/** Filter native candidate positions before extra ticks or biome writes occur. */
public final class TwilightWorldEffectGuard {
    static String state="not initialized";
    private static Method offset3,offset5;
    private static Object excluded;
    private static Logger log;
    private static boolean failed;

    public static void install(Logger logger) throws Exception {
        log=logger;VerifiedArtifacts.require("twilightforest");
        Class<?> pos=Class.forName("net.minecraft.util.math.BlockPos"),util=Class.forName("twilightforest.util.WorldUtil");
        offset3=util.getMethod("randomOffset",Random.class,pos,int.class);
        offset5=util.getMethod("randomOffset",Random.class,pos,int.class,int.class,int.class);
        // In reviewed Forge 1.12.2, out-of-height state is air and tile is null.
        // The biome callback skips this candidate by its distance check first.
        excluded=pos.getConstructor(int.class,int.class,int.class).newInstance(0,-512,0);
        failed=false;state="enabled";
        log.info("Omkality autonomous tick and biome claim guard enabled (DJ2 adapter)");
    }
    private static Object nativeOffset(Method method,Object... args) throws Exception {
        try { return method.invoke(null,args); }
        catch(InvocationTargetException error) {
            Throwable cause=error.getCause();
            if(cause instanceof RuntimeException) throw (RuntimeException)cause;
            if(cause instanceof Error) throw (Error)cause;
            throw new IllegalStateException("Native position selection failed",cause);
        }
    }
    private static Object filter(Object world,Object origin,Object selected) {
        if(failed) return excluded;
        try {
            if(!"enabled".equals(state)) throw new IllegalStateException("World effect guard is not initialized");
            return CoreServices.claims().at(world,origin).contains(world,selected)?selected:excluded;
        } catch(Exception error) {
            failed=true;state="failed closed";
            log.error("Omkality autonomous world guard failed; effects blocked",error);
            return excluded;
        }
    }
    public static Object offset(Random random,Object pos,int range,Object world,Object origin) throws Exception {
        return filter(world,origin,nativeOffset(offset3,random,pos,range));
    }
    public static Object offset(Random random,Object pos,int rx,int ry,int rz,Object world,Object origin) throws Exception {
        return filter(world,origin,nativeOffset(offset5,random,pos,rx,ry,rz));
    }
}
