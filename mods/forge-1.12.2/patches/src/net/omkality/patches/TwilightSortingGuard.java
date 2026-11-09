package net.omkality.patches;

import java.lang.reflect.*;
import java.util.ArrayList;
import java.util.List;
import org.apache.logging.log4j.Logger;
import net.omkality.api.CoreServices;
import net.omkality.api.ClaimAccess;

/** Ownerless automation may only access inventories in its FTB ownership domain.
 * Native TF still owns selection, counting, moving and merging. No fake OP actor.
 */
public final class TwilightSortingGuard {
    static String state="not initialized";
    private static Method container, getPos, getWorld;
    private static Class<?> tile, large, inventory;
    private static final List<Field> halves=new ArrayList<Field>();
    private static Logger log;
    private static boolean failed;

    private static Method method(Class<?> type,String srg,String mcp,Class<?>... args) throws Exception {
        try { return type.getMethod(srg,args); }
        catch (NoSuchMethodException error) { return type.getMethod(mcp,args); }
    }

    public static void install(Logger logger) throws Exception {
        log=logger;
        CoreServices.claims();
        VerifiedArtifacts.require("twilightforest");
        Class<?> world=Class.forName("net.minecraft.world.World"),pos=Class.forName("net.minecraft.util.math.BlockPos");
        container=method(Class.forName("net.minecraft.block.BlockChest"),"func_189418_a","getContainer",world,pos,boolean.class);
        tile=Class.forName("net.minecraft.tileentity.TileEntity");
        getPos=method(tile,"func_174877_v","getPos");
        getWorld=method(tile,"func_145831_w","getWorld");
        large=Class.forName("net.minecraft.inventory.InventoryLargeChest");
        inventory=Class.forName("net.minecraft.inventory.IInventory");
        halves.clear();
        for (Field field:large.getDeclaredFields()) {
            if (!Modifier.isStatic(field.getModifiers()) && inventory.isAssignableFrom(field.getType())) {
                field.setAccessible(true); halves.add(field);
            }
        }
        if (halves.size()!=2) throw new IllegalStateException("Unknown compound chest layout");
        failed=false; state="enabled";
        log.info("Omkality autonomous inventory claim guard enabled (DJ2 adapter)");
    }

    private static boolean permitted(Object value,ClaimAccess.Scope scope,Object world,int depth) throws Exception {
        if (value==null || depth>2) return false;
        if (large.isInstance(value)) {
            for (Field half:halves)
                if (!permitted(half.get(value),scope,world,depth+1)) return false;
            return true;
        }
        return tile.isInstance(value) && inventory.isInstance(value) && getWorld.invoke(value)==world
            && scope.contains(world,getPos.invoke(value));
    }

    public static Object inventory(Object block,Object world,Object target,boolean allowBlocked,Object sourceWorld,Object origin) {
        if (failed) return null;
        try {
            if (!"enabled".equals(state) || world!=sourceWorld)
                throw new IllegalStateException("Inventory claim guard is not active in the source world");
            ClaimAccess.Scope scope=CoreServices.claims().at(world,origin);
            if (!scope.contains(world,target)) return null;
            Object value=container.invoke(block,world,target,allowBlocked);
            return permitted(value,scope,world,0) ? value : null;
        } catch (Exception error) {
            failed=true; state="failed closed";
            log.error("Omkality autonomous inventory guard failed; guarded inventory access is blocked",error);
            return null;
        }
    }
}
