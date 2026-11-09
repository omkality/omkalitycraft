package net.omkality.api;

import org.apache.logging.log4j.Logger;

/** Register during mod pre-init; Core orders prepare -> integrations -> start. */
public interface ServerExtension {
    void prepare(Logger log) throws Exception;
    void start(Logger log) throws Exception;
}
