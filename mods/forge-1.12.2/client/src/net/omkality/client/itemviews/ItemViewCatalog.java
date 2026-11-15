package net.omkality.client.itemviews;

import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Bounded presentation rules. The caller never gives this class mutable game NBT. */
public final class ItemViewCatalog {
    public interface Text { String get(String key, Object... args); }
    public interface Wrap { List<String> lines(String text, int width); }
    private final List<Properties> labels = new ArrayList<Properties>();
    private final List<Properties> books = new ArrayList<Properties>();
    private ItemViewCatalog() {}

    public static ItemViewCatalog read(InputStream input) throws IOException {
        if (input == null) throw new IOException("Missing item-view profile");
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        byte[] buf=new byte[2048]; int n;
        while((n=input.read(buf))!=-1) {
            if(n>65536-out.size())throw new IOException("Item-view profile limit");
            out.write(buf,0,n);
        }
        Properties p=new Properties() {
            @Override public synchronized Object put(Object key,Object value) {
                if(containsKey(key))throw new IllegalArgumentException("Duplicate item-view property");
                return super.put(key,value);
            }
        };
        p.load(new InputStreamReader(new ByteArrayInputStream(out.toByteArray()),StandardCharsets.UTF_8));
        if(!"1".equals(p.getProperty("schema"))||p.size()>2048)throw new IOException("Invalid item-view schema");
        ItemViewCatalog result=new ItemViewCatalog();
        for(String kind:new String[]{"label","book"}) {
            int count=number(p,kind+".count",kind.equals("label")?96:16);
            for(int i=0;i<count;i++) {
                String prefix=kind+"."+i+"."; Properties rule=new Properties();
                for(String name:p.stringPropertyNames())if(name.startsWith(prefix))rule.setProperty(name.substring(prefix.length()),p.getProperty(name));
                String item=required(rule,"item");
                if(!item.matches("[a-z0-9_.-]+:[a-z0-9_./-]+"))throw new IOException("Invalid item-view item");
                number(rule,"meta",32767);
                if(kind.equals("label")) {
                    if(!Arrays.asList("name","lore").contains(required(rule,"field")))throw new IOException("Invalid item-view field");
                    String mode=required(rule,"mode");
                    if(mode.equals("exact"))pin(rule,"source");
                    else if(mode.equals("number")) {
                        if(required(rule,"prefix").length()>96||!required(rule,"value").startsWith("@"))throw new IOException("Invalid numeric item-view rule");
                    } else throw new IOException("Invalid item-view mode");
                    required(rule,"value"); result.labels.add(rule);
                } else {
                    pin(rule,"title");pin(rule,"author");pin(rule,"pages");
                    int parts=number(rule,"parts",96);if(parts==0)throw new IOException("Empty item-view book");
                    for(int part=0;part<parts;part++)required(rule,"part."+part);
                    result.books.add(rule);
                }
            }
        }
        return result;
    }
    private static String required(Properties p,String key)throws IOException {
        String s=p.getProperty(key);if(s==null||s.isEmpty()||s.length()>4096||s.indexOf('\0')>=0)throw new IOException("Invalid item-view value");return s;
    }
    private static int number(Properties p,String key,int max)throws IOException {
        try {String s=required(p,key);if(!s.matches("[0-9]{1,5}"))throw new NumberFormatException();int n=Integer.parseInt(s);if(n>max)throw new NumberFormatException();return n;}
        catch(NumberFormatException e){throw new IOException("Invalid item-view count");}
    }
    private static void pin(Properties p,String key)throws IOException {
        if(!required(p,key).matches("[a-f0-9]{64}"))throw new IOException("Invalid item-view source pin");
    }
    public static String digest(String text) {return hash(Collections.singletonList(text),false);}
    public static String pageDigest(List<String> pages) {return hash(pages,true);}
    private static String hash(List<String> values,boolean frame) {
        try {
            MessageDigest d=MessageDigest.getInstance("SHA-256");int bytes=0;
            if(values.size()>100)return "";
            for(String s:values) {
                if(s==null||s.length()>32766)return "";byte[] raw=s.getBytes(StandardCharsets.UTF_8);
                bytes+=raw.length;if(bytes>64*1024)return "";
                if(frame)d.update(ByteBuffer.allocate(4).putInt(raw.length).array());d.update(raw);
            }
            StringBuilder b=new StringBuilder();for(byte v:d.digest())b.append(String.format(Locale.ROOT,"%02x",v&255));return b.toString();
        }catch(java.security.NoSuchAlgorithmException e){throw new AssertionError(e);}
    }
    private static boolean matches(Properties p,String item,int meta) {
        return p.getProperty("item").equals(item)&&p.getProperty("meta").equals(Integer.toString(meta));
    }
    /** Book titles are eligible only with the same author and all canonical pages. */
    public boolean knownBook(String item,int meta,String title,String author,List<String> original) {
        if(title==null||author==null||title.length()>256||author.length()>256||original==null)return false;
        for(Properties p:books)if(matches(p,item,meta)&&p.getProperty("title").equals(digest(title))&&p.getProperty("author").equals(digest(author))&&p.getProperty("pages").equals(pageDigest(original)))return true;
        return false;
    }
    private static String value(String source,Text text,Object...args) {
        if(!source.startsWith("@"))return source;
        String key=source.substring(1),result=text.get(key,args);
        return result==null||result.equals(key)||result.isEmpty()?null:result.replace("\\n","\n");
    }
    /** Null means leave the original visible line alone. */
    public String label(String item,int meta,String field,String raw,Text text) {
        if(raw==null||raw.length()>4096)return null;
        for(Properties p:labels) {
            if(!matches(p,item,meta)||!p.getProperty("field").equals(field))continue;
            if(p.getProperty("mode").equals("exact")) {
                if(p.getProperty("source").equals(digest(raw)))return value(p.getProperty("value"),text);
            } else {
                String prefix=p.getProperty("prefix");if(!raw.startsWith(prefix))continue;
                String number=raw.substring(prefix.length());if(!number.matches("-?[0-9]{1,8}"))continue;
                return value(p.getProperty("value"),text,Integer.valueOf(number));
            }
        }
        return null;
    }
    public List<String> pages(String item,int meta,String title,String author,List<String> original,Text text,Wrap wrap) {
        if(title==null||author==null||title.length()>256||author.length()>256)return null;
        for(Properties p:books) {
            if(!matches(p,item,meta)||!p.getProperty("title").equals(digest(title))||!p.getProperty("author").equals(digest(author))||!p.getProperty("pages").equals(pageDigest(original)))continue;
            List<String> pages=new ArrayList<String>(),current=new ArrayList<String>();int count=0;
            for(int part=0;part<Integer.parseInt(p.getProperty("parts"));part++) {
                String translated=value(p.getProperty("part."+part),text);if(translated==null)return null;
                List<String> block=wrap.lines(translated,116);
                if(block==null||block.size()>1200)return null;count+=block.size();if(count>1200)return null;
                // A short paragraph belongs on one page, rather than leaving a one-line fragment.
                if(!current.isEmpty()&&(block.size()>12||current.size()+1+block.size()>12)) {
                    pages.add(String.join("\n",current));current.clear();
                }
                if(!current.isEmpty())current.add("");
                for(String line:block) {
                    if(current.size()==12){pages.add(String.join("\n",current));current.clear();}
                    current.add(line);
                }
                if(pages.size()>100)return null;
            }
            if(!current.isEmpty())pages.add(String.join("\n",current));
            if(pages.size()>100)return null;
            return Collections.unmodifiableList(pages);
        }
        return null;
    }
    public static String jsonPage(String text) {
        StringBuilder b=new StringBuilder("{\"text\":\"");
        for(int i=0;i<text.length();i++) {
            char c=text.charAt(i);
            if(c=='"'||c=='\\')b.append('\\').append(c);
            else if(c<32)b.append(String.format(Locale.ROOT,"\\u%04x",(int)c));else b.append(c);
        }
        return b.append("\"}").toString();
    }
}
