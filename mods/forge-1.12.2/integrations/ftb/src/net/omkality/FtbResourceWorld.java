package net.omkality;

import java.io.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.function.Function;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.CommandEvent;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.eventhandler.EventPriority;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Optional JED resource entry. FTB owns SPAWN permission, timer and history. */
public final class FtbResourceWorld {
    private final Logger log;
    private final int dimension,centerX,centerZ,radius,step,loadBudget;
    private final long seed;
    private final String command,identity;
    private final Path folder,marker,ledger;
    private final Object server,timer,nativeSpawn;
    private final Class<?> player,source,commandType;
    private final Field entityDimension,entityX,entityY,entityZ;
    private final Method worldGet,worldInit,info,worldSeed,terrainType,terrainName,providerFolder;
    private final Method chunkProvider,queueUnload;
    private final Field worldPlayers;
    private final Method spawn,getX,getY,getZ,setSpawn,chunk,top,blockState,air,full,block,registry,worldBorder,contains;
    private final Method dataGet,forgePlayer,online,permission,alive,health,cooldown,teleport,rank,ticks,seconds;
    private final Method send,commandName,eventCommand,eventSender,nativeArgs,destination;
    private final Constructor<?> position,plain,translation;
    private final Map<Object,Pending> pending=new WeakHashMap<Object,Pending>();
    private boolean failed;
    private int targetX,targetY,targetZ;

