package net.omkality;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Owner-controlled requirements, never class names, artifact pins or passwords. */
final class ServerProfile {
    String id="generic";
    final Set<String> capabilities=new TreeSet<String>(Arrays.asList("core.connections"));
    final Map<String,String> extensions=new TreeMap<String,String>();
    static ServerProfile read(Path config) throws Exception {
        ServerProfile result=new ServerProfile();Path path=config.resolve("omkalitycore-profile.properties");
        if(!Files.exists(path,LinkOption.NOFOLLOW_LINKS)) return result;
        if(!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS) || Files.size(path)>16384)
            throw new IllegalArgumentException("Invalid server profile file");
        Properties properties=new Properties();
        try(Reader in=Files.newBufferedReader(path,StandardCharsets.UTF_8)) { properties.load(in); }
        Set<String> allowed=new HashSet<String>(Arrays.asList("schema","id","required.capabilities","required.extensions"));
        if(!"1".equals(properties.getProperty("schema")) || !allowed.containsAll(properties.stringPropertyNames()))
            throw new IllegalArgumentException("Unknown server profile schema or field");
        result.id=properties.getProperty("id","");
        if(!result.id.matches("[a-z0-9_.-]{1,80}")) throw new IllegalArgumentException("Invalid server profile ID");
        for(String item:list(properties.getProperty("required.capabilities",""))) {
            if(!item.matches("[a-z0-9_.]{1,80}") || !result.capabilities.add(item))
                throw new IllegalArgumentException("Invalid or duplicate required capability");
        }
        for(String item:list(properties.getProperty("required.extensions",""))) {
            String[] pair=item.split("@",-1);
            if(pair.length!=2 || !pair[0].matches("[a-z0-9_]{1,64}") || !pair[1].matches("[A-Za-z0-9_.-]{1,40}")
                || result.extensions.put(pair[0],pair[1])!=null)
                throw new IllegalArgumentException("Invalid or duplicate required extension");
        }
        return result;
    }
    private static List<String> list(String value) {
        if(value.trim().isEmpty()) return Collections.emptyList();
        String[] values=value.split(",",-1);if(values.length>64) throw new IllegalArgumentException("Too many profile requirements");
        List<String> result=new ArrayList<String>();for(String item:values) result.add(item.trim());return result;
    }
}
