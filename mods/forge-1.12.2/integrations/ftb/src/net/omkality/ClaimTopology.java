package net.omkality;
import java.util.*;

/** Four-neighbour components with separate dimensions. No world or database writes. */
public final class ClaimTopology {
    public static final class Point implements Comparable<Point> {
        public final int x,z,dim;
        public Point(int a,int b,int d){x=a;z=b;dim=d;}
        public int hashCode(){return 31*(31*x+z)+dim;}
        public boolean equals(Object o){if(!(o instanceof Point))return false;Point p=(Point)o;return p.x==x&&p.z==z&&p.dim==dim;}
        public int compareTo(Point p){int n=Integer.compare(dim,p.dim);if(n==0)n=Integer.compare(x,p.x);return n==0?Integer.compare(z,p.z):n;}
        public List<Point> neighbours(){List<Point> p=new ArrayList<Point>(4);
            if(x!=Integer.MIN_VALUE)p.add(new Point(x-1,z,dim));if(x!=Integer.MAX_VALUE)p.add(new Point(x+1,z,dim));
            if(z!=Integer.MIN_VALUE)p.add(new Point(x,z-1,dim));if(z!=Integer.MAX_VALUE)p.add(new Point(x,z+1,dim));return p;}
    }
    public static int components(Set<Point> points){
        Set<Point> left=new HashSet<Point>(points);int count=0;ArrayDeque<Point> queue=new ArrayDeque<Point>();
        while(!left.isEmpty()){Point start=left.iterator().next();left.remove(start);queue.add(start);count++;
            while(!queue.isEmpty())for(Point p:queue.remove().neighbours())if(left.remove(p))queue.add(p);}
        return count;
    }
    public static boolean permitted(int before,int after,long limit){return after<=limit||after<=before;}
    /** Connect existing regions before starting new ones; native events still check each claim. */
    public static List<Point> orderAdds(Set<Point> current,Collection<Point> requested){
        Set<Point> known=new HashSet<Point>(current);TreeSet<Point> pending=new TreeSet<Point>(requested);List<Point> result=new ArrayList<Point>();
        while(!pending.isEmpty()){Point selected=null;
            for(Point p:pending){for(Point next:p.neighbours())if(known.contains(next)){selected=p;break;}if(selected!=null)break;}
            if(selected==null)selected=pending.first();pending.remove(selected);known.add(selected);result.add(selected);}
        return result;
    }
}
