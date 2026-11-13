package net.omkality;

import java.lang.management.*;
import java.lang.reflect.*;
import java.nio.file.Path;
import java.util.*;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.common.gameevent.TickEvent;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Generic Forge 1.12.2 main-thread snapshot, with bounded asynchronous output. */
public final class GameMetrics {
    private static GameMetrics active;
    private final Object server;
    private final Field ticks,worldTicks;
    private final Method playerList,players,dimensionIds;
    private final GameMetricPolicy policy;
    private final String profile,boot=UUID.randomUUID().toString().replace("-","");
    private final Logger logger;
    private final MetricFile output;
    private final TickRateWindow rate;
    private long sequence,observedTicks,lastNanos,lastWarning=Long.MIN_VALUE;
    private boolean closed;
    private String last;
    public static void install(final Logger log,String profile) throws Exception {
        GameMetricPolicy settings=GameMetricPolicy.read(System.getenv());
        if(!settings.enabled) { CoreServices.report("core.metrics","disabled");return; }
        active=new GameMetrics(log,profile,settings);
        MinecraftForge.EVENT_BUS.register(active);
        CoreServices.report("core.metrics","enabled");
    }
    public static void stop() {
        if(active==null) return;
        GameMetrics instance=active;active=null;instance.closed=true;
        MinecraftForge.EVENT_BUS.unregister(instance);
        try { instance.output.offer(instance.snapshot(System.nanoTime()).replace("\"running\":true","\"running\":false")); }
        catch(Exception error) { instance.warn(error.getClass().getSimpleName()); }
        instance.output.close();
    }
    private static Method method(Class<?> type,String srg,String mcp,Class<?>... args) throws Exception {
        try { return type.getMethod(srg,args); }
        catch(NoSuchMethodException missing) { return type.getMethod(mcp,args); }
    }
    private GameMetrics(Logger log,String id,GameMetricPolicy settings) throws Exception {
        logger=log;profile=id;policy=settings;
        rate=new TickRateWindow(policy.tpsWindowSeconds);
        if(!id.matches("[a-z0-9_.-]{1,80}")) throw new IllegalArgumentException("Invalid metrics profile");
        server=FMLCommonHandler.class.getMethod("getMinecraftServerInstance").invoke(FMLCommonHandler.instance());
        Class<?> mc=Class.forName("net.minecraft.server.MinecraftServer");
        Field ring;
        try { ring=mc.getField("field_71311_j"); }
        catch(NoSuchFieldException missing) { ring=mc.getField("tickTimeArray"); }
        ticks=ring;worldTicks=mc.getField("worldTickTimes");
        playerList=method(mc,"func_184103_al","getPlayerList");
        players=method(Class.forName("net.minecraft.server.management.PlayerList"),"func_181057_v","getPlayers");
        dimensionIds=Class.forName("net.minecraftforge.common.DimensionManager").getMethod("getIDs");
        Path directory=policy.directory;MetricFile.createDirectory(directory);
        output=new MetricFile(directory,new MetricFile.Errors() { public void report(String kind) { warn(kind); } });
    }
    private synchronized void warn(String kind) {
        long now=System.nanoTime();
        if(lastWarning==Long.MIN_VALUE || now-lastWarning>=60000000000L) {
            lastWarning=now;logger.warn("Omkality game metrics unavailable ({})",kind);
        }
    }
    @SubscribeEvent
    public void tick(TickEvent.ServerTickEvent event) {
        if(event.phase!=TickEvent.Phase.END || closed) return;
        observedTicks++;
        long now=System.nanoTime();
        if(lastNanos!=0 && now-lastNanos<policy.intervalSeconds*1000000000L) return;
        try { last=snapshot(now);output.offer(last); }
        catch(Exception error) { warn(error.getClass().getSimpleName()); }
        lastNanos=now;
    }
    private String snapshot(long now) throws Exception {
        Object online=players.invoke(playerList.invoke(server));
        if(!(online instanceof List) || ((List<?>)online).size()>10000) throw new IllegalStateException("Invalid online count");
        String throughput=rate.measure(now,observedTicks);
        MemoryUsage heap=ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        long collections=0,millis=0;boolean countKnown=true,timeKnown=true;
        for(GarbageCollectorMXBean gc:ManagementFactory.getGarbageCollectorMXBeans()) {
            if(gc.getCollectionCount()<0) countKnown=false;else collections+=gc.getCollectionCount();
            if(gc.getCollectionTime()<0) timeKnown=false;else millis+=gc.getCollectionTime();
        }
        Integer[] ids=(Integer[])dimensionIds.invoke(null);Arrays.sort(ids);
        Map<?,?> histories=(Map<?,?>)worldTicks.get(server);
        StringBuilder dimensions=new StringBuilder();int included=0;
        for(Integer id:ids) {
            if(included>=policy.maxDimensions) break;
            Object ring=histories.get(id);
            if(!(ring instanceof long[])) continue;
            if(included++>0) dimensions.append(',');
            dimensions.append('"').append(id).append("\":").append(TickWindow.json((long[])ring));
        }
        return "{\"schema\":1,\"profile\":\""+profile+"\",\"core_version\":\""+OmkalityCore.VERSION+"\",\"boot\":\""+boot+"\",\"sequence\":"+(++sequence)
            +",\"sampled_at_ms\":"+System.currentTimeMillis()+",\"uptime_ms\":"+ManagementFactory.getRuntimeMXBean().getUptime()
            +",\"running\":true,\"online\":"+((List<?>)online).size()+",\"ticks_total\":"+observedTicks
            +","+throughput
            +",\"tick\":"+TickWindow.json((long[])ticks.get(server))
            +",\"heap_used_bytes\":"+heap.getUsed()+",\"heap_committed_bytes\":"+heap.getCommitted()
            +",\"heap_max_bytes\":"+(heap.getMax()<0?"null":Long.toString(heap.getMax()))
            +",\"gc_collections_total\":"+(countKnown?Long.toString(collections):"null")
            +",\"gc_millis_total\":"+(timeKnown?Long.toString(millis):"null")
            +",\"dimension_count\":"+ids.length+",\"dimensions_truncated\":"+(ids.length>included)
            +",\"dimensions\":{"+dimensions+"}}\n";
    }
}
