package net.omkality;

import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Opt-in generic text profile; no pack names, claim quotas or second play clock. */
final class WelcomePolicy {
    final boolean enabled;
    final int hours,delay,cooldown,helpCooldown;
    final List<String> lines;
    private WelcomePolicy(Properties text,Map<String,String> env) {
        String flag=env.containsKey("OMK_WELCOME_ENABLED")?env.get("OMK_WELCOME_ENABLED"):"true";
        if(!"true".equals(flag)&&!"false".equals(flag))throw new IllegalArgumentException("Invalid welcome enabled setting");
        enabled="true".equals(flag);
        hours=number(env,"PLAY_HOURS",3,1,168);
        delay=number(env,"DELAY_SECONDS",8,1,60);
        cooldown=number(env,"COOLDOWN_SECONDS",1800,30,86400);
        helpCooldown=number(env,"HELP_COOLDOWN_SECONDS",5,1,60);
        if(!"1".equals(text.getProperty("schema")))throw new IllegalArgumentException("Invalid guide schema");
        List<String> values=new ArrayList<String>();
        for(int i=1;i<=8;i++) {
            String value=text.getProperty("line."+i);
            if(value==null)break;
            if(value.trim().isEmpty()||value.length()>240)throw new IllegalArgumentException("Invalid guide line size");
            for(int j=0;j<value.length();j++)if(Character.isISOControl(value.charAt(j)))throw new IllegalArgumentException("Invalid guide line control");
            values.add(value);
        }
        if(values.isEmpty()||text.size()!=values.size()+1)throw new IllegalArgumentException("Invalid guide fields or line sequence");
        lines=Collections.unmodifiableList(values);
    }
    static WelcomePolicy read(Path config,Map<String,String> env)throws Exception {
        Path path=config.resolve("omkalitycore-welcome.properties");
        if(!Files.exists(path,LinkOption.NOFOLLOW_LINKS))return null;
        if(Files.isSymbolicLink(path)||!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS)||Files.size(path)>16384)
            throw new IllegalArgumentException("Invalid guide profile file");
        Properties p=new Properties(){private static final long serialVersionUID=1L; @Override public synchronized Object put(Object key,Object value){
            if(containsKey(key))throw new IllegalArgumentException("Duplicate guide field");return super.put(key,value);
        }};
        try(Reader reader=Files.newBufferedReader(path,StandardCharsets.UTF_8)){p.load(reader);}
        return new WelcomePolicy(p,env);
    }
    private static int number(Map<String,String> env,String key,int fallback,int min,int max) {
        String raw=env.containsKey("OMK_WELCOME_"+key)?env.get("OMK_WELCOME_"+key):Integer.toString(fallback);
        if(raw==null||!raw.matches("[0-9]{1,5}"))throw new IllegalArgumentException("Invalid welcome "+key);
        int value=Integer.parseInt(raw);
        if(value<min||value>max)throw new IllegalArgumentException("Invalid welcome "+key);
        return value;
    }
    static boolean elapsed(long now,long last,int seconds) {
        return now>0&&last>=0&&(last==0||(now>=last&&now-last>=seconds));
    }
    boolean automatic(int ticks,long now,long last) {
        return enabled&&ticks>=0&&ticks<hours*72000&&elapsed(now,last,cooldown);
    }
}
