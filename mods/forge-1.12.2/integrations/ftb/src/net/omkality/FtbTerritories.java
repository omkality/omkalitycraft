package net.omkality;

import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import com.feed_the_beast.ftblib.lib.data.ForgePlayer;
import com.feed_the_beast.ftblib.lib.data.ForgeTeam;
import com.feed_the_beast.ftblib.lib.data.Universe;
import com.feed_the_beast.ftblib.lib.math.ChunkDimPos;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.CommandEvent;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.eventhandler.Event;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.relauncher.Side;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Optional FTB policy. Native FTB owns storage, authorization and mutations. */
public final class FtbTerritories {
    @SuppressWarnings("unused") private static FtbTerritories active;
    private final int perMember,packetLimit,graphLimit;
    private final Logger log;
    private boolean failed;
    private final Class<?> claimEvent,messageType,playerType;
    private final Method eventActor,eventPosition,getTeamChunks,getPos,getTeam,canModify,getForgePlayer;
    private final Method messageOnServer,worldThread,schedule,send,commandName,entityId,nullablePlayer;
    private final Field action,requested,chunkX,chunkZ,dimension,contextHandler,connectionPlayer,treeMirror,leafMirror;
    private final Constructor<?> playerPosition,text;
    private final Map<Integer,Long> notices=new HashMap<Integer,Long>();
    private final String unclaimPermission;

