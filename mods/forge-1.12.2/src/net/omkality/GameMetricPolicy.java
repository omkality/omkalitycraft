package net.omkality;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;

/** Owner settings, independent of a pack, GUI, credentials or player input. */
final class GameMetricPolicy {
    final boolean enabled;
    final int intervalSeconds, maxDimensions,tpsWindowSeconds;
    final Path directory;
    private GameMetricPolicy(boolean on,int interval,int dimensions,int window,Path path) {
        enabled=on;intervalSeconds=interval;maxDimensions=dimensions;tpsWindowSeconds=window;directory=path;
    }
    static GameMetricPolicy read(Map<String,String> env) {
        String flag=env.containsKey("OMK_GAME_METRICS_ENABLED")?env.get("OMK_GAME_METRICS_ENABLED"):"false";
        if(!"true".equals(flag) && !"false".equals(flag)) throw new IllegalArgumentException("Invalid game metrics enabled setting");
        int interval=number(env,"INTERVAL_SECONDS",30,5,300);
        int dimensions=number(env,"MAX_DIMENSIONS",32,1,64);
        int window=number(env,"TPS_WINDOW_SECONDS",60,5,3600);
        if(window<interval) throw new IllegalArgumentException("TPS window must cover sample interval");
        String path=env.containsKey("OMK_GAME_METRICS_DIRECTORY")?env.get("OMK_GAME_METRICS_DIRECTORY"):"omk-metrics";
        if(path==null || path.isEmpty() || path.length()>500 || path.indexOf('\n')>=0 || path.indexOf('\r')>=0)
            throw new IllegalArgumentException("Invalid game metrics directory setting");
        return new GameMetricPolicy("true".equals(flag),interval,dimensions,window,Paths.get(path).toAbsolutePath().normalize());
    }
    private static int number(Map<String,String> env,String key,int fallback,int min,int max) {
        String value=env.containsKey("OMK_GAME_METRICS_"+key)?env.get("OMK_GAME_METRICS_"+key):Integer.toString(fallback);
        if(value==null || !value.matches("[0-9]{1,4}")) throw new IllegalArgumentException("Invalid game metrics "+key);
        int result=Integer.parseInt(value);
        if(result<min || result>max) throw new IllegalArgumentException("Invalid game metrics "+key);
        return result;
    }
}
