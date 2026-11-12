package net.omkality.api;

/** Optional loaded backup state. No pack or third-party types cross this API. */
public interface BackupPolicyAccess {
    String adapter();
    boolean automaticBackupsDisabled() throws Exception;
    boolean backupRunning() throws Exception;
}
