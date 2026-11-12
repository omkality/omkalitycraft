package net.omkality;

import java.io.InputStream;
import java.lang.reflect.Field;
import java.net.JarURLConnection;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import net.minecraftforge.fml.common.Loader;
import net.omkality.api.BackupPolicyAccess;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Read-only loaded state for the separately reviewed stock FTB artifact. */
final class FtbBackupPolicy implements BackupPolicyAccess {
    private final Object general,backups;
    private final Field enabled,shutdown,doing;
    static Path sourceJar(URL location) throws Exception {
        if("jar".equals(location.getProtocol())) location=((JarURLConnection)location.openConnection()).getJarFileURL();
        if(!"file".equals(location.getProtocol())) throw new IllegalStateException("unreviewed_ftb_location");
        return Paths.get(location.toURI());
    }
    private FtbBackupPolicy() throws Exception {
        Class<?> config=Class.forName("com.feed_the_beast.mods.ftbbackups.FTBBackupsConfig");
        URL location=config.getProtectionDomain().getCodeSource().getLocation();
        Path path=sourceJar(location);
        if(!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS) || Files.size(path)>1024*1024) throw new IllegalStateException("unreviewed_ftb_artifact");
        MessageDigest digest=MessageDigest.getInstance("SHA-256");
        int total=0;byte[] buffer=new byte[8192];
        try(InputStream input=Files.newInputStream(path)) {
            int count;
            while((count=input.read(buffer))!=-1) {
                total+=count;if(total>1024*1024) throw new IllegalStateException("oversized_ftb_artifact");
                digest.update(buffer,0,count);
            }
        }
        StringBuilder sha=new StringBuilder();for(byte value:digest.digest())sha.append(String.format("%02x",value&255));
        if(!"6b6bcbbf6ac4528657345e1696339528a44643ecb06e6137908eafb8432bd962".equals(sha.toString())) throw new IllegalStateException("unreviewed_ftb_sha256");
        general=config.getField("general").get(null);
        enabled=general.getClass().getField("enabled");shutdown=general.getClass().getField("force_on_shutdown");
        Class<?> type=Class.forName("com.feed_the_beast.mods.ftbbackups.Backups");
        backups=type.getField("INSTANCE").get(null);doing=type.getField("doingBackup");
    }
    static void install(Logger log) {
        if(!Loader.isModLoaded("ftbbackups")) return;
        try {
            if(!"1.1.0.1".equals(Loader.instance().getIndexedModList().get("ftbbackups").getVersion())) throw new IllegalStateException("unreviewed_ftb_version");
            CoreServices.provideBackupPolicy(new FtbBackupPolicy());
            CoreServices.report("ftb.backup_policy","enabled");
        } catch(Exception unavailable) {
            CoreServices.report("ftb.backup_policy","unsupported");
            String reason=unavailable.getMessage();
            if(reason==null || !reason.matches("unreviewed_ftb_[a-z0-9_]+")) reason=unavailable.getClass().getSimpleName();
            log.warn("No reviewed loaded-state backup adapter for this FTB artifact ({})",reason);
        }
    }
    public String adapter() { return "ftb-backups-1.1.0.1-disabled-v1"; }
    public boolean automaticBackupsDisabled() throws Exception { return !enabled.getBoolean(general) && !shutdown.getBoolean(general); }
    public boolean backupRunning() throws Exception { return doing.getInt(backups)!=0; }
}
