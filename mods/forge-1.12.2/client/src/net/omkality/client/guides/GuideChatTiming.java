package net.omkality.client.guides;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashSet;
import java.util.Properties;
import java.util.Set;
import java.util.WeakHashMap;

/** Bounded presentation metadata; never changes a message, chat id or clock. */
public final class GuideChatTiming {
    private final Set<String> lines;
    private final int ticks;
    private final WeakHashMap<Object,Boolean> marked=new WeakHashMap<Object,Boolean>();
    GuideChatTiming(Set<String> expected,int seconds) {
        if(seconds<10||seconds>60)throw new IllegalArgumentException("Invalid guide display duration");
        lines=Collections.unmodifiableSet(new HashSet<String>(expected));ticks=seconds*20;
    }
    public static GuideChatTiming read(InputStream source,int seconds)throws IOException {
        if(source==null)throw new IllegalArgumentException("Missing guide text profile");
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] buffer=new byte[1024];int count;
        try {while((count=source.read(buffer))!=-1){bytes.write(buffer,0,count);if(bytes.size()>16384)throw new IllegalArgumentException("Oversized guide text profile");}}
        finally {source.close();}
        Properties values=new Properties(){private static final long serialVersionUID=1L;
            @Override public synchronized Object put(Object key,Object value){if(containsKey(key))throw new IllegalArgumentException("Duplicate guide field");return super.put(key,value);}};
        values.load(new StringReader(new String(bytes.toByteArray(),StandardCharsets.UTF_8)));
        if(!"1".equals(values.getProperty("schema")))throw new IllegalArgumentException("Invalid guide text schema");
        Set<String> expected=new HashSet<String>();int entries=0;
        for(int i=1;i<=8;i++) {
            String value=values.getProperty("line."+i);if(value==null)break;
            if(value.trim().isEmpty()||value.length()>240)throw new IllegalArgumentException("Invalid guide text size");
            for(int j=0;j<value.length();j++)if(Character.isISOControl(value.charAt(j)))throw new IllegalArgumentException("Invalid guide text control");
            expected.add(plain(value));entries++;
        }
        if(entries==0||values.size()!=entries+1)throw new IllegalArgumentException("Invalid guide text fields");
        return new GuideChatTiming(expected,seconds);
    }
    private static String plain(String value) {return value.replaceAll("(?i)§[0-9a-fk-or]","");}
    public boolean matches(String value) {return value!=null&&value.length()<=4096&&lines.contains(plain(value));}
    public void remember(Object line,String original) {
        if(line==null||!matches(original))return;
        if(marked.size()>=256)marked.clear();
        marked.put(line,Boolean.TRUE);
    }
    public int counter(Object line,int original,int current) {
        int age=current-original;
        if(age<0||!marked.containsKey(line))return original;
        // Preserve vanilla overflow arithmetic and its existing fade/visibility curve.
        return current-(int)((long)age*200L/ticks);
    }
    int tracked(){return marked.size();}
}
