package net.omkality;

import java.lang.reflect.*;
import java.util.*;
import net.omkality.api.CoreServices;
import net.omkality.api.PlayerPlacementAccess;

/** FTB owns permission decisions. This provider does not write or roll back blocks. */
public final class FtbPlayerPlacement implements PlayerPlacementAccess {
    private final Field actorWorld,remote;
    private final Class<?> playerType;
    private final Method active,blocked,block,x,z;
    private FtbPlayerPlacement() throws Exception {
        Class<?> player=Class.forName("net.minecraft.entity.player.EntityPlayer");
        Class<?> pos=Class.forName("net.minecraft.util.math.BlockPos");
        Class<?> state=Class.forName("net.minecraft.block.state.IBlockState");
        Class<?> claims=Class.forName("com.feed_the_beast.ftbutilities.data.ClaimedChunks");
        playerType=Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        actorWorld=Class.forName("net.minecraft.entity.Entity").getField("field_70170_p");
        remote=Class.forName("net.minecraft.world.World").getField("field_72995_K");
        active=claims.getMethod("isActive");blocked=claims.getMethod("blockBlockEditing",player,pos,state);
        block=state.getMethod("func_177230_c");x=pos.getMethod("func_177958_n");z=pos.getMethod("func_177952_p");
    }
    public static void install() throws Exception {
        CoreServices.providePlayerPlacement(new FtbPlayerPlacement());
    }
    public Scope at(final Object actor,final Object world) throws Exception {
        if(!playerType.isInstance(actor) || remote.getBoolean(world) || actorWorld.get(actor)!=world)
            throw new IllegalArgumentException("Native server player/world required");
        FtbClaimDomains.flush();
        // Pinned FTB decisions depend on actor, chunk and block identity,
        // including explicit block grants. The cache dies with this operation.
        final Map<Long,IdentityHashMap<Object,Boolean>> memo=new HashMap<Long,IdentityHashMap<Object,Boolean>>();
        return new Scope() {
            private int keys;
            public boolean permits(Object target,Object placed) throws Exception {
                if(actorWorld.get(actor)!=world) return false;
                if(!Boolean.TRUE.equals(active.invoke(null))) throw new IllegalStateException("Claim provider became inactive");
                int cx=((Number)x.invoke(target)).intValue()>>4,cz=((Number)z.invoke(target)).intValue()>>4;
                long key=((long)cx<<32)|(cz&0xffffffffL);Object type=block.invoke(placed);
                IdentityHashMap<Object,Boolean> values=memo.get(key);
                if(values!=null && values.containsKey(type)) return values.get(type);
                boolean result=!Boolean.TRUE.equals(blocked.invoke(null,actor,target,placed));
                if(keys<4096) {
                    if(values==null){values=new IdentityHashMap<Object,Boolean>();memo.put(key,values);}
                    values.put(type,result);keys++;
                }
                return result;
            }
        };
    }
}
