package net.omkality;

import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Deterministic helpers only; real Forge readings are accepted in a native lab. */
public final class GameMetricsControlsTest {
    private static int checks;
    private static void expect(boolean value) { if(!value) throw new AssertionError();checks++; }
    private static void denied(Map<String,String> values) {
        try { GameMetricPolicy.read(values);throw new AssertionError(); }
        catch(IllegalArgumentException expected) { expect(!expected.getMessage().contains("secret")); }
    }
    public static void main(String[] args) throws Exception {
        GameMetricPolicy defaults=GameMetricPolicy.read(Collections.<String,String>emptyMap());
        expect(!defaults.enabled && defaults.intervalSeconds==30 && defaults.maxDimensions==32);
        Map<String,String> values=new HashMap<String,String>();values.put("OMK_GAME_METRICS_ENABLED","true");
        values.put("OMK_GAME_METRICS_INTERVAL_SECONDS","5");values.put("OMK_GAME_METRICS_MAX_DIMENSIONS","64");
        expect(GameMetricPolicy.read(values).enabled && GameMetricPolicy.read(values).intervalSeconds==5);
        for(String value:new String[]{"0","301","３０","secret","5\n"}) {
            values.put("OMK_GAME_METRICS_INTERVAL_SECONDS",value);denied(values);
        }
        values.clear();values.put("OMK_GAME_METRICS_ENABLED","TRUE");denied(values);
        values.clear();values.put("OMK_GAME_METRICS_DIRECTORY","secret\n");denied(values);
        long[] ring=new long[100];expect(TickWindow.json(ring).contains("\"mean_ms\":null"));
        for(int i=0;i<100;i++)ring[i]=(i+1)*1000000L;
        String stats=TickWindow.json(ring);
        expect(stats.contains("\"samples\":100") && stats.contains("\"mean_ms\":50.5") && stats.contains("\"p95_ms\":95.0") && stats.contains("\"max_ms\":100.0"));
        Arrays.fill(ring,0);ring[0]=1000000;expect(TickWindow.json(ring).contains("\"p95_ms\":1.0"));
        ring[1]=-1;
        try { TickWindow.json(ring);throw new AssertionError(); } catch(IllegalArgumentException expected) { checks++; }
        try { TickWindow.json(new long[99]);throw new AssertionError(); } catch(IllegalArgumentException expected) { checks++; }
        TickRateWindow throughput=new TickRateWindow(60);
        expect(throughput.measure(0,0).contains("\"observed_tps\":null"));
        expect(throughput.measure(5000000000L,100).contains("\"observed_tps\":20.0"));
        // A 22-second pause is visible after the one low interval is overwritten.
        throughput.measure(27000000000L,101);
        expect(!throughput.measure(32000000000L,201).contains("\"observed_tps\":20.0"));
        expect(throughput.measure(100000000000L,1561).contains("\"observed_tps\":20.0"));
        expect(throughput.measure(100000000001L,1).contains("\"observed_tps\":null"));
        Path root=Files.createTempDirectory("omk-metrics-controls-");
        final AtomicInteger errors=new AtomicInteger();MetricFile.Errors report=new MetricFile.Errors() { public void report(String kind) { errors.incrementAndGet(); } };
        // createTempDirectory uses 700 on POSIX. This folder is exclusively ours.
        MetricFile file=new MetricFile(root,report);
        try(MetricFile refused=new MetricFile(root,report)) { throw new AssertionError(); } catch(java.io.IOException expected) { checks++; }
        for(int i=0;i<10000;i++)file.offer("{\"sequence\":"+i+"}\n");
        file.offer("{\"sequence\":10000,\"running\":false}\n");file.close();
        expect(new String(Files.readAllBytes(root.resolve("current.json")),StandardCharsets.UTF_8).contains("\"sequence\":10000"));
        try(java.util.stream.Stream<Path> paths=Files.list(root)) { expect(errors.get()==0 && paths.count()==2); }
        MetricFile next=new MetricFile(root,report);next.offer("{}\n");next.close();expect(errors.get()==0);
        MetricFile fault=new MetricFile(root,report);
        Files.createDirectory(root.resolve(".pending"));fault.offer("{\"unpublished\":true}\n");
        long deadline=System.nanoTime()+2000000000L;
        while(errors.get()==0 && System.nanoTime()<deadline)Thread.sleep(10);
        expect(errors.get()==1 && new String(Files.readAllBytes(root.resolve("current.json")),StandardCharsets.UTF_8).equals("{}\n"));
        Files.delete(root.resolve(".pending"));fault.offer("{\"recovered\":true}\n");fault.close();
        expect(new String(Files.readAllBytes(root.resolve("current.json")),StandardCharsets.UTF_8).contains("recovered"));
        if(FileSystems.getDefault().supportedFileAttributeViews().contains("posix")) {
            Path outside=Files.createTempFile("omk-metrics-link-control-",".json");
            Files.delete(root.resolve("current.json"));Files.createLink(root.resolve("current.json"),outside);
            try(MetricFile refused=new MetricFile(root,report)) { throw new AssertionError(); }
            catch(java.io.IOException expected) { expect(Files.size(outside)==0); }
            Files.delete(root.resolve("current.json"));Files.delete(outside);
        }
        Files.write(root.resolve("unknown"),new byte[]{1});
        try(MetricFile refused=new MetricFile(root,report)) { throw new AssertionError(); } catch(java.io.IOException expected) { expect(Files.exists(root.resolve("unknown"))); }
        try(java.util.stream.Stream<Path> paths=Files.list(root)) {
            for(Path path:(Iterable<Path>)paths::iterator)Files.delete(path);
        }
        Files.delete(root);
        System.out.println("Game metrics helper controls: "+checks+" passed");
    }
}
