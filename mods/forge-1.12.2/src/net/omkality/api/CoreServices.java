package net.omkality.api;

import java.util.*;
import org.apache.logging.log4j.Logger;
import net.minecraftforge.fml.common.Loader;

/** Small versioned extension contract. No pack classes or external claim types. */
public final class CoreServices {
    public static final int API_VERSION = 1;
    private static final Map<String,ServerExtension> extensions = new TreeMap<String,ServerExtension>();
    private static final Map<String,String> states = new TreeMap<String,String>();
    private static ClaimAccess claims;
    private static PlayerPlacementAccess playerPlacement;
    private static boolean starting;
    private CoreServices() {}

    public static synchronized void register(String modId,int api,ServerExtension extension) {
        if(starting || api!=API_VERSION || extension==null || !modId.matches("[a-z0-9_]{1,64}")
            || extensions.containsKey(modId) || !Loader.isModLoaded(modId))
            throw new IllegalStateException("Invalid or incompatible Core extension registration");
        extensions.put(modId,extension);
    }
    public static synchronized void provideClaims(ClaimAccess provider) {
        if(provider==null || claims!=null) throw new IllegalStateException("Claim provider already registered or invalid");
        claims=provider;
    }
    public static ClaimAccess claims() {
        if(claims==null) throw new IllegalStateException("No supported claim provider is active");
        return claims;
    }
    public static synchronized void providePlayerPlacement(PlayerPlacementAccess provider) {
        if(provider==null || playerPlacement!=null) throw new IllegalStateException("Player placement provider already registered or invalid");
        playerPlacement=provider;
    }
    public static PlayerPlacementAccess playerPlacement() {
        if(playerPlacement==null) throw new IllegalStateException("No supported player placement provider is active");
        return playerPlacement;
    }
    public static synchronized void report(String key,String state) {
        if(!key.matches("[a-z0-9_.]{1,80}") || state==null || state.length()>160)
            throw new IllegalStateException("Invalid Core capability status");
        states.put(key,state);
    }
    public static synchronized Map<String,String> statuses() { return new TreeMap<String,String>(states); }
    public static synchronized Map<String,String> extensions() {
        Map<String,String> result=new TreeMap<String,String>();
        for(String id:extensions.keySet()) result.put(id,Loader.instance().getIndexedModList().get(id).getVersion());
        return result;
    }
    public static void requireExtensions(Map<String,String> required) {
        Map<String,String> actual=extensions();
        for(Map.Entry<String,String> entry:required.entrySet())
            if(!entry.getValue().equals(actual.get(entry.getKey())))
                throw new IllegalStateException("Required Core extension is missing or incompatible: "+entry.getKey());
    }
    public static void requireCapabilities(Set<String> required) {
        Map<String,String> actual=statuses();
        for(String key:required) if(!"enabled".equals(actual.get(key)))
            throw new IllegalStateException("Required Core capability is unavailable: "+key);
    }
    public static void prepare(Logger log) throws Exception {
        starting=true;
        for(ServerExtension extension:extensions.values()) extension.prepare(log);
    }
    public static void start(Logger log) throws Exception {
        for(ServerExtension extension:extensions.values()) extension.start(log);
    }
}
