package net.omkality;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Base64;
import java.util.ArrayList;
import java.util.Locale;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.CommandEvent;
import net.minecraftforge.event.ServerChatEvent;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.gameevent.TickEvent;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Console-only moderation. Timed mutes never modify native FTB mute state. */
public final class OwnerModeration {
    private final Object server;
    private final Class<?> rcon, player;
    private final Method eventSender,eventCommand,eventParameters,commandName,sendMessage;
    private final Method schedule,mainThread,playerList,byId,profile,profileId,profileName;
    private final Method banned,getEntry,addEntry,writeChanges,disconnect,chatPlayer;
    private final Field connection,banSource;
    private final Method banValues,banExpiry,entryValue,jsonProperty;
    private final Constructor<?> jsonObject;
    private static final String BAN_SOURCE="Omkality owner TUI v1";
    private long sweptSecond=-1;
    private boolean sweepFailed;
    private final Constructor<?> text,banEntry;
    private final Path store;
    private final Map<UUID,Long> mutes=new HashMap<UUID,Long>();
    private final Logger log;

    public static void install(Path config,Logger log) throws Exception {
        OwnerModeration bridge=new OwnerModeration(config,log);
        bridge.expireBans();
        MinecraftForge.EVENT_BUS.register(bridge);
        CoreServices.report("core.moderation","enabled");
    }
    private static Method method(Class<?> type,String srg,String mcp,Class<?>... args) throws Exception {
        try { return type.getMethod(srg,args); }
        catch(NoSuchMethodException missing) { return type.getMethod(mcp,args); }
    }
    private OwnerModeration(Path config,Logger logger) throws Exception {
        log=logger;
        store=config.resolve("omkality-owner-mutes.properties");
        server=FMLCommonHandler.class.getMethod("getMinecraftServerInstance").invoke(FMLCommonHandler.instance());
        Class<?> mc=Class.forName("net.minecraft.server.MinecraftServer");
        Class<?> sender=Class.forName("net.minecraft.command.ICommandSender");
        Class<?> component=Class.forName("net.minecraft.util.text.ITextComponent");
        Class<?> list=Class.forName("net.minecraft.server.management.PlayerList");
        Class<?> userList=Class.forName("net.minecraft.server.management.UserList");
        Class<?> gameProfile=Class.forName("com.mojang.authlib.GameProfile");
        player=Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        rcon=Class.forName("net.minecraft.network.rcon.RConConsoleSource");
        schedule=method(mc,"func_152344_a","addScheduledTask",Runnable.class);
        mainThread=method(mc,"func_152345_ab","isCallingFromMinecraftThread");
        playerList=method(mc,"func_184103_al","getPlayerList");
        byId=method(list,"func_177451_a","getPlayerByUUID",UUID.class);
        banned=method(list,"func_152608_h","getBannedPlayers");
        getEntry=method(userList,"func_152683_b","getEntry",Object.class);
        addEntry=method(userList,"func_152687_a","addEntry",Class.forName("net.minecraft.server.management.UserListEntry"));
        writeChanges=method(userList,"func_152678_f","writeChanges");
        profile=method(Class.forName("net.minecraft.entity.player.EntityPlayer"),"func_146103_bH","getGameProfile");
        profileId=gameProfile.getMethod("getId");profileName=gameProfile.getMethod("getName");
        try { connection=player.getField("field_71135_a"); }
        catch(NoSuchFieldException missing) { throw new IllegalStateException("missing_player_connection",missing); }
        disconnect=method(Class.forName("net.minecraft.network.NetHandlerPlayServer"),"func_194028_b","disconnect",component);
        sendMessage=method(sender,"func_145747_a","sendMessage",component);
        text=Class.forName("net.minecraft.util.text.TextComponentString").getConstructor(String.class);
        Class<?> json=Class.forName("com.google.gson.JsonObject");
        jsonObject=json.getConstructor();jsonProperty=json.getMethod("addProperty",String.class,String.class);
        banEntry=Class.forName("net.minecraft.server.management.UserListBansEntry").getConstructor(json);
        Class<?> nativeBan=Class.forName("net.minecraft.server.management.UserListEntryBan");
        banExpiry=method(nativeBan,"func_73680_d","getBanEndDate");
        entryValue=Class.forName("net.minecraft.server.management.UserListEntry").getDeclaredMethod("func_152640_f");entryValue.setAccessible(true);
        banSource=nativeBan.getDeclaredField("field_73695_e");banSource.setAccessible(true);
        banValues=userList.getDeclaredMethod("func_152688_e");banValues.setAccessible(true);
        eventSender=CommandEvent.class.getMethod("getSender");
        eventCommand=CommandEvent.class.getMethod("getCommand");
        eventParameters=CommandEvent.class.getMethod("getParameters");
        commandName=method(Class.forName("net.minecraft.command.ICommand"),"func_71517_b","getName");
        chatPlayer=ServerChatEvent.class.getMethod("getPlayer");
        if(Files.exists(store)) {
            if(!Files.isRegularFile(store) || Files.size(store)>65536) throw new IllegalStateException("invalid_mute_store");
            Properties values=new Properties();
            try(java.io.Reader reader=Files.newBufferedReader(store,StandardCharsets.UTF_8)) { values.load(reader); }
            if(values.size()>1024) throw new IllegalStateException("mute_capacity");
            for(String key:values.stringPropertyNames()) {
                UUID id=UUID.fromString(key); long until=Long.parseLong(values.getProperty(key));
                if(!id.toString().equals(key) || until<=0) throw new IllegalStateException("invalid_mute");
                if(until>System.currentTimeMillis()/1000) mutes.put(id,until);
            }
        }
    }
    private Object ban(Object identity,long until,String reason) throws Exception {
        // The native 1.12.2 date constructor incorrectly uses expiry as creation date.
        // Its JSON constructor preserves both dates and is also the native on-disk format.
        Object json=jsonObject.newInstance();
        SimpleDateFormat format=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss Z",Locale.ROOT);
        String[][] values={{"uuid",profileId.invoke(identity).toString()},{"name",profileName.invoke(identity).toString()},
            {"created",format.format(new Date())},{"source",BAN_SOURCE},{"expires",format.format(new Date(until*1000))},{"reason",reason}};
        for(String[] value:values) jsonProperty.invoke(json,value[0],value[1]);
        return banEntry.newInstance(json);
    }
    private void expireBans() throws Exception {
        Object bans=banned.invoke(playerList.invoke(server));
        Object source=banValues.invoke(bans);
        if(!(source instanceof Map) || ((Map<?,?>)source).size()>10000) throw new IllegalStateException("ban_capacity");
        ArrayList<Object> expired=new ArrayList<Object>();
        Date now=new Date();
        for(Object entry:((Map<?,?>)source).values()) {
            Date until=(Date)banExpiry.invoke(entry);
            if(BAN_SOURCE.equals(banSource.get(entry)) && until!=null && !until.after(now)) expired.add(entryValue.invoke(entry));
        }
        // Vanilla's expiry helper removes GameProfile keys from a String-keyed map.
        // Use removeEntry's canonical key only for this bridge's finite expired bans.
        Method remove=method(Class.forName("net.minecraft.server.management.UserList"),"func_152684_c","removeEntry",Object.class);
        for(Object identity:expired) remove.invoke(bans,identity);
        if(!expired.isEmpty()) writeChanges.invoke(bans);
    }
    @SubscribeEvent
    public void tick(TickEvent.ServerTickEvent event) {
        if(event.phase!=TickEvent.Phase.END) return;
        long now=System.currentTimeMillis()/1000;
        if(sweptSecond==now) return;
        sweptSecond=now;
        try { expireBans();sweepFailed=false; }
        catch(Exception error) { if(!sweepFailed) log.error("Owner ban expiry check failed",error);sweepFailed=true; }
    }
    private void mute(UUID id,long until) throws Exception {
        Map<UUID,Long> next=new HashMap<UUID,Long>(); long now=System.currentTimeMillis()/1000;
        for(Map.Entry<UUID,Long> entry:mutes.entrySet()) if(entry.getValue()>now) next.put(entry.getKey(),entry.getValue());
        // A shorter repeated request cannot unexpectedly remove an existing restriction.
        next.put(id,Math.max(until,next.containsKey(id)?next.get(id):0));
        if(next.size()>1024) throw new IllegalStateException("mute_capacity");
        Properties values=new Properties();
        for(Map.Entry<UUID,Long> entry:next.entrySet()) values.setProperty(entry.getKey().toString(),entry.getValue().toString());
        Path pending=Files.createTempFile(store.getParent(),"omk-mutes-",".pending");
        try {
            try(java.io.Writer writer=Files.newBufferedWriter(pending,StandardCharsets.UTF_8)) { values.store(writer,"Owner timed mutes, UTC epoch seconds; independent of FTB mute"); }
            Files.move(pending,store,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
            mutes.clear();mutes.putAll(next);
        } finally { Files.deleteIfExists(pending); }
    }
    private static String receipt(String[] a,boolean ok,String effect,Long expiry,String error) {
        return "OMK_MODERATION_V1 {\"nonce\":\""+a[2]+"\",\"uuid\":\""+a[3]+"\",\"command\":\""+a[1]+"\",\"ok\":"+ok+",\"effect\":\""+effect+"\",\"expires_at\":"+expiry+",\"error\":"+(error==null?"null":"\""+error+"\"")+"}";
    }
    private String run(String[] a) throws Exception {
        if(!Boolean.TRUE.equals(mainThread.invoke(server))) throw new IllegalStateException("wrong_thread");
        if(a.length!=8 || !a[1].matches("kick|ban|mute") || !a[2].matches("[a-f0-9]{32}") || !a[3].matches("[a-f0-9-]{36}") || !a[4].matches("[A-Za-z0-9_]{1,16}") || !a[5].matches("0|[1-9][0-9]{0,7}") || !a[6].matches("[A-Za-z0-9_-]{1,684}") || !"v1".equals(a[7])) throw new IllegalArgumentException("invalid_request");
        UUID id=UUID.fromString(a[3]);
        if(!id.toString().equals(a[3])) throw new IllegalArgumentException("invalid_uuid");
        long seconds=Long.parseLong(a[5]);
        if(seconds>31536000 || ("kick".equals(a[1])?seconds!=0:seconds==0)) throw new IllegalArgumentException("invalid_duration");
        String reason=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(Base64.getUrlDecoder().decode(a[6]))).toString();
        if(reason.isEmpty() || reason.codePointCount(0,reason.length())>128) throw new IllegalArgumentException("invalid_reason");
        for(int i=0;i<reason.length();) { int c=reason.codePointAt(i);int type=Character.getType(c);if(Character.isISOControl(c)||type==Character.FORMAT||c==167) throw new IllegalArgumentException("invalid_reason");i+=Character.charCount(c); }
        Object list=playerList.invoke(server),target=byId.invoke(list,id);
        if(target==null) return receipt(a,false,"none",null,"player_offline");
        Object identity=profile.invoke(target);
        if(!id.equals(profileId.invoke(identity)) || !a[4].equals(profileName.invoke(identity))) return receipt(a,false,"none",null,"refused");
        Long expiry="kick".equals(a[1])?null:System.currentTimeMillis()/1000+seconds;
        String effect="none";
        try {
            if("mute".equals(a[1])) { mute(id,expiry);expiry=mutes.get(id); }
            else {
                if("ban".equals(a[1])) {
                    expireBans();
                    Object bans=banned.invoke(list);
                    if(getEntry.invoke(bans,identity)!=null) return receipt(a,false,"none",null,"already_banned");
                    effect="unknown";
                    addEntry.invoke(bans,ban(identity,expiry,reason));
                    writeChanges.invoke(bans); // addEntry alone swallows IO failures in vanilla.
                }
                effect="unknown";
                disconnect.invoke(connection.get(target),text.newInstance("[OmkalityCraft] "+reason));
            }
            return receipt(a,true,"applied",expiry,null);
        } catch(Exception failure) { log.warn("Owner moderation failed ({})",failure.getClass().getSimpleName());return receipt(a,false,effect,null,"refused"); }
    }
    @SubscribeEvent(priority=EventPriority.HIGHEST)
    public void command(CommandEvent event) {
        Object actor=null;
        try {
            actor=eventSender.invoke(event);
            String name=commandName.invoke(eventCommand.invoke(event)).toString();
            String[] input=(String[])eventParameters.invoke(event);
            if("list".equals(name) && input.length>0 && "omk-moderation".equals(input[0])) {
                event.setCanceled(true);
                if(!rcon.isInstance(actor)) { sendMessage.invoke(actor,text.newInstance("OMK_MODERATION_ERROR console_only"));return; }
                final String[] args=input.clone();
                if(args.length>8) throw new IllegalArgumentException("invalid_request");
                MaintenanceRequest<String> request=new MaintenanceRequest<String>(new Callable<String>() { public String call() throws Exception { return run(args); } });
                if(Boolean.TRUE.equals(mainThread.invoke(server))) request.run();
                else { Future<?> future=(Future<?>)schedule.invoke(server,request);try { future.get(5,TimeUnit.SECONDS); } catch(java.util.concurrent.TimeoutException timeout) { future.cancel(false); } }
                sendMessage.invoke(actor,text.newInstance(request.finish()));
            } else if(player.isInstance(actor) && name.matches("me|tell|msg|w|say") && muted(actor)) {
                event.setCanceled(true);feedback(actor);
            }
        } catch(Exception failure) {
            log.warn("Owner moderation request refused ({})",failure.getClass().getSimpleName());
            if(event.isCanceled() && actor!=null) try { sendMessage.invoke(actor,text.newInstance("OMK_MODERATION_ERROR refused")); } catch(Exception ignored) { }
        }
    }
    private boolean muted(Object actor) throws Exception {
        Long until=mutes.get((UUID)profileId.invoke(profile.invoke(actor)));
        return until!=null && until>System.currentTimeMillis()/1000;
    }
    private void feedback(Object actor) throws Exception { sendMessage.invoke(actor,text.newInstance("[OmkalityCraft] Временный мут ещё действует.")); }
    @SubscribeEvent(priority=EventPriority.HIGHEST)
    public void chat(ServerChatEvent event) {
        try { Object actor=chatPlayer.invoke(event);if(muted(actor)) { event.setCanceled(true);feedback(actor); } }
        catch(Exception failure) { log.error("Owner timed mute check failed",failure); }
    }
}
