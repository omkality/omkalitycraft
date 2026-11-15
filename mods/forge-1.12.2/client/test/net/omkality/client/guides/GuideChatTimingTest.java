package net.omkality.client.guides;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Pure matching/time/bounds controls; native Mixin transformation is separate. */
public final class GuideChatTimingTest {
    private static int checks;
    private static void check(boolean condition) {if(!condition)throw new AssertionError("guide timing "+checks);checks++;}
    private static GuideChatTiming read(String source,int seconds)throws Exception {
        return GuideChatTiming.read(new ByteArrayInputStream(source.getBytes(StandardCharsets.UTF_8)),seconds);
    }
    private static void reject(String source,int seconds)throws Exception {
        try {read(source,seconds);throw new AssertionError("invalid guide profile accepted");}
        catch(IllegalArgumentException expected){checks++;}
    }
    public static void main(String[] args)throws Exception {
        GuideChatTiming timing=read("schema=1\nline.1=§fПамятка\nline.2=§3/home §7— домой.\n",20);
        for(String value:new String[]{"Памятка","§fПамятка","§a§lПамятка§r","§3/home §7— домой.","/home — домой."})check(timing.matches(value));
        for(String value:new String[]{"<player> Памятка","[system] Памятка","Памятка!","памятка","/home — домой. extra",null,"§xПамятка"})check(!timing.matches(value));
        char[] large=new char[4097];Arrays.fill(large,'x');check(!timing.matches(new String(large)));
        Object guide=new Object(),ordinary=new Object();timing.remember(guide,"Памятка");timing.remember(ordinary,"<player> Памятка");
        check(timing.counter(guide,1000,1000)==1000);
        check(1200-timing.counter(guide,1000,1200)==100);
        check(1399-timing.counter(guide,1000,1399)==199);
        check(1400-timing.counter(guide,1000,1400)==200);
        check(timing.counter(ordinary,1000,1200)==1000);
        check(timing.counter(guide,1000,999)==1000);
        timing.remember(guide,"Памятка");check(1400-timing.counter(guide,1000,1400)==200);
        int now=Integer.MIN_VALUE+50,then=Integer.MAX_VALUE-49;check(now-timing.counter(guide,then,now)==50);
        GuideChatTiming shortest=read("schema=1\nline.1=Памятка\n",10);shortest.remember(guide,"Памятка");check(shortest.counter(guide,1000,1200)==1000);
        GuideChatTiming longest=read("schema=1\nline.1=Памятка\n",60);longest.remember(guide,"Памятка");check(2200-longest.counter(guide,1000,2200)==200);
        for(int seconds:new int[]{0,9,61,Integer.MAX_VALUE})reject("schema=1\nline.1=Памятка\n",seconds);
        for(String text:new String[]{"schema=2\nline.1=x\n","schema=1\n","schema=1\nline.2=x\n","schema=1\nline.1=x\nline.1=y\n","schema=1\nline.1=x\nunknown=x\n","schema=1\nline.1=   \n","schema=1\nline.1=x\\ny\n"})reject(text,20);
        Object nullLine=null;timing.remember(nullLine,"Памятка");check(timing.tracked()==1);
        List<Object> retained=new ArrayList<Object>();
        for(int i=0;i<800;i++){Object line=new Object();retained.add(line);timing.remember(line,"Памятка");if(timing.tracked()>256)throw new AssertionError("unbounded guide metadata");}check(timing.tracked()<=256);
        GuideChatTiming packaged=GuideChatTiming.read(GuideChatTimingTest.class.getResourceAsStream("/assets/omkalityclient/guides/dj2-2.23.4.properties"),20);
        check(packaged.matches("OmkalityCraft · Короткая памятка"));
        check(packaged.matches("/guide — показать эту памятку снова."));
        check(!packaged.matches("hello"));
        check(!GuideChatLifetime.validProfile("../outside"));check(!GuideChatLifetime.validProfile("dj2/secret"));check(GuideChatLifetime.validProfile("dj2-2.23.4"));
        System.out.println("guide timing checks="+checks);
    }
}
