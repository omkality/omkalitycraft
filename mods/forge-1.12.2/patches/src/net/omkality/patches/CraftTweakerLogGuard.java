package net.omkality.patches;

import org.apache.logging.log4j.Logger;

/** Require the reviewed ZenUtils writer of the server's CraftTweaker log. */
public final class CraftTweakerLogGuard {
    /** Marker applied by the writer mixin. */
    public interface Installed { }

    /** Check the exact JARs and transformed writer before the server becomes ready. */
    public static void install(Logger log) throws Exception {
        VerifiedArtifacts.requireClass("crafttweaker.CrafttweakerImplementationAPI", "crafttweaker.4.1.20.711");
        String writer = "youyihj.zenutils.impl.runtime.ZenUtilsFileLogger";
        VerifiedArtifacts.requireClass(writer, "zenutils.1.27.2");
        if (!Installed.class.isAssignableFrom(Class.forName(writer))) {
            throw new IllegalStateException("CraftTweaker log adapter is absent");
        }
        log.info("Omkality bounded CraftTweaker file log initialized");
    }
}
