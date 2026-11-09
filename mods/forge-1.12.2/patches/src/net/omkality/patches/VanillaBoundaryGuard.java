package net.omkality.patches;

import java.lang.reflect.*;
import java.util.List;
import org.apache.logging.log4j.Logger;
import net.omkality.api.CoreServices;

/** Exact 1.12.2 native mutations only. FTB owns live, dimension-aware authority. */
public final class VanillaBoundaryGuard {
    static String state="not initialized";
    private static volatile boolean enabled,failed;
    private static Logger log;
    private static Method x,z,offset,offset2,opposite,getState,setState,getTile,getValue;
    private static Method moveList,destroyList;
    private static volatile Method canMove,nativeFlow;
    private static Field remote,sticky;
    private static Object facingProperty,air;
    private static Class<?> movingTile;

    private static Method m(Class<?> type,String name,Class<?>... args) throws Exception {
        Method result=type.getDeclaredMethod(name,args);result.setAccessible(true);return result;
    }
    public static void install(Logger logger) throws Exception {
        log=logger;
        VerifiedArtifacts.requireClass("net.minecraft.block.BlockPistonBase","minecraft.1.12.2.server");
        VerifiedArtifacts.requireClass("net.minecraftforge.fml.common.FMLCommonHandler","forge.1.12.2-14.23.5.2860");
        VerifiedArtifacts.require("mixinbooter");
        Class<?> world=Class.forName("net.minecraft.world.World"),pos=Class.forName("net.minecraft.util.math.BlockPos");
        Class<?> facing=Class.forName("net.minecraft.util.EnumFacing"),blockState=Class.forName("net.minecraft.block.state.IBlockState");
        Class<?> property=Class.forName("net.minecraft.block.properties.IProperty"),block=Class.forName("net.minecraft.block.Block");
        x=pos.getMethod("func_177958_n");z=pos.getMethod("func_177952_p");
        offset=pos.getMethod("func_177972_a",facing);offset2=pos.getMethod("func_177967_a",facing,int.class);
        opposite=facing.getMethod("func_176734_d");getState=world.getMethod("func_180495_p",pos);
        setState=world.getMethod("func_175656_a",pos,blockState);getTile=world.getMethod("func_175625_s",pos);
        getValue=blockState.getMethod("func_177229_b",property);
        remote=world.getField("field_72995_K");
        sticky=Class.forName("net.minecraft.block.BlockPistonBase").getDeclaredField("field_150082_a");sticky.setAccessible(true);
        facingProperty=Class.forName("net.minecraft.block.BlockDirectional").getField("field_176387_N").get(null);
        movingTile=Class.forName("net.minecraft.tileentity.TileEntityPiston");
        Class<?> helper=Class.forName("net.minecraft.block.state.BlockPistonStructureHelper");
        canMove=helper.getMethod("func_177253_a");moveList=helper.getMethod("func_177254_c");destroyList=helper.getMethod("func_177252_d");
        nativeFlow=m(Class.forName("net.minecraft.block.BlockDynamicLiquid"),"func_176375_a",world,pos,blockState,int.class);
        Object airBlock=Class.forName("net.minecraft.init.Blocks").getField("field_150350_a").get(null);
        air=block.getMethod("func_176223_P").invoke(airBlock);
        failed=false;enabled=true;state="enabled";
        log.info("Omkality vanilla mutation claim guard enabled (DJ2 1.12.2 adapter)");
    }
    private static Object invoke(Method method,Object receiver,Object... args) throws Exception {
        try { return method.invoke(receiver,args); }
        catch(InvocationTargetException error) {
            Throwable cause=error.getCause();
            if(cause instanceof RuntimeException) throw (RuntimeException)cause;
            if(cause instanceof Error) throw (Error)cause;
            throw new IllegalStateException("Native vanilla operation failed",cause);
        }
    }
    private static boolean fault(Exception error) {
        if(!failed) {
            failed=true;state="failed closed";
            log.error("Omkality vanilla boundary guard failed; guarded mutations blocked",error);
        }
        return false;
    }
    private static boolean writes(Object world,Object origin,Object target) throws Exception {
        // No FTB work for the common case: one chunk can never span two FTB owners.
        if(((Number)x.invoke(origin)).intValue()>>4 == ((Number)x.invoke(target)).intValue()>>4
            && ((Number)z.invoke(origin)).intValue()>>4 == ((Number)z.invoke(target)).intValue()>>4) return true;
        return CoreServices.claims().at(world,origin).permitsWrite(world,target,true);
    }
    public static boolean beginMove(Object world,Object origin,Object facing) {
        if(!enabled) return true; // Initial world construction precedes FMLServerStarted and player ticks.
        if(failed) return false;
        try { return remote.getBoolean(world) || writes(world,origin,offset.invoke(origin,facing)); }
        catch(Exception error) { return fault(error); }
    }
    public static boolean event(Object piston,Object state,Object world,Object origin,int id) {
        if(!enabled) return true;
        if(failed) return false;
        try {
            if(remote.getBoolean(world) || (id!=0 && id!=1)) return true;
            Object facing=getValue.invoke(state,facingProperty),head=offset.invoke(origin,facing);
            if(!writes(world,origin,head)) return false;
            // Native sticky retraction can finish a moving tile before doMove runs.
            if(id==1 && sticky.getBoolean(piston)) {
                Object target=offset2.invoke(origin,facing,2);
                if(movingTile.isInstance(getTile.invoke(world,target)) && !writes(world,origin,target)) return false;
            }
            return true;
        } catch(Exception error) { return fault(error); }
    }
    public static boolean move(Object helper,Object world,Object origin,Object facing,boolean extending) throws Exception {
        Method method=canMove;
        if(method==null) { method=helper.getClass().getMethod("func_177253_a");canMove=method; }
        if(!Boolean.TRUE.equals(invoke(method,helper))) return false;
        if(!enabled) return true;
        if(failed) return false;
        try {
            if(remote.getBoolean(world)) return true;
            List<?> moved=(List<?>)moveList.invoke(helper),destroyed=(List<?>)destroyList.invoke(helper);
            if(moved.size()>12 || destroyed.size()>12) throw new IllegalStateException("Unreviewed native piston shape");
            Object direction=extending?facing:opposite.invoke(facing);
            for(Object pos:moved) if(!writes(world,origin,pos) || !writes(world,origin,offset.invoke(pos,direction))) return false;
            for(Object pos:destroyed) if(!writes(world,origin,pos)) return false;
            return true;
        } catch(Exception error) { return fault(error); }
    }
    public static void flow(Object receiver,Object world,Object target,Object state,int level,Object origin) throws Exception {
        if(enabled) {
            if(failed) return;
            try { if(!remote.getBoolean(world) && !writes(world,origin,target)) return; }
            catch(Exception error) { fault(error);return; }
        }
        Method method=nativeFlow;
        if(method==null) {
            method=m(Class.forName("net.minecraft.block.BlockDynamicLiquid"),"func_176375_a",
                Class.forName("net.minecraft.world.World"),Class.forName("net.minecraft.util.math.BlockPos"),
                Class.forName("net.minecraft.block.state.IBlockState"),int.class);
            nativeFlow=method;
        }
        invoke(method,receiver,world,target,state,level);
    }
    public static boolean generated(Object world,Object target,Object newState,Object origin) throws Exception {
        if(enabled) {
            if(failed) return false;
            try { if(!remote.getBoolean(world) && !writes(world,origin,target)) return false; }
            catch(Exception error) { return fault(error); }
        }
        Method method=setState;
        if(method==null) method=world.getClass().getMethod("func_175656_a",Class.forName("net.minecraft.util.math.BlockPos"),Class.forName("net.minecraft.block.state.IBlockState"));
        return Boolean.TRUE.equals(invoke(method,world,target,newState));
    }
    public static Object mixingNeighbor(Object world,Object neighbor,Object origin) throws Exception {
        if(enabled) {
            if(failed) return air;
            try { if(!remote.getBoolean(world) && !writes(world,neighbor,origin)) return air; }
            catch(Exception error) { fault(error);return air; }
        }
        Method method=getState;
        if(method==null) method=world.getClass().getMethod("func_180495_p",Class.forName("net.minecraft.util.math.BlockPos"));
        return invoke(method,world,neighbor);
    }
}
