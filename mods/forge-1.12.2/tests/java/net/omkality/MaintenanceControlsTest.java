package net.omkality;

import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;

/** Pure helper controls; no Minecraft/Forge ABI classes or world fixtures. */
public final class MaintenanceControlsTest {
    private static int checks;
    private static void expect(boolean value) { if(!value)throw new AssertionError();checks++; }
    public static void main(String[] args) throws Exception {
        final AtomicInteger calls=new AtomicInteger();
        Callable<Integer> action=new Callable<Integer>() { public Integer call() { return calls.incrementAndGet(); } };
        MaintenanceRequest<Integer> expired=new MaintenanceRequest<Integer>(action);
        try { expired.finish();throw new AssertionError(); } catch(IllegalStateException expected) {}
        Thread late=new Thread(expired);late.start();late.join();
        expect(calls.get()==0);
        MaintenanceRequest<Integer> accepted=new MaintenanceRequest<Integer>(action);
        accepted.run();accepted.run();expect(accepted.finish()==1 && calls.get()==1);
        MaintenanceRequest<Integer> failed=new MaintenanceRequest<Integer>(new Callable<Integer>() { public Integer call() { throw new IllegalStateException("fixture"); } });
        failed.run();
        try { failed.finish();throw new AssertionError(); } catch(IllegalStateException expected) { expect("fixture".equals(expected.getMessage())); }
        MaintenanceNotices notices=new MaintenanceNotices();
        String operation="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        MaintenanceNotices.Receipt first=notices.send(operation,60,action), replay=notices.send(operation,60,action);
        expect(!first.replayed && replay.replayed && first.delivered==2 && replay.delivered==2 && calls.get()==2);
        notices.send(operation,30,action);expect(calls.get()==3);
        try { notices.send(operation,10,new Callable<Integer>() { public Integer call() { throw new IllegalStateException("partial"); } });throw new AssertionError(); } catch(IllegalStateException expected) {}
        try { notices.send(operation,10,action);throw new AssertionError(); } catch(IllegalStateException expected) { expect("notice_unconfirmed".equals(expected.getMessage()) && calls.get()==3); }
        for(int seconds:new int[]{0,3601}) {
            try { notices.send(operation,seconds,action);throw new AssertionError(); } catch(IllegalArgumentException expected) {}
        }
        try { notices.send("bad",60,action);throw new AssertionError(); } catch(IllegalArgumentException expected) { expect(calls.get()==3); }
        MaintenanceNotices bounded=new MaintenanceNotices();
        for(int i=0;i<256;i++)bounded.send(String.format("%032x",i),60,action);
        try { bounded.send(operation,60,action);throw new AssertionError(); } catch(IllegalStateException expected) { expect("notice_limit".equals(expected.getMessage())); }
        int before=calls.get();MaintenanceNotices.Receipt old=bounded.send(String.format("%032x",0),60,action);
        expect(old.replayed && calls.get()==before); // Capacity never evicts old retry fences.
        java.net.URL file=new java.io.File("example.jar").toURI().toURL();
        expect(FtbBackupPolicy.sourceJar(file).equals(java.nio.file.Paths.get(file.toURI())));
        expect(FtbBackupPolicy.sourceJar(new java.net.URL("jar:"+file+"!/Example.class")).equals(java.nio.file.Paths.get(file.toURI())));
        try { FtbBackupPolicy.sourceJar(new java.net.URL("https://example.invalid/file.jar"));throw new AssertionError(); }
        catch(IllegalStateException expected) { expect(true); }
        System.out.println("Maintenance helper controls: "+checks+" passed");
    }
}
