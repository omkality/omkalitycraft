package net.omkality;

import java.lang.reflect.*;

/** Shared, live FTB ownership lookup for ownerless server effects. No claim DB/cache. */
final class FtbClaimDomains {
    private static Method active,queue,teamAt,sameTeam,getX,getZ,dimension;
    private static Field instance,provider;
    private static Constructor<?> chunkPosition;

    static void install() throws Exception {
        FtbMuteGuard.requireVersion("ftbutilities","5.4.1.131");
        FtbMuteGuard.requireVersion("ftblib","5.4.7.2");
        Class<?> claims=Class.forName("com.feed_the_beast.ftbutilities.data.ClaimedChunks");
        Class<?> chunk=Class.forName("com.feed_the_beast.ftblib.lib.math.ChunkDimPos");
        Class<?> team=Class.forName("com.feed_the_beast.ftblib.lib.data.ForgeTeam");
        active=claims.getMethod("isActive");
        if(!Boolean.TRUE.equals(active.invoke(null))) throw new IllegalStateException("Autonomous effects require active FTB claims");
        instance=claims.getField("instance");queue=claims.getMethod("processQueue");teamAt=claims.getMethod("getChunkTeam",chunk);
        sameTeam=team.getMethod("equalsTeam",team);chunkPosition=chunk.getConstructor(int.class,int.class,int.class);
        Class<?> world=Class.forName("net.minecraft.world.World"),pos=Class.forName("net.minecraft.util.math.BlockPos");
        provider=world.getField("field_73011_w");dimension=provider.getType().getMethod("getDimension");
        getX=pos.getMethod("func_177958_n");getZ=pos.getMethod("func_177952_p");
    }
    static Object flush() throws Exception {
        if(!Boolean.TRUE.equals(active.invoke(null))) throw new IllegalStateException("FTB claims became inactive");
        Object claims=instance.get(null);queue.invoke(claims);return claims;
    }
    static Object owner(Object claims,Object world,Object pos) throws Exception {
        int dim=((Number)dimension.invoke(provider.get(world))).intValue();
        int x=((Number)getX.invoke(pos)).intValue()>>4,z=((Number)getZ.invoke(pos)).intValue()>>4;
        return teamAt.invoke(claims,chunkPosition.newInstance(x,z,dim));
    }
    static boolean matches(Object first,Object second) throws Exception {
        return first==null ? second==null : second!=null && Boolean.TRUE.equals(sameTeam.invoke(first,second));
    }
    static boolean permits(Object world,Object origin,Object target) throws Exception {
        Object claims=flush();return matches(owner(claims,world,origin),owner(claims,world,target));
    }
}