    public static void install(Path config,Logger logger)throws Exception{
        Path file=config.resolve("omkalitycore-territories.properties");
        if(!Files.exists(file,LinkOption.NOFOLLOW_LINKS)){CoreServices.report("ftb.territories","not configured");return;}
        if(!Files.isRegularFile(file,LinkOption.NOFOLLOW_LINKS)||Files.size(file)>4096)throw new IllegalArgumentException("Invalid territory policy file");
        Properties p=new Properties();try(java.io.Reader in=Files.newBufferedReader(file,StandardCharsets.UTF_8)){p.load(in);}
        Set<String> allowed=new HashSet<String>(Arrays.asList("schema","regions_per_member","max_request_chunks","max_graph_chunks"));
        if(!"1".equals(p.getProperty("schema"))||!allowed.containsAll(p.stringPropertyNames()))throw new IllegalArgumentException("Invalid territory policy schema");
        FtbTerritories guard=new FtbTerritories(number(p,"regions_per_member",3,1,50),number(p,"max_request_chunks",1024,1,4096),number(p,"max_graph_chunks",20000,50,100000),logger);
        guard.installPacketAdapter();MinecraftForge.EVENT_BUS.register(guard);active=guard;
        CoreServices.report("ftb.territories","enabled");logger.info("Omkality FTB territory quota enabled: {} per member",guard.perMember);
    }
    private static int number(Properties p,String key,int fallback,int min,int max){
        String raw=p.getProperty(key,Integer.toString(fallback));if(!raw.matches("[0-9]{1,6}"))throw new IllegalArgumentException("Invalid territory policy integer: "+key);
        int n=Integer.parseInt(raw);if(n<min||n>max)throw new IllegalArgumentException("Territory policy out of range: "+key);return n;
    }
    private static Field field(Class<?> type,String name)throws Exception{Field f=type.getDeclaredField(name);f.setAccessible(true);return f;}
    private static void pin(Class<?> type,String expected)throws Exception{
        java.net.URL location=type.getProtectionDomain().getCodeSource().getLocation();
        if("jar".equals(location.getProtocol()))location=((java.net.JarURLConnection)location.openConnection()).getJarFileURL();
        if(!"file".equals(location.getProtocol()))throw new IllegalStateException("Territory adapter requires a local JAR");
        Path file=Paths.get(location.toURI());if(!Files.isRegularFile(file))throw new IllegalStateException("Territory adapter needs a reviewed JAR");
        byte[] digest=MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file));StringBuilder hex=new StringBuilder();
        for(byte b:digest)hex.append(String.format(Locale.ROOT,"%02x",b&255));if(!expected.equals(hex.toString()))throw new IllegalStateException("Unreviewed territory adapter artifact");
    }
    private FtbTerritories(int per,int pack,int graph,Logger logger)throws Exception{
        perMember=per;packetLimit=pack;graphLimit=graph;log=logger;
        Class<?> claims=Class.forName("com.feed_the_beast.ftbutilities.data.ClaimedChunks");
        pin(claims,"e458fe39aba9ba28122496e54f826e4f61df515ed1f8d0c70cc9e56f67a5404a");
        pin(ForgeTeam.class,"623fc574f0227fec6cc9e26c3879a605f9b4499c0078ff085291901a5495a6ac");
        claimEvent=Class.forName("com.feed_the_beast.ftbutilities.events.chunks.ChunkModifiedEvent$Claim");
        eventActor=claimEvent.getMethod("getPlayer");eventPosition=claimEvent.getMethod("getChunkDimPos");
        getPos=Class.forName("com.feed_the_beast.ftbutilities.data.ClaimedChunk").getMethod("getPos");
        getTeam=claims.getMethod("getChunkTeam",ChunkDimPos.class);getTeamChunks=claims.getMethod("getTeamChunks",ForgeTeam.class,OptionalInt.class,boolean.class);
        canModify=claims.getMethod("canPlayerModify",ForgePlayer.class,ChunkDimPos.class,String.class);
        unclaimPermission=(String)Class.forName("com.feed_the_beast.ftbutilities.FTBUtilitiesPermissions").getField("CLAIMS_OTHER_UNCLAIM").get(null);
        treeMirror=Class.forName("com.feed_the_beast.ftbutilities.ranks.CommandTreeOverride").getField("mirrored");
        leafMirror=Class.forName("com.feed_the_beast.ftbutilities.ranks.CommandOverride").getField("mirrored");
        playerType=Class.forName("net.minecraft.entity.player.EntityPlayerMP");getForgePlayer=Universe.class.getMethod("getPlayer",Class.forName("net.minecraft.command.ICommandSender"));
        playerPosition=ChunkDimPos.class.getConstructor(Class.forName("net.minecraft.entity.Entity"));
        messageType=Class.forName("com.feed_the_beast.ftbutilities.net.MessageClaimedChunksModify");action=field(messageType,"action");requested=field(messageType,"chunks");
        Class<?> pos=Class.forName("net.minecraft.util.math.ChunkPos");chunkX=pos.getField("field_77276_a");chunkZ=pos.getField("field_77275_b");
        dimension=Class.forName("net.minecraft.entity.Entity").getField("field_71093_bK");
        // Reflect fields only: enumerating MessageContext methods resolves its
        // client-only return type on a dedicated Forge server.
        Class<?> ctx=Class.forName("net.minecraftforge.fml.common.network.simpleimpl.MessageContext");contextHandler=ctx.getField("netHandler");
        connectionPlayer=Class.forName("net.minecraft.network.NetHandlerPlayServer").getField("field_147369_b");
        worldThread=FMLCommonHandler.class.getMethod("getWorldThread",Class.forName("net.minecraft.network.INetHandler"));
        schedule=Class.forName("net.minecraft.util.IThreadListener").getMethod("func_152344_a",Runnable.class);messageOnServer=messageType.getMethod("onMessage",playerType);
        send=Class.forName("net.minecraft.command.ICommandSender").getMethod("func_145747_a",Class.forName("net.minecraft.util.text.ITextComponent"));
        text=Class.forName("net.minecraft.util.text.TextComponentString").getConstructor(String.class);commandName=Class.forName("net.minecraft.command.ICommand").getMethod("func_71517_b");
        entityId=Class.forName("net.minecraft.entity.Entity").getMethod("func_145782_y");nullablePlayer=ForgePlayer.class.getMethod("getNullablePlayer");
    }
    private void installPacketAdapter()throws Exception{
        Object wrapper=field(Class.forName("com.feed_the_beast.ftbutilities.net.FTBUtilitiesNetHandler"),"CLAIMS").get(null);
        Object channel=wrapper.getClass().getMethod("getChannel",Side.class).invoke(wrapper,Side.SERVER);
        Object pipeline=Class.forName("io.netty.channel.Channel").getMethod("pipeline").invoke(channel);
        Class<?> pt=Class.forName("io.netty.channel.ChannelPipeline"),ht=Class.forName("io.netty.channel.ChannelHandler"),mh=Class.forName("net.minecraftforge.fml.common.network.simpleimpl.IMessageHandler");
        String name=messageType.getName();Object old=pt.getMethod("get",String.class).invoke(pipeline,name);
        Class<?> nw=Class.forName("net.minecraftforge.fml.common.network.simpleimpl.SimpleChannelHandlerWrapper");
        if(old==null||old.getClass()!=nw)throw new IllegalStateException("Unexpected FTB request handler");
        Object handler=Proxy.newProxyInstance(mh.getClassLoader(),new Class<?>[]{mh},new InvocationHandler(){public Object invoke(Object proxy,Method method,Object[] args)throws Throwable{
            if(method.getDeclaringClass()==Object.class){if("hashCode".equals(method.getName()))return System.identityHashCode(proxy);if("equals".equals(method.getName()))return proxy==args[0];return "Omkality FTB territory handler";}
            final Object message=args[0],context=args[1];Object thread=worldThread.invoke(FMLCommonHandler.instance(),contextHandler.get(context));
            schedule.invoke(thread,new Runnable(){public void run(){Object actor=null;try{
                actor=connectionPlayer.get(contextHandler.get(context));if(preparePacket(message,actor))messageOnServer.invoke(message,actor);
            }catch(Exception error){fault(error);try{notice(actor,"Проверка территорий временно недоступна.");}catch(Exception ignored){}}}});return null;
        }});
        Object replacement=nw.getConstructor(mh,Side.class,Class.class).newInstance(handler,Side.SERVER,messageType);
        pt.getMethod("replace",String.class,String.class,ht).invoke(pipeline,name,name,replacement);
    }
    private Set<ClaimTopology.Point> snapshot(Object claims,ForgeTeam team)throws Exception{
        Collection<?> chunks=(Collection<?>)getTeamChunks.invoke(claims,team,OptionalInt.empty(),true);if(chunks.size()>graphLimit)throw new IllegalStateException("Territory graph bound exceeded");
        Set<ClaimTopology.Point> result=new HashSet<ClaimTopology.Point>();for(Object c:chunks)result.add(point((ChunkDimPos)getPos.invoke(c)));return result;
    }
    private static ClaimTopology.Point point(ChunkDimPos p){return new ClaimTopology.Point(p.posX,p.posZ,p.dim);}
    private boolean allow(ForgeTeam team,Set<ClaimTopology.Point> before,Set<ClaimTopology.Point> after,Object actor)throws Exception{
        if(team.type.isServer)return true;int a=ClaimTopology.components(before),b=ClaimTopology.components(after);long max=(long)perMember*team.getMembers().size();
        if(ClaimTopology.permitted(a,b,max))return true;
        notice(actor,"Лимит отдельных территорий: "+b+" / "+max+" (по "+perMember+" на участника). Соедините участки или освободите целую территорию.");return false;
    }
    @SubscribeEvent(priority=EventPriority.LOWEST)
    public void claim(Event event){
        if(!claimEvent.isInstance(event))return;
        try{ForgePlayer actor=(ForgePlayer)eventActor.invoke(event);if(actor.team.type.isServer)return;if(failed){event.setCanceled(true);return;}
            Object claims=FtbClaimDomains.flush();ChunkDimPos pos=(ChunkDimPos)eventPosition.invoke(event);
            if(getTeam.invoke(claims,pos)!=null){event.setCanceled(true);return;}
            Set<ClaimTopology.Point> before=snapshot(claims,actor.team),after=new HashSet<ClaimTopology.Point>(before);after.add(point(pos));
            if(!allow(actor.team,before,after,nullablePlayer.invoke(actor)))event.setCanceled(true);
        }catch(Exception error){fault(error);event.setCanceled(true);}
    }
    private boolean preparePacket(Object message,Object actor)throws Exception{
        int mode=action.getInt(message);if(mode==2||mode==3)return true;if(mode!=0&&mode!=1)return false;if(failed)return false;
        Collection<?> raw=(Collection<?>)requested.get(message);if(raw==null||raw.size()>packetLimit){notice(actor,"Слишком большая область. Выберите меньше чанков.");return false;}
        ForgePlayer player=(ForgePlayer)getForgePlayer.invoke(Universe.get(),actor);if(!player.hasTeam())return true;
        Object claims=FtbClaimDomains.flush();int dim=dimension.getInt(actor);Map<ClaimTopology.Point,Object> originals=new TreeMap<ClaimTopology.Point,Object>();
        for(Object pos:raw)originals.put(new ClaimTopology.Point(chunkX.getInt(pos),chunkZ.getInt(pos),dim),pos);
        if(mode==0){
            List<Object> sorted=new ArrayList<Object>();for(ClaimTopology.Point p:ClaimTopology.orderAdds(snapshot(claims,player.team),originals.keySet()))sorted.add(originals.get(p));
            requested.set(message,sorted);return true; // Native pre-claim event checks every actual addition.
        }
        Map<ForgeTeam,Set<ClaimTopology.Point>> before=new HashMap<ForgeTeam,Set<ClaimTopology.Point>>(),after=new HashMap<ForgeTeam,Set<ClaimTopology.Point>>();
        for(ClaimTopology.Point p:originals.keySet()){
            ChunkDimPos pos=new ChunkDimPos(p.x,p.z,p.dim);if(!Boolean.TRUE.equals(canModify.invoke(claims,player,pos,unclaimPermission)))continue;
            ForgeTeam team=(ForgeTeam)getTeam.invoke(claims,pos);if(team==null||team.type.isServer)continue;
            if(!before.containsKey(team)){Set<ClaimTopology.Point> current=snapshot(claims,team);before.put(team,current);after.put(team,new HashSet<ClaimTopology.Point>(current));}
            after.get(team).remove(p);
        }
        for(ForgeTeam team:before.keySet())if(!allow(team,before.get(team),after.get(team),actor))return false;return true;
    }
    @SubscribeEvent(priority=EventPriority.HIGHEST)
    public void command(CommandEvent event){
        boolean relevant=false;
        try{Object command=CommandEvent.class.getMethod("getCommand").invoke(event),actor=CommandEvent.class.getMethod("getSender").invoke(event);if(!playerType.isInstance(actor))return;
            String name=commandName.invoke(command).toString();if(!name.equals("chunks")&&!name.equals("unclaim"))return;
            // FTB ranks wrap both roots and leaves. Inspect the pinned native
            // command, but leave permission checks and execution on its wrapper.
            if(treeMirror.getDeclaringClass().isInstance(command))command=treeMirror.get(command);
            else if(leafMirror.getDeclaringClass().isInstance(command))command=leafMirror.get(command);
            String[] args=event.getParameters();String type=command.getClass().getName();
            relevant=type.equals("com.feed_the_beast.ftbutilities.command.chunks.CmdUnclaim")||(type.equals("com.feed_the_beast.ftbutilities.command.chunks.CmdChunks")&&name.equals("chunks")&&args.length>0&&args[0].equals("unclaim"));
            if(!relevant)return;if(failed){event.setCanceled(true);return;}
            ForgePlayer player=(ForgePlayer)getForgePlayer.invoke(Universe.get(),actor);Object claims=FtbClaimDomains.flush();ChunkDimPos pos=(ChunkDimPos)playerPosition.newInstance(actor);
            if(!Boolean.TRUE.equals(canModify.invoke(claims,player,pos,unclaimPermission)))return;
            ForgeTeam team=(ForgeTeam)getTeam.invoke(claims,pos);if(team==null||team.type.isServer)return;
            Set<ClaimTopology.Point> before=snapshot(claims,team),after=new HashSet<ClaimTopology.Point>(before);after.remove(point(pos));if(!allow(team,before,after,actor))event.setCanceled(true);
        }catch(Exception error){fault(error);if(relevant)event.setCanceled(true);}
    }
    private void notice(Object actor,String value)throws Exception{
        if(actor==null)return;int id=((Number)entityId.invoke(actor)).intValue();long now=System.currentTimeMillis();Long last=notices.get(id);
        if(last!=null&&now-last<1500)return;if(notices.size()>=256)notices.clear();notices.put(id,now);send.invoke(actor,text.newInstance(value));
    }
    private void fault(Exception error){if(!failed){failed=true;CoreServices.report("ftb.territories","failed closed");log.error("Omkality territory quota adapter failed; claim changes denied",error);}}
}
