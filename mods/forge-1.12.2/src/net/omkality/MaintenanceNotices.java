package net.omkality;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Callable;

/** Per-boot, bounded at-most-once notice attempts. Never evict a retry fence. */
final class MaintenanceNotices {
    static final class Receipt {
        final int delivered;
        final boolean replayed;
        Receipt(int delivered,boolean replayed) { this.delivered=delivered;this.replayed=replayed; }
    }
    private final Map<String,Integer> attempts=new HashMap<String,Integer>();
    synchronized Receipt send(String operation,int seconds,Callable<Integer> broadcast) throws Exception {
        if(operation==null || !operation.matches("[a-f0-9]{32}") || seconds<1 || seconds>3600)
            throw new IllegalArgumentException("invalid_notice");
        String key=operation+":"+seconds;
        if(attempts.containsKey(key)) {
            Integer count=attempts.get(key);
            if(count==null) throw new IllegalStateException("notice_unconfirmed");
            return new Receipt(count,true);
        }
        if(attempts.size()>=256) throw new IllegalStateException("notice_limit");
        attempts.put(key,null); // Retained even if a partial broadcast throws.
        int count=broadcast.call();
        if(count<0 || count>10000) throw new IllegalStateException("invalid_recipient_count");
        attempts.put(key,count);
        return new Receipt(count,false);
    }
}
