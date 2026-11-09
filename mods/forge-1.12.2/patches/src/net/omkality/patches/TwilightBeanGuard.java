package net.omkality.patches;

import java.lang.reflect.*;
import net.omkality.api.CoreServices;
import net.omkality.api.PlayerPlacementAccess;
import org.apache.logging.log4j.Logger;

/** Authorize native writes BEFORE replacing blocks or dropping tile inventories. */
public final class TwilightBeanGuard {
    private static final ThreadLocal<PlayerPlacementAccess.Scope> scope=new ThreadLocal<PlayerPlacementAccess.Scope>();
    private static Method grow,set2,set3;
    private static Logger log;
    private static boolean failed;
    public static void install(Logger logger) throws Exception {
        log=logger;VerifiedArtifacts.require("twilightforest");CoreServices.playerPlacement();
        Class<?> world=Class.forName("net.minecraft.world.World"),pos=Class.forName("net.minecraft.util.math.BlockPos");
        Class<?> state=Class.forName("net.minecraft.block.state.IBlockState");
        grow=Class.forName("twilightforest.item.ItemTFMagicBeans").getDeclaredMethod("makeHugeStalk",world,pos,int.class,int.class);
        grow.setAccessible(true);
        set2=world.getMethod("func_175656_a",pos,state);set3=world.getMethod("func_180501_a",pos,state,int.class);
        CoreServices.report("fix.twilight.beans","enabled");
        log.info("Omkality native plant placement pre-write guard enabled (DJ2 adapter)");
    }
    private static Object invoke(Method method,Object receiver,Object... arguments) throws Exception {
        try{return method.invoke(receiver,arguments);}
        catch(InvocationTargetException error) {
            Throwable cause=error.getCause();
            if(cause instanceof RuntimeException) throw (RuntimeException)cause;
            if(cause instanceof Error) throw (Error)cause;
            throw new IllegalStateException("Native plant operation failed",cause);
        }
    }
    private static void fail(Exception error) {
        if(!failed) {
            failed=true;CoreServices.report("fix.twilight.beans","failed closed");
            log.error("Omkality plant placement permission adapter failed; writes denied",error);
        }
    }
    public static void grow(Object item,Object actor,Object world,Object origin,int min,int max) throws Exception {
        PlayerPlacementAccess.Scope previous=scope.get(),current;
        if(failed) return;
        try{current=CoreServices.playerPlacement().at(actor,world);}
        catch(Exception error){fail(error);return;}
        scope.set(current);
        try{invoke(grow,item,world,origin,min,max);}
        finally{if(previous==null)scope.remove();else scope.set(previous);}
    }
    public static boolean write(Object world,Object position,Object state,Integer flags) throws Exception {
        if(failed) return false;
        try {
            PlayerPlacementAccess.Scope current=scope.get();
            if(current==null) throw new IllegalStateException("Native plant write outside player scope");
            if(!current.permits(position,state)) return false;
        } catch(Exception error){fail(error);return false;}
        // Native failures remain native failures, not permission failures.
        return Boolean.TRUE.equals(flags==null?invoke(set2,world,position,state):invoke(set3,world,position,state,flags));
    }
}
