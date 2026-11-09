package net.omkality.patches;

import java.lang.reflect.*;
import java.util.Map;
import java.util.UUID;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Recheck portable-device conditions on the server thread before native effects. */
public final class MekanismPortableGuard {
    private static Class<?> portable,teleporter;
    private static Method held,item,empty,access,alive,uuid,frequencies,closest,energy,cost,loaded,getTile,getWorld;
    private static Constructor<?> coord,position;
    private static Field hand,type,requested,world,remote,name,publicFreq,privateManagers,publicManager,dimension,cx,cy,cz,tileFrequency;
    private static boolean enabled,failed;
    private static Logger log;

    public static void install(Logger logger) throws Exception {
        log=logger;
        VerifiedArtifacts.requireClass("mekanism.common.network.PacketPortableTeleporter","mekanism.portable.9.8.3.390");
        Class<?> player=Class.forName("net.minecraft.entity.player.EntityPlayer"),entity=Class.forName("net.minecraft.entity.Entity");
        Class<?> stack=Class.forName("net.minecraft.item.ItemStack"),wt=Class.forName("net.minecraft.world.World");
        Class<?> pt=Class.forName("net.minecraft.util.math.BlockPos"),ct=Class.forName("mekanism.api.Coord4D");
        Class<?> freq=Class.forName("mekanism.common.frequency.Frequency"),manager=Class.forName("mekanism.common.frequency.FrequencyManager");
        Class<?> message=Class.forName("mekanism.common.network.PacketPortableTeleporter$PortableTeleporterMessage");
        Class<?> nativeMod=Class.forName("mekanism.common.Mekanism");
        portable=Class.forName("mekanism.common.item.ItemPortableTeleporter");
        teleporter=Class.forName("mekanism.common.tile.TileEntityTeleporter");
        held=player.getMethod("func_184586_b",Class.forName("net.minecraft.util.EnumHand"));
        item=stack.getMethod("func_77973_b");empty=stack.getMethod("func_190926_b");
        access=Class.forName("mekanism.common.util.SecurityUtils").getMethod("canAccess",player,stack);
        alive=entity.getMethod("func_70089_S");uuid=entity.getMethod("func_110124_au");
        hand=message.getField("currentHand");type=message.getField("packetType");requested=message.getField("frequency");
        world=entity.getField("field_70170_p");remote=wt.getField("field_72995_K");
        name=freq.getField("name");publicFreq=freq.getField("publicFreq");
        publicManager=nativeMod.getField("publicTeleporters");privateManagers=nativeMod.getField("privateTeleporters");
        frequencies=manager.getMethod("getFrequencies");closest=freq.getMethod("getClosestCoords",ct);
        coord=ct.getConstructor(entity);position=pt.getConstructor(int.class,int.class,int.class);
        energy=portable.getMethod("getEnergy",stack);cost=portable.getMethod("calculateEnergyCost",entity,ct);
        dimension=ct.getField("dimensionId");cx=ct.getField("x");cy=ct.getField("y");cz=ct.getField("z");
        getWorld=Class.forName("net.minecraftforge.common.DimensionManager").getMethod("getWorld",int.class);
        loaded=wt.getMethod("func_175667_e",pt);getTile=wt.getMethod("func_175625_s",pt);
        tileFrequency=teleporter.getField("frequency");
        enabled=true;
        CoreServices.report("fix.mekanism.portable","enabled");
        log.info("Omkality native Mekanism portable-device guard enabled (DJ2 adapter)");
    }

    public static boolean permits(Object player,Object message) {
        if(!enabled || failed || player==null || message==null) return false;
        try {
            if(!Boolean.TRUE.equals(alive.invoke(player))) return false;
            Object source=world.get(player),currentHand=hand.get(message),packetType=type.get(message);
            if(source==null || remote.getBoolean(source) || currentHand==null || packetType==null) return false;
            String operation=((Enum<?>)packetType).name();
            // DATA_RESPONSE is client-bound and must never execute the server proxy.
            if(!operation.equals("DATA_REQUEST") && !operation.equals("SET_FREQ")
                && !operation.equals("DEL_FREQ") && !operation.equals("TELEPORT")) return false;
            Object stack=held.invoke(player,currentHand);
            if(Boolean.TRUE.equals(empty.invoke(stack)) || !portable.isInstance(item.invoke(stack))) return false;
            if(!Boolean.TRUE.equals(access.invoke(null,player,stack))) return false;
            Object given=requested.get(message);
            if(operation.equals("DATA_REQUEST")) return true; // The native request permits no selection.
            if(given==null || name.get(given)==null) return false;
            if(!operation.equals("TELEPORT")) return true;

            UUID owner=(UUID)uuid.invoke(player);
            Object manager=publicFreq.getBoolean(given)?publicManager.get(null):((Map<?,?>)privateManagers.get(null)).get(owner);
            if(manager==null) return false;
            Object found=null;
            for(Object frequency:(Iterable<?>)frequencies.invoke(manager)) {
                if(name.get(given).equals(name.get(frequency))) {found=frequency;break;}
            }
            if(found==null) return false;
            Object target=closest.invoke(found,coord.newInstance(player));
            if(target==null) return false;
            // Observe existing native state only; a request must not load a dimension/chunk.
            Object targetWorld=getWorld.invoke(null,dimension.getInt(target));
            Object at=position.newInstance(cx.getInt(target),cy.getInt(target),cz.getInt(target));
            if(targetWorld==null || !Boolean.TRUE.equals(loaded.invoke(targetWorld,at))) return false;
            Object tile=getTile.invoke(targetWorld,at);
            if(!teleporter.isInstance(tile) || !found.equals(tileFrequency.get(tile))) return false;
            Object device=item.invoke(stack);
            double available=((Number)energy.invoke(device,stack)).doubleValue();
            double needed=((Number)cost.invoke(null,player,target)).doubleValue();
            // The original handler remains the sole owner of cost deduction and teleport.
            return Double.isFinite(available) && Double.isFinite(needed) && needed>=0D && available>=needed;
        } catch(Exception error) {
            failed=true;CoreServices.report("fix.mekanism.portable","failed closed");
            log.error("Omkality Mekanism portable adapter failed; portable requests denied",error);
            return false;
        }
    }
}
