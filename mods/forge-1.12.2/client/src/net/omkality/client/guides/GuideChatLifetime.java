package net.omkality.client.guides;

import java.util.Collections;

/** Optional immutable profile; bad configuration falls back to vanilla display. */
public final class GuideChatLifetime {
    private static final GuideChatTiming POLICY=load();
    private GuideChatLifetime(){}
    public static boolean validProfile(String value){return value!=null&&value.matches("[a-z0-9][a-z0-9.-]{0,47}");}
    private static GuideChatTiming load() {
        if(Boolean.getBoolean("omkality.guide.chat.forge112"))try {
            String profile=System.getProperty("omkality.guide.chat.profile","");
            if(!validProfile(profile))throw new IllegalArgumentException();
            int seconds=Integer.parseInt(System.getProperty("omkality.guide.chat.seconds","20"));
            return GuideChatTiming.read(GuideChatLifetime.class.getResourceAsStream("/assets/omkalityclient/guides/"+profile+".properties"),seconds);
        } catch(Exception invalid) {System.err.println("[OmkalityClient] Guide display profile unavailable; using vanilla chat duration.");}
        return new GuideChatTiming(Collections.<String>emptySet(),10);
    }
    public static void remember(Object line,String original){POLICY.remember(line,original);}
    public static int counter(Object line,int original,int current){return POLICY.counter(line,original,current);}
}
