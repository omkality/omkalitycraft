package net.omkality;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.CommandEvent;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.omkality.api.BackupPolicyAccess;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Restricted owner transport, not a player command or generic RCON executor. */
public final class MaintenanceBridge {
    private final Object server;
    private final Class<?> rcon;
    private final Method eventSender,eventCommand,eventParameters,commandName,sendMessage;
    private final Method mainThread,schedule,playerList,players;
    private final Constructor<?> text;
    private final String boot=UUID.randomUUID().toString().replace("-","");
    private final MaintenanceNotices notices=new MaintenanceNotices();
    private final Logger log;
    public static void install(Logger log) throws Exception {
        MinecraftForge.EVENT_BUS.register(new MaintenanceBridge(log));
        CoreServices.report("core.maintenance","enabled");
    }
    private static Method method(Class<?> type,String srg,String mcp,Class<?>... args) throws Exception {
        try { return type.getMethod(srg,args); }
        catch(NoSuchMethodException missing) { return type.getMethod(mcp,args); }
    }
    private MaintenanceBridge(Logger logger) throws Exception {
        log=logger;
        server=FMLCommonHandler.class.getMethod("getMinecraftServerInstance").invoke(FMLCommonHandler.instance());
        Class<?> mc=Class.forName("net.minecraft.server.MinecraftServer");
        Class<?> sender=Class.forName("net.minecraft.command.ICommandSender");
        Class<?> component=Class.forName("net.minecraft.util.text.ITextComponent");
        rcon=Class.forName("net.minecraft.network.rcon.RConConsoleSource");
        mainThread=method(mc,"func_152345_ab","isCallingFromMinecraftThread");
        schedule=method(mc,"func_152344_a","addScheduledTask",Runnable.class);
        playerList=method(mc,"func_184103_al","getPlayerList");
        players=method(Class.forName("net.minecraft.server.management.PlayerList"),"func_181057_v","getPlayers");
        sendMessage=method(sender,"func_145747_a","sendMessage",component);
        text=Class.forName("net.minecraft.util.text.TextComponentString").getConstructor(String.class);
        eventSender=CommandEvent.class.getMethod("getSender");
        eventCommand=CommandEvent.class.getMethod("getCommand");
        eventParameters=CommandEvent.class.getMethod("getParameters");
        commandName=method(Class.forName("net.minecraft.command.ICommand"),"func_71517_b","getName");
    }
    private boolean onMain() throws Exception { return Boolean.TRUE.equals(mainThread.invoke(server)); }
    private String run(final String[] args) throws Exception {
        if(!onMain()) throw new IllegalStateException("wrong_thread");
        BackupPolicyAccess provider=CoreServices.backupPolicy();
        String adapter=provider==null?"unavailable":provider.adapter();
        if(adapter==null || !adapter.matches("[a-z0-9][a-z0-9.-]{0,79}")) throw new IllegalStateException("invalid_backup_adapter");
        boolean disabled=provider!=null && provider.automaticBackupsDisabled();
        boolean running=provider==null || provider.backupRunning();
        String prefix="OMK_MAINTENANCE_V1 {\"schema\":1,\"boot\":\""+boot+"\",\"main_thread\":true";
        if(args.length==2 && "probe".equals(args[1]))
            return prefix+",\"backup_adapter\":\""+adapter+"\",\"automatic_backups_disabled\":"+disabled+",\"backup_running\":"+running+"}";
        if(args.length!=5 || !"warn".equals(args[1]) || !boot.equals(args[2]) || !args[3].matches("[a-f0-9]{32}") || !args[4].matches("[1-9][0-9]{0,3}"))
            throw new IllegalArgumentException("invalid_notice_or_boot");
        final int seconds=Integer.parseInt(args[4]);
        if(!disabled || running) throw new IllegalStateException("backup_policy_not_ready");
        MaintenanceNotices.Receipt receipt=notices.send(args[3],seconds,new Callable<Integer>() {
            public Integer call() throws Exception {
                Object source=players.invoke(playerList.invoke(server));
                if(!(source instanceof List) || ((List<?>)source).size()>10000) throw new IllegalStateException("invalid_players");
                List<?> online=new ArrayList<Object>((List<?>)source);
                Object message=text.newInstance("[OmkalityCraft] Плановый перезапуск через "+seconds+" с. Сервер сохранит прогресс и создаст резервную копию. Возвращайтесь через несколько минут.");
                for(Object player:online) sendMessage.invoke(player,message);
                return online.size();
            }
        });
        return prefix+",\"operation\":\""+args[3]+"\",\"seconds_before\":"+seconds+",\"delivered\":"+receipt.delivered+",\"replayed\":"+receipt.replayed+"}";
    }
    private String dispatch(final String[] args) throws Exception {
        MaintenanceRequest<String> request=new MaintenanceRequest<String>(new Callable<String>() {
            public String call() throws Exception { return run(args); }
        });
        if(onMain()) request.run();
        else {
            Future<?> future=(Future<?>)schedule.invoke(server,request);
            try { future.get(5,TimeUnit.SECONDS); }
            catch(TimeoutException expired) { future.cancel(false); }
            catch(InterruptedException interrupted) { future.cancel(false);Thread.currentThread().interrupt(); }
        }
        return request.finish();
    }
    @SubscribeEvent(priority=EventPriority.HIGHEST)
    public void command(CommandEvent event) {
        Object actor=null;
        try {
            if(!"list".equals(commandName.invoke(eventCommand.invoke(event)))) return;
            String[] input=(String[])eventParameters.invoke(event);
            if(input.length==0 || !"omk-maintenance".equals(input[0])) return;
            event.setCanceled(true);
            actor=eventSender.invoke(event);
            if(!rcon.isInstance(actor)) {
                sendMessage.invoke(actor,text.newInstance("OMK_MAINTENANCE_ERROR console_only"));return;
            }
            // Fixed argument grammar is also checked on the main thread.
            if(input.length>5) throw new IllegalArgumentException("invalid_request");
            sendMessage.invoke(actor,text.newInstance(dispatch(input.clone())));
        } catch(Exception error) {
            log.warn("Omkality maintenance request refused ({})",error.getClass().getSimpleName());
            if(actor!=null) try { sendMessage.invoke(actor,text.newInstance("OMK_MAINTENANCE_ERROR refused")); }
            catch(Exception ignored) { /* The caller needs a valid typed receipt. */ }
        }
    }
}
