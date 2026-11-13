package net.omkality;

import java.lang.reflect.*;
import java.nio.file.Path;
import java.util.*;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.common.gameevent.PlayerEvent;
import net.minecraftforge.fml.common.gameevent.TickEvent;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Generic Forge chat guide; vanilla stats and Forge PlayerPersisted own the data. */
public final class WelcomeChat {
    private static WelcomeChat active;
    private static final String COMMAND="guide",ROOT="PlayerPersisted",KEY="omkality_guide";
    private final Object server,stat;
    private final WelcomePolicy policy;
    private final WelcomeQueue queue=new WelcomeQueue();
    private final Logger log;
    private final Class<?> playerType,compound;
    private final Method uuid,playerList,byUuid,statistics,readStat,entityData,has,typed,getCompound,getLong,setLong,setTag,send,commandName;
    private final Constructor<?> text;
    private long lastWarning=Long.MIN_VALUE;
    private WelcomeChat(Path config,WelcomePolicy p,Logger logger)throws Exception {
        policy=p;log=logger;
        server=FMLCommonHandler.class.getMethod("getMinecraftServerInstance").invoke(FMLCommonHandler.instance());
        Class<?> mc=Class.forName("net.minecraft.server.MinecraftServer"),entity=Class.forName("net.minecraft.entity.Entity");
        playerType=Class.forName("net.minecraft.entity.player.EntityPlayerMP");compound=Class.forName("net.minecraft.nbt.NBTTagCompound");
        uuid=m(entity,"func_110124_au","getUniqueID");
        playerList=m(mc,"func_184103_al","getPlayerList");
        byUuid=m(Class.forName("net.minecraft.server.management.PlayerList"),"func_177451_a","getPlayerByUUID",UUID.class);
        statistics=m(playerType,"func_147099_x","getStatFile");
        readStat=m(Class.forName("net.minecraft.stats.StatisticsManager"),"func_77444_a","readStat",Class.forName("net.minecraft.stats.StatBase"));
        Class<?> stats=Class.forName("net.minecraft.stats.StatList");
        Field field;try{field=stats.getField("field_188097_g");}catch(NoSuchFieldException e){field=stats.getField("PLAY_ONE_MINUTE");}stat=field.get(null);
        entityData=entity.getMethod("getEntityData");
        has=m(compound,"func_74764_b","hasKey",String.class);typed=m(compound,"func_150297_b","hasKey",String.class,int.class);
        getCompound=m(compound,"func_74775_l","getCompoundTag",String.class);getLong=m(compound,"func_74763_f","getLong",String.class);
        setLong=m(compound,"func_74772_a","setLong",String.class,long.class);setTag=m(compound,"func_74782_a","setTag",String.class,Class.forName("net.minecraft.nbt.NBTBase"));
        Class<?> sender=Class.forName("net.minecraft.command.ICommandSender"),command=Class.forName("net.minecraft.command.ICommand");
        send=m(sender,"func_145747_a","sendMessage",Class.forName("net.minecraft.util.text.ITextComponent"));
        text=Class.forName("net.minecraft.util.text.TextComponentString").getConstructor(String.class);
        commandName=m(command,"func_71517_b","getName");
        Object manager=m(mc,"func_71187_D","getCommandManager").invoke(server);
        Map<?,?> commands=(Map<?,?>)m(Class.forName("net.minecraft.command.ICommandManager"),"func_71555_a","getCommands").invoke(manager);
        if(commands.containsKey(COMMAND))throw new IllegalStateException("Guide command already registered");
        Object proxy=Proxy.newProxyInstance(command.getClassLoader(),new Class<?>[]{command},new InvocationHandler(){
            public Object invoke(Object proxy,Method method,Object[] args)throws Throwable {
                String n=method.getName();
                if(n.equals("func_71517_b")||n.equals("getName")||n.equals("toString"))return COMMAND;
                if(n.equals("func_71518_a")||n.equals("getUsage"))return "/"+COMMAND;
                if(n.equals("func_71514_a")||n.equals("getAliases")||n.equals("func_184883_a")||n.equals("getTabCompletions"))return Collections.emptyList();
                if(n.equals("func_184882_a")||n.equals("checkPermission"))return true;
                if(n.equals("func_82358_a")||n.equals("isUsernameIndex"))return false;
                if(n.equals("compareTo"))return COMMAND.compareTo(commandName.invoke(args[0]).toString());
                if(n.equals("equals"))return proxy==args[0];if(n.equals("hashCode"))return System.identityHashCode(proxy);
                if(n.equals("func_184881_a")||n.equals("execute")) {
                    if(((String[])args[2]).length!=0){send.invoke(args[1],text.newInstance("/"+COMMAND));return null;}
                    try{guide(args[1],false);}catch(Exception error){warn(error);}return null;
                }
                throw new UnsupportedOperationException("Unknown guide command method");
            }
        });
        m(manager.getClass(),"func_71560_a","registerCommand",command).invoke(manager,proxy);
    }
    private static Method m(Class<?> type,String srg,String mcp,Class<?>...args)throws Exception {
        try{return type.getMethod(srg,args);}catch(NoSuchMethodException e){return type.getMethod(mcp,args);}
    }
    public static void install(Path config,Logger log)throws Exception {
        WelcomePolicy p=WelcomePolicy.read(config,System.getenv());
        if(p==null||!p.enabled){CoreServices.report("core.welcome","disabled");return;}
        active=new WelcomeChat(config,p,log);MinecraftForge.EVENT_BUS.register(active);CoreServices.report("core.welcome","enabled");
    }
    public static void stop(){if(active!=null){MinecraftForge.EVENT_BUS.unregister(active);active=null;}}
    @SubscribeEvent public void login(PlayerEvent.PlayerLoggedInEvent event) {
        try {Object player=PlayerEvent.class.getField("player").get(event);
            if(playerType.isInstance(player)&&!queue.login((UUID)uuid.invoke(player),System.nanoTime(),policy.delay))throw new IllegalStateException("Guide pending queue full");
        }catch(Exception error){warn(error);}
    }
    @SubscribeEvent public void logout(PlayerEvent.PlayerLoggedOutEvent event) {
        try{queue.logout((UUID)uuid.invoke(PlayerEvent.class.getField("player").get(event)));}catch(Exception error){warn(error);}
    }
    @SubscribeEvent public void tick(TickEvent.ServerTickEvent event) {
        if(event.phase!=TickEvent.Phase.END)return;
        for(UUID id:queue.due(System.nanoTime()))try{
            Object player=byUuid.invoke(playerList.invoke(server),id);if(player!=null)guide(player,true);
        }catch(Exception error){warn(error);}
    }
    private Object child(Object parent,String key)throws Exception {
        if(Boolean.TRUE.equals(has.invoke(parent,key))&&!Boolean.TRUE.equals(typed.invoke(parent,key,10)))throw new IllegalStateException("Invalid guide compound");
        return getCompound.invoke(parent,key);
    }
    private long timestamp(Object tag,String key)throws Exception {
        if(Boolean.TRUE.equals(has.invoke(tag,key))&&!Boolean.TRUE.equals(typed.invoke(tag,key,4)))throw new IllegalStateException("Invalid guide timestamp type");
        long value=((Number)getLong.invoke(tag,key)).longValue();if(value<0)throw new IllegalStateException("Invalid guide timestamp");return value;
    }
    private void guide(Object player,boolean automatic)throws Exception {
        if(playerType.isInstance(player)) {
            long now=System.currentTimeMillis()/1000;
            Object root=entityData.invoke(player),persisted=child(root,ROOT),tag=child(persisted,KEY);
            long last=timestamp(tag,automatic?"last_auto":"last_help");
            if(automatic) {
                Object ticks=readStat.invoke(statistics.invoke(player),stat);
                if(!(ticks instanceof Integer)||((Integer)ticks)<0)throw new IllegalStateException("Unknown guide play ticks");
                if(!policy.automatic((Integer)ticks,now,last))return;
            } else if(!WelcomePolicy.elapsed(now,last,policy.helpCooldown))return;
            // Fence before sending: a partial chat send must not be retried in this session.
            setLong.invoke(tag,"last_auto",now);setLong.invoke(tag,"last_help",now);
            setTag.invoke(persisted,KEY,tag);setTag.invoke(root,ROOT,persisted);
            queue.logout((UUID)uuid.invoke(player));
        }
        for(String line:policy.lines)send.invoke(player,text.newInstance(line));
    }
    private void warn(Exception error) {
        long now=System.nanoTime();if(lastWarning==Long.MIN_VALUE||now-lastWarning>=60000000000L){lastWarning=now;log.warn("Omkality guide skipped: {}",error.getClass().getSimpleName());}
    }
}
