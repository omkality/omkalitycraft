package net.omkality;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Pure policy/queue controls; actual chat/stat/NBT bindings need a real game. */
public final class WelcomeControlsTest {
    private static int checks;
    private static void check(boolean result){if(!result)throw new AssertionError("welcome control "+checks);checks++;}
    private static WelcomePolicy profile(String text,Map<String,String> env)throws Exception {
        Path folder=Files.createTempDirectory("omk-guide-");
        try{Files.write(folder.resolve("omkalitycore-welcome.properties"),text.getBytes(StandardCharsets.UTF_8));return WelcomePolicy.read(folder,env);}
        finally{Files.deleteIfExists(folder.resolve("omkalitycore-welcome.properties"));Files.delete(folder);}
    }
    private static void reject(String text,Map<String,String> env)throws Exception {
        try{profile(text,env);throw new AssertionError("invalid policy accepted");}
        catch(IllegalArgumentException expected){check(!expected.getMessage().contains("private-value"));}
    }
    public static void main(String[] args)throws Exception {
        String text="schema=1\nline.1=Памятка\nline.2=/home\n";
        Map<String,String> empty=Collections.emptyMap();WelcomePolicy p=profile(text,empty);
        check(p.enabled&&p.hours==3&&p.delay==8&&p.cooldown==1800&&p.helpCooldown==5);
        check(p.lines.get(0).equals("Памятка")&&p.lines.size()==2);
        check(p.automatic(0,2000,0));check(p.automatic(215999,2000,0));check(!p.automatic(216000,2000,0));
        check(!p.automatic(-1,2000,0));check(!p.automatic(1,2000,1000));check(p.automatic(1,2800,1000));
        check(!p.automatic(1,999,1000));check(!p.automatic(1,0,0));check(!p.automatic(1,2000,-1));
        check(!WelcomePolicy.elapsed(2000,Long.MAX_VALUE,5));check(!WelcomePolicy.elapsed(2000,1996,5));check(WelcomePolicy.elapsed(2000,1995,5));
        Map<String,String> env=new HashMap<String,String>();env.put("OMK_WELCOME_ENABLED","false");check(!profile(text,env).automatic(0,2000,0));
        String[] names={"PLAY_HOURS","DELAY_SECONDS","COOLDOWN_SECONDS","HELP_COOLDOWN_SECONDS"};
        int[] max={168,60,86400,60};
        for(int i=0;i<names.length;i++) {
            env.clear();env.put("OMK_WELCOME_"+names[i],"0");reject(text,env);
            env.put("OMK_WELCOME_"+names[i],Integer.toString(max[i]+1));reject(text,env);
            env.put("OMK_WELCOME_"+names[i],"private-value");reject(text,env);
        }
        env.clear();env.put("OMK_WELCOME_ENABLED","private-value");reject(text,env);
        for(String bad:new String[]{"schema=2\nline.1=a\n","schema=1\n","schema=1\nline.2=a\n","schema=1\nline.1=a\nline.1=b\n","schema=1\nline.1=a\nother=b\n","schema=1\nline.1=\\u0001\n","schema=1\nline.1= \n"})reject(bad,empty);
        char[] huge=new char[241];Arrays.fill(huge,'a');reject("schema=1\nline.1="+new String(huge)+"\n",empty);
        Path missing=Files.createTempDirectory("omk-guide-empty-");check(WelcomePolicy.read(missing,empty)==null);Files.delete(missing);
        WelcomeQueue queue=new WelcomeQueue();UUID id=UUID.randomUUID();check(queue.login(id,100,2));
        check(queue.due(2000000099L).isEmpty());check(queue.due(2000000100L).equals(Arrays.asList(id)));check(queue.due(3000000100L).isEmpty());
        queue.login(id,0,1);queue.logout(id);check(queue.due(2000000000L).isEmpty());
        queue.login(id,0,1);queue.login(id,1,2);check(queue.due(1000000001L).isEmpty());check(queue.due(2000000001L).size()==1);
        queue.login(id,Long.MAX_VALUE-100,1);check(queue.due(Long.MIN_VALUE+999999899L).size()==1);
        for(int i=0;i<1024;i++)if(!queue.login(new UUID(0,i),0,1))throw new AssertionError("queue capacity");
        check(true);
        check(!queue.login(new UUID(1,1),0,1));check(queue.login(new UUID(0,1),0,1));check(queue.due(1000000000L).size()==1024);
        System.out.println("Welcome policy/queue controls passed: "+checks);
    }
}