    private static final class Pending {
        final int dim,x,y,z;final float hp;final long until;
        Pending(int d,int a,int b,int c,float h,long u){dim=d;x=a;y=b;z=c;hp=h;until=u;}
    }
    private static Class<?> c(String name)throws Exception{return Class.forName(name);}
    private static Method m(String type,String name,Class<?>... args)throws Exception{return c(type).getMethod(name,args);}
    private static int integer(Properties p,String key,int low,int high){
        String s=p.getProperty(key);if(s==null||!s.matches("-?[0-9]{1,10}"))throw new IllegalArgumentException("Invalid resource integer: "+key);
        int n=Integer.parseInt(s);if(n<low||n>high)throw new IllegalArgumentException("Resource integer out of range: "+key);return n;
    }
    private static Properties properties(Path file)throws Exception{
        if(!Files.isRegularFile(file,LinkOption.NOFOLLOW_LINKS)||Files.size(file)>4096)throw new IllegalArgumentException("Invalid resource policy or marker");
        Properties p=new Properties();try(Reader in=Files.newBufferedReader(file,StandardCharsets.UTF_8)){p.load(in);}return p;
    }
    private static String sha(Path file)throws Exception{
        byte[] raw=MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file));StringBuilder out=new StringBuilder();
        for(byte b:raw)out.append(String.format(Locale.ROOT,"%02x",b&255));return out.toString();
    }
    private static void pin(Class<?> type,String expected)throws Exception{
        java.net.URL location=type.getProtectionDomain().getCodeSource().getLocation();
        if("jar".equals(location.getProtocol()))location=((java.net.JarURLConnection)location.openConnection()).getJarFileURL();
        if(!"file".equals(location.getProtocol())||!expected.equals(sha(Paths.get(location.toURI()))))throw new IllegalStateException("Unreviewed resource adapter artifact");
    }
    public static FtbResourceWorld prepare(Path config,Logger log)throws Exception{
        Path file=config.resolve("omkalitycore-resource.properties");
        if(!Files.exists(file,LinkOption.NOFOLLOW_LINKS)){CoreServices.report("ftb.resource","not configured");return null;}
        return new FtbResourceWorld(config,properties(file),log);
    }
    private FtbResourceWorld(Path config,Properties p,Logger logger)throws Exception{
        log=logger;
        Set<String> keys=new HashSet<String>(Arrays.asList("schema","dimension","seed","command","identity","jed_config_sha256","spawn_x","spawn_z","search_radius","search_step","chunk_loads"));
        if(!"1".equals(p.getProperty("schema"))||!p.stringPropertyNames().equals(keys))throw new IllegalArgumentException("Invalid resource policy schema");
        dimension=integer(p,"dimension",-32000,-2);centerX=integer(p,"spawn_x",-100000,100000);centerZ=integer(p,"spawn_z",-100000,100000);
        radius=integer(p,"search_radius",2,256);step=integer(p,"search_step",1,32);loadBudget=integer(p,"chunk_loads",1,64);
        if((2L*radius/step+1)*(2L*radius/step+1)>1024)throw new IllegalArgumentException("Resource search bound exceeded");
        String seedText=p.getProperty("seed");if(!seedText.matches("-?[0-9]{1,19}"))throw new IllegalArgumentException("Invalid resource seed");seed=Long.parseLong(seedText);
        command=p.getProperty("command");identity=p.getProperty("identity");
        if(!command.matches("[a-z]{3,16}")||!identity.matches("[a-z0-9_.-]{3,64}"))throw new IllegalArgumentException("Invalid resource identity or command");
        Path json=config.resolve("justenoughdimensions/dimensions.json");String digest=p.getProperty("jed_config_sha256");
        if(!digest.matches("[a-f0-9]{64}")||!Files.isRegularFile(json,LinkOption.NOFOLLOW_LINKS)||Files.size(json)>65536||!sha(json).equals(digest))throw new IllegalStateException("Resource dimension configuration changed");
        FtbMuteGuard.requireVersion("justenoughdimensions","1.6.0-dev.20211009.214847");
        pin(c("fi.dy.masa.justenoughdimensions.JustEnoughDimensions"),"6840d8ad69059f90c4288c317bf88284a4ccd716d06cc0aa0d37d20b2693dd8f");
        pin(c("com.feed_the_beast.ftbutilities.data.FTBUtilitiesPlayerData"),"e458fe39aba9ba28122496e54f826e4f61df515ed1f8d0c70cc9e56f67a5404a");
        pin(c("com.feed_the_beast.ftblib.lib.data.Universe"),"623fc574f0227fec6cc9e26c3879a605f9b4499c0078ff085291901a5495a6ac");
        Class<?> options=c("fi.dy.masa.justenoughdimensions.config.Configs");
        for(String key:new String[]{"enableReplacingRegisteredDimensions","enableUnregisteringDimensions","usePerWorldDimensionConfig","usePerWorldMainConfig","copyDimensionConfigToWorld","copyMainConfigToWorld","enableCommandRedirecting"})
            if(options.getField(key).getBoolean(null))throw new IllegalStateException("Unreviewed resource dimension option: "+key);
        if(!options.getField("enableSeparateWorldInfo").getBoolean(null)||!options.getField("enableSeparateWorldBorders").getBoolean(null))throw new IllegalStateException("Resource world isolation disabled");
        if(!Boolean.TRUE.equals(m("net.minecraftforge.common.DimensionManager","isDimensionRegistered",int.class).invoke(null,dimension)))throw new IllegalStateException("Resource dimension not registered");
        Object type=m("net.minecraftforge.common.DimensionManager","getProviderType",int.class).invoke(null,dimension);
        Field clazz=c("net.minecraft.world.DimensionType").getDeclaredField("field_186077_g");clazz.setAccessible(true);
        if(!((Class<?>)clazz.get(type)).getName().equals("fi.dy.masa.justenoughdimensions.world.WorldProviderSurfaceJED"))throw new IllegalStateException("Resource dimension belongs to another provider");

        player=c("net.minecraft.entity.player.EntityPlayerMP");source=c("net.minecraft.command.ICommandSender");commandType=c("net.minecraft.command.ICommand");
        entityDimension=c("net.minecraft.entity.Entity").getField("field_71093_bK");entityX=c("net.minecraft.entity.Entity").getField("field_70165_t");entityY=c("net.minecraft.entity.Entity").getField("field_70163_u");entityZ=c("net.minecraft.entity.Entity").getField("field_70161_v");
        worldGet=m("net.minecraftforge.common.DimensionManager","getWorld",int.class);worldInit=m("net.minecraftforge.common.DimensionManager","initDimension",int.class);
        chunkProvider=m("net.minecraft.world.World","func_72863_F");queueUnload=m("net.minecraft.world.gen.ChunkProviderServer","func_73240_a");worldPlayers=c("net.minecraft.world.World").getField("field_73010_i");
        info=m("net.minecraft.world.World","func_72912_H");worldSeed=m("net.minecraft.world.World","func_72905_C");
        terrainType=m("net.minecraft.world.storage.WorldInfo","func_76067_t");terrainName=m("net.minecraft.world.WorldType","func_77127_a");providerFolder=m("net.minecraft.world.WorldProvider","getSaveFolder");
        position=c("net.minecraft.util.math.BlockPos").getConstructor(int.class,int.class,int.class);Class<?> pos=position.getDeclaringClass();
        spawn=m("net.minecraft.world.World","func_175694_M");getX=pos.getMethod("func_177958_n");getY=pos.getMethod("func_177956_o");getZ=pos.getMethod("func_177952_p");setSpawn=m("net.minecraft.world.World","func_175652_B",pos);
        chunk=m("net.minecraft.world.World","func_72964_e",int.class,int.class);top=m("net.minecraft.world.World","func_175672_r",pos);blockState=m("net.minecraft.world.World","func_180495_p",pos);air=m("net.minecraft.world.World","func_175623_d",pos);
        full=m("net.minecraft.block.state.IBlockState","func_185913_b");block=m("net.minecraft.block.state.IBlockState","func_177230_c");registry=m("net.minecraft.block.Block","getRegistryName");
        worldBorder=m("net.minecraft.world.World","func_175723_af");contains=m("net.minecraft.world.border.WorldBorder","func_177746_a",pos);
        forgePlayer=m("com.feed_the_beast.ftblib.lib.command.CommandUtils","getForgePlayer",source);online=forgePlayer.getReturnType().getMethod("getNullablePlayer");
        dataGet=m("com.feed_the_beast.ftbutilities.data.FTBUtilitiesPlayerData","get",forgePlayer.getReturnType());
        Class<?> timers=c("com.feed_the_beast.ftbutilities.data.FTBUtilitiesPlayerData$Timer");timer=timers.getField("SPAWN").get(null);
        cooldown=dataGet.getReturnType().getMethod("checkTeleportCooldown",source,timers);teleport=timers.getMethod("teleport",player,Function.class,c("com.feed_the_beast.ftblib.lib.util.misc.IScheduledTask"));
        rank=m("com.feed_the_beast.ftblib.lib.config.RankConfigAPI","get",player,String.class);ticks=m("com.feed_the_beast.ftblib.lib.config.ConfigValue","getTimer");seconds=ticks.getReturnType().getMethod("seconds");
        permission=commandType.getMethod("func_184882_a",c("net.minecraft.server.MinecraftServer"),source);alive=m("net.minecraft.entity.Entity","func_70089_S");health=m("net.minecraft.entity.EntityLivingBase","func_110143_aJ");
        send=source.getMethod("func_145747_a",c("net.minecraft.util.text.ITextComponent"));plain=c("net.minecraft.util.text.TextComponentString").getConstructor(String.class);translation=c("net.minecraft.util.text.TextComponentTranslation").getConstructor(String.class,Object[].class);
        commandName=commandType.getMethod("func_71517_b");eventCommand=CommandEvent.class.getMethod("getCommand");eventSender=CommandEvent.class.getMethod("getSender");nativeArgs=m("net.minecraft.command.CommandException","func_74844_a");
        destination=m("com.feed_the_beast.ftblib.lib.math.TeleporterDimPos","of",double.class,double.class,double.class,int.class);
        server=FMLCommonHandler.instance().getMinecraftServerInstance();
        Object manager=m("net.minecraft.server.MinecraftServer","func_71187_D").invoke(server);
        nativeSpawn=((Map<?,?>)m("net.minecraft.command.ICommandManager","func_71555_a").invoke(manager)).get("spawn");
        if(nativeSpawn==null)throw new IllegalStateException("Native FTB spawn command unavailable");
        Object original=nativeSpawn;
        if(original.getClass().getName().equals("com.feed_the_beast.ftbutilities.ranks.CommandOverride"))original=original.getClass().getField("mirrored").get(original);
        if(!original.getClass().getName().equals("com.feed_the_beast.ftbutilities.command.tp.CmdSpawn"))throw new IllegalStateException("Spawn command is not the reviewed FTB implementation");
        Object main=worldGet.invoke(null,0),save=m("net.minecraft.world.World","func_72860_G").invoke(main);
        Path root=((File)m("net.minecraft.world.storage.ISaveHandler","func_75765_b").invoke(save)).toPath().toAbsolutePath().normalize();
        folder=root.resolve("DIM"+dimension);marker=folder.resolve(".omk-resource.properties");ledger=root.resolve("omk-resource-world.properties");
        boolean existed=Files.exists(folder,LinkOption.NOFOLLOW_LINKS),recorded=Files.exists(ledger,LinkOption.NOFOLLOW_LINKS);
        if(recorded&&!existed)throw new IllegalStateException("Resource dimension data missing; recorded reset or recovery required");
        if(existed&&!recorded)throw new IllegalStateException("Existing resource dimension has no ownership record");
        if(existed)verifyMarker();
        Object world=loadWorld();
        if(info.invoke(world)==info.invoke(main)||((Number)worldSeed.invoke(world)).longValue()!=seed||!"default".equals(terrainName.invoke(terrainType.invoke(info.invoke(world)))))throw new IllegalStateException("Unexpected resource world metadata");
        Object provider=c("net.minecraft.world.World").getField("field_73011_w").get(world);
        if(!("DIM"+dimension).equals(providerFolder.invoke(provider)))throw new IllegalStateException("Unexpected resource save directory");
        if(!existed){
            if(!Files.isDirectory(folder,LinkOption.NOFOLLOW_LINKS))throw new IllegalStateException("Resource directory was not created by JED");
            byte[] ownership=("schema=1\nidentity="+identity+"\ndimension="+dimension+"\nseed="+seed+"\n").getBytes(StandardCharsets.US_ASCII);
            writeOwnership(marker,ownership);writeOwnership(ledger,ownership);
        }
        if(!findSpawn(world,false))throw new IllegalStateException("No safe resource entry inside the bounded spawn search");
        log.info("Omkality resource world verified: dimension {}, folder {}, safe entry ({}, {}, {})",dimension,folder.getFileName(),targetX,targetY,targetZ);
    }
    private void verifyMarker()throws Exception{
        if(!Files.isDirectory(folder,LinkOption.NOFOLLOW_LINKS)||Files.isSymbolicLink(folder))throw new IllegalStateException("Linked resource dimension directory");
        verifyOwnership(properties(marker));verifyOwnership(properties(ledger));
    }
    private void verifyOwnership(Properties p){
        if(p.size()!=4||!"1".equals(p.getProperty("schema"))||!identity.equals(p.getProperty("identity"))||!Integer.toString(dimension).equals(p.getProperty("dimension"))||!Long.toString(seed).equals(p.getProperty("seed")))throw new IllegalStateException("Existing resource dimension is not owned by this policy");
    }
    private static void writeOwnership(Path file,byte[] bytes)throws Exception{
        try(java.nio.channels.FileChannel channel=java.nio.channels.FileChannel.open(file,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){
            java.nio.ByteBuffer data=java.nio.ByteBuffer.wrap(bytes);while(data.hasRemaining())channel.write(data);channel.force(true);
        }
    }
    private Object loadWorld()throws Exception{
        Object world=worldGet.invoke(null,dimension);if(world==null){worldInit.invoke(null,dimension);world=worldGet.invoke(null,dimension);}if(world==null)throw new IllegalStateException("Resource dimension unavailable");return world;
    }
    private void releaseEmpty(Object world)throws Exception{
        // Native queueing preserves Forge tickets; subsequent player chunk
        // requests unqueue their chunks. Never force-unload an occupied world.
        if(((List<?>)worldPlayers.get(world)).isEmpty())queueUnload.invoke(chunkProvider.invoke(world));
    }
    private boolean findSpawn(Object world,boolean protection)throws Exception{
        Set<Long> loaded=new HashSet<Long>();
        Object previous=spawn.invoke(world);int oldX=((Number)getX.invoke(previous)).intValue(),oldY=((Number)getY.invoke(previous)).intValue(),oldZ=((Number)getZ.invoke(previous)).intValue();
        if(Math.abs(oldX-centerX)<=radius&&Math.abs(oldZ-centerZ)<=radius&&populate(world,oldX,oldZ,loaded)&&safe(world,oldX,oldY,oldZ,protection)){targetX=oldX;targetY=oldY;targetZ=oldZ;return true;}
        List<int[]> points=new ArrayList<int[]>();points.add(new int[]{centerX,centerZ});
        for(int r=step;r<=radius;r+=step)for(int a=-r;a<=r;a+=step){points.add(new int[]{centerX+a,centerZ-r});points.add(new int[]{centerX+a,centerZ+r});if(a!=-r&&a!=r){points.add(new int[]{centerX-r,centerZ+a});points.add(new int[]{centerX+r,centerZ+a});}}
        for(int[] p:points){int x=p[0],z=p[1];if(!populate(world,x,z,loaded))continue;
            Object feet=top.invoke(world,position.newInstance(x,0,z));int y=((Number)getY.invoke(feet)).intValue();
            if(safe(world,x,y,z,protection)){targetX=x;targetY=y;targetZ=z;return true;}
        }
        return false;
    }
    private boolean populate(Object world,int x,int z,Set<Long> loaded)throws Exception{
        List<int[]> chunks=new ArrayList<int[]>();
        // Include incoming decoration from negative neighbours and the positive
        // neighbours needed to finish it. Do not select an undecorated edge.
        for(int cx=((x-1)>>4)-1;cx<=((x+1)>>4)+1;cx++)for(int cz=((z-1)>>4)-1;cz<=((z+1)>>4)+1;cz++){
            long key=((long)cx<<32)^(cz&0xffffffffL);if(!loaded.contains(key))chunks.add(new int[]{cx,cz});
        }
        if(loaded.size()+chunks.size()>loadBudget)return false;
        for(int[] q:chunks){chunk.invoke(world,q[0],q[1]);loaded.add(((long)q[0]<<32)^(q[1]&0xffffffffL));}return true;
    }
    private boolean safe(Object world,int x,int y,int z,boolean protection)throws Exception{
        if(y<2||y>251)return false;Object border=worldBorder.invoke(world),claims=protection?FtbClaimDomains.flush():null;
        for(int dx=-1;dx<=1;dx++)for(int dz=-1;dz<=1;dz++){
            Object floor=position.newInstance(x+dx,y-1,z+dz),a=position.newInstance(x+dx,y,z+dz),b=position.newInstance(x+dx,y+1,z+dz);
            if(!Boolean.TRUE.equals(contains.invoke(border,a))||!Boolean.TRUE.equals(air.invoke(world,a))||!Boolean.TRUE.equals(air.invoke(world,b)))return false;
            Object state=blockState.invoke(world,floor);String name=String.valueOf(registry.invoke(block.invoke(state)));
            if(!Boolean.TRUE.equals(full.invoke(state))||name.equals("minecraft:magma")||name.equals("minecraft:cactus")||name.equals("minecraft:fire"))return false;
            if(protection){Object owner=FtbClaimDomains.owner(claims,world,a);if(owner==null||!"omk_spawn".equals(owner.getClass().getMethod("getId").invoke(owner)))return false;}
        }
        return true;
    }
    public void start()throws Exception{
        if(!"enabled".equals(CoreServices.statuses().get("ftb.spawn")))throw new IllegalStateException("Resource entry requires verified server-owned spawn claims");
        if(!safe(loadWorld(),targetX,targetY,targetZ,true))throw new IllegalStateException("Resource entry is not safe and protected");
        Object manager=m("net.minecraft.server.MinecraftServer","func_71187_D").invoke(server);
        Map<?,?> commands=(Map<?,?>)m("net.minecraft.command.ICommandManager","func_71555_a").invoke(manager);
        if(commands.containsKey(command))throw new IllegalStateException("Resource command already registered");
        setSpawn.invoke(loadWorld(),position.newInstance(targetX,targetY,targetZ));
        Object handler=Proxy.newProxyInstance(commandType.getClassLoader(),new Class<?>[]{commandType},new InvocationHandler(){public Object invoke(Object proxy,Method method,Object[] args)throws Throwable{
            String name=method.getName();
            if(name.equals("hashCode"))return System.identityHashCode(proxy);if(name.equals("equals"))return proxy==args[0];if(name.equals("toString"))return command;
            if(name.equals("func_71517_b"))return command;if(name.equals("func_71518_a"))return "/"+command;
            if(name.equals("func_71514_a")||name.equals("func_184883_a"))return Collections.emptyList();
            if(name.equals("func_82358_a"))return false;if(name.equals("compareTo"))return command.compareTo(commandName.invoke(args[0]).toString());
            if(name.equals("func_184882_a"))return permitted(args[1]);
            if(name.equals("func_184881_a")){execute(args[1],(String[])args[2]);return null;}
            throw new IllegalStateException("Unknown native command callback: "+name);
        }});
        m("net.minecraft.command.CommandHandler","func_71560_a",commandType).invoke(manager,handler);
        MinecraftForge.EVENT_BUS.register(this);CoreServices.report("ftb.resource","enabled");
        releaseEmpty(loadWorld());
    }
    private boolean permitted(Object actor)throws Exception{return player.isInstance(actor)&&Boolean.TRUE.equals(permission.invoke(nativeSpawn,server,actor));}
    private int coordinate(Field field,Object actor)throws Exception{return (int)Math.floor(field.getDouble(actor));}
    private boolean pending(Object actor)throws Exception{
        Pending p=pending.get(actor);if(p==null)return false;
        if(System.currentTimeMillis()>p.until||p.dim!=entityDimension.getInt(actor)||p.x!=coordinate(entityX,actor)||p.y!=coordinate(entityY,actor)||p.z!=coordinate(entityZ,actor)||((Number)health.invoke(actor)).floatValue()<p.hp||online.invoke(forgePlayer.invoke(null,actor))!=actor){pending.remove(actor);return false;}return true;
    }
    private void execute(final Object actor,String[] args){
        try{
            if(!permitted(actor)){tell(actor,"Команда недоступна.");return;}
            if(args.length!=0){tell(actor,"Используйте /"+command);return;}
            if(failed){tell(actor,"Ресурсный мир временно недоступен.");return;}
            if(pending(actor)){tell(actor,"Дождитесь завершения телепортации.");return;}
            cooldown.invoke(dataGet.invoke(null,forgePlayer.invoke(null,actor)),actor,timer);
            long warmup=((Number)seconds.invoke(ticks.invoke(rank.invoke(null,actor,"ftbutilities.spawn.warmup")))).longValue();
            final Pending request=new Pending(entityDimension.getInt(actor),coordinate(entityX,actor),coordinate(entityY,actor),coordinate(entityZ,actor),((Number)health.invoke(actor)).floatValue(),System.currentTimeMillis()+Math.max(2000L,warmup*1000L+2000L));pending.put(actor,request);
            Function<Object,Object> target=current->{try{
                if(current!=actor||pending.get(actor)!=request||!pending(actor)||!Boolean.TRUE.equals(alive.invoke(actor))||!permitted(actor))return null;
                cooldown.invoke(dataGet.invoke(null,forgePlayer.invoke(null,actor)),actor,timer);verifyMarker();Object world=loadWorld();
                try{
                if(!safe(world,targetX,targetY,targetZ,true)){
                    if(!findSpawn(world,true)){tell(actor,"Точка входа в ресурсный мир временно недоступна.");return null;}
                    // Obstacles, including a player's grave, are preserved. Only
                    // a verified server-owned destination becomes the new spawn.
                    setSpawn.invoke(world,position.newInstance(targetX,targetY,targetZ));
                }
                return destination.invoke(null,targetX+0.5,targetY+0.01,targetZ+0.5,dimension);
                }finally{releaseEmpty(world);}
            }catch(InvocationTargetException error){if(!nativeError(actor,error))fault(error);return null;}catch(Exception error){fault(error);return null;}finally{pending.remove(actor);}};
            teleport.invoke(timer,actor,target,null);
        }catch(InvocationTargetException error){pending.remove(actor);if(!nativeError(actor,error))fault(error);}catch(Exception error){pending.remove(actor);fault(error);}
    }
    @SubscribeEvent(priority=EventPriority.HIGH)
    public void command(CommandEvent event){try{
        if(!"spawn".equals(commandName.invoke(eventCommand.invoke(event))))return;Object actor=eventSender.invoke(event);
        if(player.isInstance(actor)&&pending(actor)){event.setCanceled(true);tell(actor,"Дождитесь завершения телепортации.");}
    }catch(Exception error){fault(error);}}
    private void tell(Object actor,String message)throws Exception{if(actor!=null)send.invoke(actor,plain.newInstance(message));}
    private boolean nativeError(Object actor,InvocationTargetException error){try{
        Throwable reason=error.getCause();if(nativeArgs.getDeclaringClass().isInstance(reason)){send.invoke(actor,translation.newInstance(reason.getMessage(),nativeArgs.invoke(reason)));return true;}
    }catch(Exception ignored){}return false;}
    private void fault(Exception error){if(!failed){failed=true;pending.clear();CoreServices.report("ftb.resource","failed closed");log.error("Omkality resource entry failed; existing worlds preserved",error);}}
}
