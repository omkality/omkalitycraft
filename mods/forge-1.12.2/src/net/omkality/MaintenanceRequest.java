package net.omkality;

import java.util.concurrent.Callable;

/** A queued request cancelled before it starts can never execute late. */
final class MaintenanceRequest<T> implements Runnable {
    private final Callable<T> action;
    private boolean active=true, started;
    private T result;
    private Exception error;
    MaintenanceRequest(Callable<T> action) { this.action=action; }
    public synchronized void run() {
        if(!active || started) return;
        started=true;
        try { result=action.call(); }
        catch(Exception failed) { error=failed; }
    }
    synchronized T finish() throws Exception {
        active=false;
        if(!started) throw new IllegalStateException("request_expired");
        if(error!=null) throw error;
        return result;
    }
}
