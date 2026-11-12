package net.omkality;

import java.util.Arrays;

/** Nearest-rank p95 of valid entries in Forge's last-100-tick ring. */
final class TickWindow {
    static String json(long[] input) {
        if(input==null || input.length!=100) throw new IllegalArgumentException("Invalid tick ring");
        long[] values=new long[100];int count=0;double total=0;
        for(long value:input) {
            if(value<0) throw new IllegalArgumentException("Negative tick duration");
            if(value>0) { values[count++]=value;total+=value; }
        }
        if(count==0) return "{\"samples\":0,\"mean_ms\":null,\"p95_ms\":null,\"max_ms\":null}";
        Arrays.sort(values,0,count);
        return "{\"samples\":"+count+",\"mean_ms\":"+(total/count/1000000d)
            +",\"p95_ms\":"+(values[(int)Math.ceil(count*0.95)-1]/1000000d)
            +",\"max_ms\":"+(values[count-1]/1000000d)+"}";
    }
}
