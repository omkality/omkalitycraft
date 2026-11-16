package net.omkality.patches;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Finish player-owned transient slots through native closing, before logout/save. */
public final class DisconnectContainerGuard {
    public interface Installed { }
    public interface DropInstalled { }
    private static volatile DisconnectContainerGuard active;
    private final Object server;
    private final Class<?> playerType,personalType,workbenchType;
    private final Field personal,opened,inventory;
    private final Method mainThread,alive,disconnected,cursor,empty,slot,stack,closed,closeContainer,playerList,players;
    private final Method tossPlayer,tossEntity,droppedStack;

    private static Method method(Class<?> type,String srg,String mcp,Class<?>...args)throws Exception {
        try{return type.getMethod(srg,args);}catch(NoSuchMethodException error){return type.getMethod(mcp,args);}
    }
    private static Field field(Class<?> type,String srg,String mcp)throws Exception {
        try{return type.getField(srg);}catch(NoSuchFieldException error){return type.getField(mcp);}
    }
    private DisconnectContainerGuard()throws Exception {
        playerType=Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        if(!Installed.class.isAssignableFrom(playerType))throw new IllegalStateException("Player disconnect lifecycle mixin is absent");
        if(!DropInstalled.class.isAssignableFrom(Class.forName("mod.acgaming.universaltweaks.bugfixes.entities.disconnectdupe.UTDisconnectDupe")))
            throw new IllegalStateException("Native disconnect drop compatibility mixin is absent");
        Class<?> player=Class.forName("net.minecraft.entity.player.EntityPlayer"),container=Class.forName("net.minecraft.inventory.Container");
        personalType=Class.forName("net.minecraft.inventory.ContainerPlayer");workbenchType=Class.forName("net.minecraft.inventory.ContainerWorkbench");
        personal=field(player,"field_71069_bz","inventoryContainer");opened=field(player,"field_71070_bA","openContainer");inventory=field(player,"field_71071_by","inventory");
        alive=method(Class.forName("net.minecraft.entity.Entity"),"func_70089_S","isEntityAlive");
        disconnected=method(playerType,"func_193105_t","hasDisconnected");
        cursor=method(Class.forName("net.minecraft.entity.player.InventoryPlayer"),"func_70445_o","getItemStack");
        empty=method(Class.forName("net.minecraft.item.ItemStack"),"func_190926_b","isEmpty");
        slot=method(container,"func_75139_a","getSlot",int.class);stack=method(Class.forName("net.minecraft.inventory.Slot"),"func_75211_c","getStack");
        closed=method(container,"func_75134_a","onContainerClosed",player);closeContainer=method(playerType,"func_71128_l","closeContainer");
        server=FMLCommonHandler.class.getMethod("getMinecraftServerInstance").invoke(FMLCommonHandler.instance());
        Class<?> mc=Class.forName("net.minecraft.server.MinecraftServer");mainThread=method(mc,"func_152345_ab","isCallingFromMinecraftThread");
        playerList=method(mc,"func_184103_al","getPlayerList");players=method(Class.forName("net.minecraft.server.management.PlayerList"),"func_181057_v","getPlayers");
        Class<?> toss=Class.forName("net.minecraftforge.event.entity.item.ItemTossEvent");
        tossPlayer=toss.getMethod("getPlayer");tossEntity=toss.getMethod("getEntityItem");
        droppedStack=method(Class.forName("net.minecraft.entity.item.EntityItem"),"func_92059_d","getItem");
    }
    public static void install(Logger log)throws Exception {
        VerifiedArtifacts.requireClass("net.minecraft.entity.player.EntityPlayerMP","minecraft.1.12.2.server");
        VerifiedArtifacts.requireClass("net.minecraft.inventory.ContainerPlayer","minecraft.1.12.2.server");
        VerifiedArtifacts.requireClass("net.minecraft.inventory.ContainerWorkbench","minecraft.1.12.2.server");
        VerifiedArtifacts.require("universaltweaks");
        VerifiedArtifacts.require("mixinbooter");active=new DisconnectContainerGuard();
        CoreServices.report("fix.vanilla.disconnect","enabled");
        log.info("Omkality native player transient-container finalization enabled (1.12.2)");
    }
    private boolean held(Object actor)throws Exception {
        return !Boolean.TRUE.equals(empty.invoke(cursor.invoke(inventory.get(actor))));
    }
    private boolean inputs(Object container,int count)throws Exception {
        for(int i=1;i<=count;i++)if(!Boolean.TRUE.equals(empty.invoke(stack.invoke(slot.invoke(container,i)))))return true;
        return false;
    }
    private void sources(List<Object> out,Object container,int count)throws Exception {
        for(int i=1;i<=count;i++) {
            Object value=stack.invoke(slot.invoke(container,i));
            if(!Boolean.TRUE.equals(empty.invoke(value)))out.add(value);
        }
    }
    private void settle(Object actor)throws Exception {
        if(!playerType.isInstance(actor)||!Boolean.TRUE.equals(mainThread.invoke(server))
            ||!Boolean.TRUE.equals(alive.invoke(actor))||Boolean.TRUE.equals(disconnected.invoke(actor)))return;
        Object own=personal.get(actor);
        if(own==null||own.getClass()!=personalType)return;
        Object current=opened.get(actor);
        List<Object> actual=new ArrayList<Object>(14);sources(actual,own,4);
        Object carried=cursor.invoke(inventory.get(actor));
        if(!Boolean.TRUE.equals(empty.invoke(carried)))actual.add(carried);
        if(current!=null&&current.getClass()==workbenchType)sources(actual,current,9);
        if(actual.isEmpty())return;
        // References, never stack copies: the exception applies only to the
        // native drops of these exact transient items, before player data save.
        try(DisconnectDropScope scope=DisconnectDropScope.enter(actor,actual.toArray())) {
            if(current!=null&&current.getClass()==workbenchType&&(inputs(current,9)||held(actor)))closeContainer.invoke(actor);
            // Do not call custom machine close handlers or move their slots.
            if(inputs(own,4)||held(actor))closed.invoke(own,actor);
        }
    }
    private static RuntimeException failure(Exception error) {
        Throwable cause=error instanceof InvocationTargetException?((InvocationTargetException)error).getCause():error;
        if(cause instanceof Error)throw (Error)cause;
        if(cause instanceof RuntimeException)return (RuntimeException)cause;
        return new IllegalStateException("Native transient-container finalization failed",cause);
    }
    public static void beforeDisconnect(Object actor) {
        DisconnectContainerGuard binding=active;if(binding==null)return;
        try{binding.settle(actor);}catch(Exception error){throw failure(error);}
    }
    public static boolean permitsNativeDrop(Object event) {
        DisconnectContainerGuard binding=active;if(binding==null||!DisconnectDropScope.active())return false;
        try {
            return DisconnectDropScope.permits(binding.tossPlayer.invoke(event),binding.droppedStack.invoke(binding.tossEntity.invoke(event)));
        }catch(Exception error){throw failure(error);}
    }
    public static void beforeStop() {
        DisconnectContainerGuard binding=active;if(binding==null)return;
        try {
            if(!Boolean.TRUE.equals(binding.mainThread.invoke(binding.server)))return;
            List<?> snapshot=new ArrayList<Object>((List<?>)binding.players.invoke(binding.playerList.invoke(binding.server)));
            for(Object actor:snapshot)binding.settle(actor);
        }catch(Exception error){throw failure(error);}
    }
    public static void stop(){active=null;}
}
