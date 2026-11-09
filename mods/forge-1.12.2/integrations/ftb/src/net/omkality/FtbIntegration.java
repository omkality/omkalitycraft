package net.omkality;

import java.nio.file.Path;
import java.nio.file.Files;
import net.omkality.api.ClaimAccess;
import net.omkality.api.CoreServices;
import org.apache.logging.log4j.Logger;

/** Exact supported FTB implementation; no external types cross the Core API. */
public final class FtbIntegration {
    public static void install(Path config,Logger log) throws Exception {
        FtbMuteGuard.install(log);
        CoreServices.report("ftb.integration","enabled");
        CoreServices.report("ftb.mute",FtbMuteGuard.state);
        if(!Boolean.TRUE.equals(Class.forName("com.feed_the_beast.ftbutilities.data.ClaimedChunks")
                .getMethod("isActive").invoke(null))) {
            CoreServices.report("ftb.claims","disabled");
            CoreServices.report("ftb.containers","disabled");
            CoreServices.report("ftb.player_placement","disabled");
            if(Files.exists(config.resolve("omkalitycore-spawn.properties")) || Files.exists(config.resolve("omkalitycore-rtp.properties")) || Files.exists(config.resolve("omkalitycore-territories.properties")) || Files.exists(config.resolve("omkalitycore-resource.properties")))
                throw new IllegalStateException("Configured FTB gameplay services require active claims");
            log.info("FTB claims disabled by owner; Core claim integration is inactive");
            return;
        }
        FtbClaimGuard.install(log);
        FtbClaimDomains.install();
        FtbTerritories.install(config,log);
        FtbPlayerPlacement.install();
        CoreServices.provideClaims(new ClaimAccess() {
            public Scope at(final Object world,final Object origin) throws Exception {
                final Object claims=FtbClaimDomains.flush(),owner=FtbClaimDomains.owner(claims,world,origin);
                return new Scope() {
                    public boolean contains(Object targetWorld,Object target) throws Exception {
                        return targetWorld==world && FtbClaimDomains.matches(owner,FtbClaimDomains.owner(claims,world,target));
                    }
                    public boolean permitsWrite(Object targetWorld,Object target,boolean allowUnclaimed) throws Exception {
                        if(targetWorld!=world) return false;
                        Object targetOwner=FtbClaimDomains.owner(claims,world,target);
                        return (allowUnclaimed && targetOwner==null) || FtbClaimDomains.matches(owner,targetOwner);
                    }
                };
            }
        });
        FtbResourceWorld resource=FtbResourceWorld.prepare(config,log);
        FtbSpawnClaims.install(config,log);
        FtbRtpGuard.install(config,log);
        CoreServices.report("ftb.integration","enabled");
        CoreServices.report("ftb.claims","enabled");
        CoreServices.report("ftb.player_placement","enabled");
        CoreServices.report("ftb.containers",FtbClaimGuard.state);
        CoreServices.report("ftb.mute",FtbMuteGuard.state);
        CoreServices.report("ftb.spawn",FtbSpawnClaims.state);
        CoreServices.report("ftb.rtp",FtbRtpGuard.state);
        if(resource!=null)resource.start();
    }
}
