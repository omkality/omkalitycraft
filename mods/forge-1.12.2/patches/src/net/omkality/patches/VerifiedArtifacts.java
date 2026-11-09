package net.omkality.patches;

import java.io.InputStream;
import java.net.JarURLConnection;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.Properties;
import net.minecraftforge.fml.common.Loader;
import net.minecraftforge.fml.common.ModContainer;

/** Immutable, reviewed adapter artifacts packaged with Core, never player input. */
final class VerifiedArtifacts {
    static void requireClass(String name,String key) throws Exception {
        Properties supported=new Properties();
        try(InputStream in=VerifiedArtifacts.class.getResourceAsStream("/adapters/dj2-artifacts.properties")) {
            if(in==null) throw new IllegalStateException("Missing adapter artifact pins");supported.load(in);
        }
        String expected=supported.getProperty(key);
        if(expected==null || !expected.matches("[a-f0-9]{64}")) throw new IllegalStateException("Missing native artifact pin");
        Path artifact=sourceJar(Class.forName(name).getProtectionDomain().getCodeSource().getLocation());
        if(!Files.isRegularFile(artifact)) throw new IllegalStateException("Native adapter source is not a JAR");
        MessageDigest sha=MessageDigest.getInstance("SHA-256");
        try(InputStream in=Files.newInputStream(artifact)) { byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1)sha.update(buffer,0,n); }
        StringBuilder actual=new StringBuilder();for(byte value:sha.digest())actual.append(String.format("%02x",value&255));
        if(!expected.equals(actual.toString())) throw new IllegalStateException("Unreviewed native adapter artifact");
    }
    static Path sourceJar(URL location) throws Exception {
        if ("jar".equals(location.getProtocol())) {
            location = ((JarURLConnection) location.openConnection()).getJarFileURL();
        }
        if (!"file".equals(location.getProtocol())) {
            throw new IllegalStateException("Adapter source must be a local JAR");
        }
        return Paths.get(location.toURI());
    }

    static void require(String modId) throws Exception {
        ModContainer mod = Loader.instance().getIndexedModList().get(modId);
        if (mod == null) throw new IllegalStateException("Required adapter mod is absent: " + modId);
        Properties supported = new Properties();
        try (InputStream resource = VerifiedArtifacts.class.getResourceAsStream("/adapters/dj2-artifacts.properties")) {
            if (resource == null) throw new IllegalStateException("Missing reviewed adapter artifact policy");
            supported.load(resource);
        }
        String expected = supported.getProperty(modId + "." + mod.getVersion());
        if (expected == null || !expected.matches("[a-f0-9]{64}")) {
            throw new IllegalStateException("Unsupported artifact version for adapter: " + modId);
        }
        Path artifact = mod.getSource().toPath();
        if ("mixinbooter".equals(modId)) {
            // This coremod uses a DummyModContainer whose source is minecraft.jar.
            // Bind the pin to the API actually loaded by LaunchClassLoader instead.
            artifact = sourceJar(Class.forName("zone.rong.mixinbooter.ILateMixinLoader")
                .getProtectionDomain().getCodeSource().getLocation());
        }
        if (!Files.isRegularFile(artifact)) {
            throw new IllegalStateException("Adapter artifact is not a regular JAR: " + modId);
        }
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream source = Files.newInputStream(artifact)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = source.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        StringBuilder actual = new StringBuilder();
        for (byte value : digest.digest()) actual.append(String.format("%02x", value & 255));
        if (!expected.equals(actual.toString())) {
            throw new IllegalStateException("Unverified artifact for adapter: " + modId);
        }
    }
}
