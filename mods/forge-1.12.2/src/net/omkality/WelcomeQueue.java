package net.omkality;

import java.util.*;

/** Login-only pending work; removes before delivery, no ticking session database. */
final class WelcomeQueue {
    private final Map<UUID,Long> pending=new HashMap<UUID,Long>();
    boolean login(UUID id,long now,int delay) {
        if(!pending.containsKey(id)&&pending.size()>=1024)return false;
        pending.put(id,now+delay*1000000000L);return true;
    }
    void logout(UUID id){pending.remove(id);}
    List<UUID> due(long now) {
        List<UUID> result=new ArrayList<UUID>();
        Iterator<Map.Entry<UUID,Long>> iterator=pending.entrySet().iterator();
        while(iterator.hasNext()) {
            Map.Entry<UUID,Long> item=iterator.next();
            if(now-item.getValue()>=0){result.add(item.getKey());iterator.remove();}
        }
        return result;
    }
}
