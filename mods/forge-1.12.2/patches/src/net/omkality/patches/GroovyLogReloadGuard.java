package net.omkality.patches;

import java.io.IOException;
import java.io.Writer;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/** Close only the file writer created by the pinned Groovy logger, never stdout. */
public final class GroovyLogReloadGuard {
    public interface Installed { }

    public static void install(Logger log) throws Exception {
        VerifiedArtifacts.require("groovyscript");
        VerifiedArtifacts.require("mixinbooter");
        Class<?> type = Class.forName("com.cleanroommc.groovyscript.sandbox.GroovyLogImpl");
        if (!Installed.class.isAssignableFrom(type)) {
            throw new IllegalStateException("Groovy file logger lifecycle adapter is absent");
        }
        log.info("Omkality Groovy file logger lifecycle adapter initialized");
    }

    public static void closeOwned(Writer writer) {
        if (writer == null) return;
        try { writer.close(); }
        catch (IOException error) {
            LogManager.getLogger("OmkalityScriptLogs").warn("Could not flush/close the previous Groovy file writer", error);
        }
    }
}
