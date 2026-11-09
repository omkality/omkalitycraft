package net.omkality.patches;

import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Refresh the pinned TC Fix filter cache after JED registers late dimensions,
 * before Core initializes the resource world. Never edits rules or chunks. */
public final class ResourceGenerationGuard {
    public static void install(Path config,Logger log)throws Exception{
        Path policy=config.resolve("omkalitycore-resource.properties");
        if(!Files.exists(policy,LinkOption.NOFOLLOW_LINKS)){CoreServices.report("fix.resource.generation","not configured");return;}
        if(!Files.isRegularFile(policy,LinkOption.NOFOLLOW_LINKS)||Files.size(policy)>4096)throw new IllegalStateException("Invalid resource policy for generation adapter");
        Properties p=new Properties();try(Reader reader=Files.newBufferedReader(policy,StandardCharsets.UTF_8)){p.load(reader);}
        String value=p.getProperty("dimension","");if(!value.matches("-[0-9]{1,5}"))throw new IllegalStateException("Invalid resource generation dimension");
        int dimension=Integer.parseInt(value);if(dimension < -32000||dimension > -2)throw new IllegalStateException("Unsafe resource generation dimension");
        VerifiedArtifacts.requireClass("thecodex6824.thaumcraftfix.ThaumcraftFix","thaumcraftfix.1.1.11");
        VerifiedArtifacts.requireClass("fi.dy.masa.justenoughdimensions.JustEnoughDimensions","jed.1.6.0");
        Class<?> manager=Class.forName("net.minecraftforge.common.DimensionManager");
        Object resource=manager.getMethod("getProviderType",int.class).invoke(null,dimension);
        Object main=manager.getMethod("getProviderType",int.class).invoke(null,0);
        if(resource==null||resource==main)throw new IllegalStateException("Independent JED type must be registered before generation adapter");
        if(!"omk_resource".equals(resource.getClass().getMethod("func_186065_b").invoke(resource)))throw new IllegalStateException("Resource DimensionType name was aliased by JED");
        Class<?> api=Class.forName("thecodex6824.thaumcraftfix.api.FeatureControlApi");
        boolean before=((Set<?>)api.getMethod("crystalAllowedDimensions").invoke(null)).contains(resource);
        // The upstream public bridge exposes reloadConfig. Rebuild its caches
        // from the unchanged config rather than mutating its immutable sets.
        Object implementation=Class.forName("thecodex6824.thaumcraftfix.api.internal.ThaumcraftFixApiBridge").getMethod("implementation").invoke(null);
        implementation.getClass().getMethod("reloadConfig").invoke(implementation);
        if(!Boolean.TRUE.equals(api.getMethod("isControllingCrystalGen").invoke(null))||!Boolean.TRUE.equals(api.getMethod("isControllingVegetationGen").invoke(null)))throw new IllegalStateException("Reviewed TC generation controls are disabled");
        for(String method:new String[]{"crystalAllowedDimensions","vegetationAllowedDimensions"}){
            Set<?> allowed=(Set<?>)api.getMethod(method).invoke(null);
            if(!allowed.contains(main)||!allowed.contains(resource))throw new IllegalStateException("TC generation config does not allow both main and resource types");
        }
        CoreServices.report("fix.resource.generation","enabled");
        log.info("Omkality resource generation filters refreshed before world initialization: dimension {}, crystal allowed before={}, after=true",dimension,before);
    }
}
