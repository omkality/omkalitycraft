package net.omkality;

import java.util.ArrayDeque;
import java.util.Deque;

/** Bounded rolling tick throughput; a stall survives a slower consumer poll. */
final class TickRateWindow {
    private static final class Point {
        final long at,ticks;
        Point(long time,long count) { at=time;ticks=count; }
    }
    private final long window;
    private final Deque<Point> points=new ArrayDeque<Point>();
    TickRateWindow(int seconds) {
        if(seconds<5 || seconds>3600) throw new IllegalArgumentException("Invalid TPS window");
        window=seconds*1000000000L;
    }
    String measure(long now,long ticks) {
        if(ticks<0) throw new IllegalArgumentException("Invalid tick counter");
        Point previous=points.peekLast();
        if(previous!=null && (now-previous.at<=0 || ticks<previous.ticks)) points.clear();
        points.addLast(new Point(now,ticks));
        while(points.size()>2) {
            Point first=points.removeFirst();
            if(now-points.peekFirst().at<window) { points.addFirst(first);break; }
        }
        while(points.size()>1000) points.removeFirst();
        Point first=points.peekFirst();long nanos=now-first.at;
        if(nanos<=0) return "\"observed_tps\":null,\"interval_ms\":null";
        double tps=Math.min(20,(ticks-first.ticks)*1000000000d/nanos);
        return "\"observed_tps\":"+tps+",\"interval_ms\":"+(nanos/1000000d);
    }
}
