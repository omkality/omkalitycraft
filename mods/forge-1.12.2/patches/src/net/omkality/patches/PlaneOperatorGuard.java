package net.omkality.patches;

import java.lang.reflect.Method;
import net.minecraftforge.fml.common.FMLCommonHandler;
import net.omkality.api.CoreServices;

/** Suppress only the reviewed PlaneFix startup grant; never edit an OP list. */
public final class PlaneOperatorGuard {
    private PlaneOperatorGuard() {}

    public static void beforeGrant() throws Exception {
        VerifiedArtifacts.requireClass("shadows.PlaneFix","planefix.1.0.0");
        Object server=FMLCommonHandler.instance().getMinecraftServerInstance();
        if(server==null) throw new IllegalStateException("Missing server for PlaneFix policy");
        Class<?> type=Class.forName("net.minecraft.server.MinecraftServer");
        Method protection;
        try { protection=type.getMethod("func_82357_ak"); }
        catch(NoSuchMethodException development) { protection=type.getMethod("getSpawnProtectionSize"); }
        Object size=protection.invoke(server);
        if(!(size instanceof Integer) || ((Integer)size).intValue()!=0)
            throw new IllegalStateException("PlaneFix no-OP policy requires spawn-protection=0 and FTB spawn claims");
        CoreServices.report("fix.planefix.operator","enabled");
    }
}
