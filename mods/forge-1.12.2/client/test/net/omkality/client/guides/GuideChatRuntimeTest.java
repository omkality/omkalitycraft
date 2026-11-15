package net.omkality.client.guides;

/** Each process gets fresh static configuration; no native rendering is claimed. */
public final class GuideChatRuntimeTest {
    public static void main(String[] args) {
        Object guide=new Object(),ordinary=new Object();
        GuideChatLifetime.remember(guide,"OmkalityCraft · Короткая памятка");
        GuideChatLifetime.remember(ordinary,"<player> OmkalityCraft · Короткая памятка");
        if(GuideChatLifetime.counter(guide,1000,1200)!=Integer.parseInt(args[0]))throw new AssertionError("wrong configured guide age");
        if(GuideChatLifetime.counter(ordinary,1000,1200)!=1000)throw new AssertionError("ordinary chat changed");
        System.out.println("guide runtime checks=2");
    }
}
