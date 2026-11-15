package net.omkality.client.itemviews;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Semantic boundaries: a recognized render view must never become a general text rewrite. */
public final class ItemViewCatalogTest {
    private static int checks;
    private static void check(boolean result){if(!result)throw new AssertionError("item views "+checks);checks++;}
    private static ItemViewCatalog read(String text)throws IOException{return ItemViewCatalog.read(new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8)));}
    private static void invalid(String text)throws Exception {
        try{read(text);throw new AssertionError("invalid profile accepted");}catch(IOException|IllegalArgumentException expected){checks++;}
    }
    private static String prefix="schema=1\nlabel.count=2\nbook.count=1\n";
    public static void main(String[] args)throws Exception {
        String source="§lBook of Logic",author="Atricos";
        List<String> original=Arrays.asList("{\"text\":\"Original 1\"}","{\"text\":\"Original 2\"}");
        List<String> before=new ArrayList<String>(original);
        String profile=prefix+
            "label.0.item=minecraft:written_book\nlabel.0.meta=0\nlabel.0.field=name\nlabel.0.mode=exact\nlabel.0.source="+ItemViewCatalog.digest(source)+"\nlabel.0.value=Книга логики\n"+
            "label.1.item=contenttweaker:steve\nlabel.1.meta=0\nlabel.1.field=lore\nlabel.1.mode=number\nlabel.1.prefix=Age: "+"\nlabel.1.value=@age\n"+
            "book.0.item=minecraft:written_book\nbook.0.meta=0\nbook.0.title="+ItemViewCatalog.digest(source)+"\nbook.0.author="+ItemViewCatalog.digest(author)+"\nbook.0.pages="+ItemViewCatalog.pageDigest(original)+"\nbook.0.parts=2\nbook.0.part.0=@intro\nbook.0.part.1=Девять условий.\n";
        ItemViewCatalog c=read(profile);
        ItemViewCatalog.Text text=(key,values)->key.equals("age")?"Возраст: "+values[0]:key.equals("intro")?"Первая строка\\nВторая строка":key;
        ItemViewCatalog.Wrap wrap=(s,width)->Arrays.asList(s.split("\n",-1));
        check(c.label("minecraft:written_book",0,"name",source,text).equals("Книга логики"));
        check(c.label("minecraft:book",0,"name",source,text)==null);
        check(c.label("minecraft:written_book",1,"name",source,text)==null);
        check(c.label("minecraft:written_book",0,"lore",source,text)==null);
        check(c.label("minecraft:written_book",0,"name",source+"!",text)==null);
        check(c.label("minecraft:written_book",0,"name",null,text)==null);
        check(c.label("contenttweaker:steve",0,"lore","Age: 23",text).equals("Возраст: 23"));
        check(c.label("contenttweaker:steve",0,"lore","Age: -5",text).equals("Возраст: -5"));
        for(String raw:Arrays.asList("Age: 2.3","Age: 23 trailing","Age: 999999999","Unrelated 23"))check(c.label("contenttweaker:steve",0,"lore",raw,text)==null);
        check(c.label("contenttweaker:alex",0,"lore","Age: 23",text)==null);
        ItemViewCatalog.Text missing=(key,values)->key;
        check(c.label("contenttweaker:steve",0,"lore","Age: 23",missing)==null);
        List<String> pages=c.pages("minecraft:written_book",0,source,author,original,text,wrap);
        check(pages.equals(Arrays.asList("Первая строка\nВторая строка\n\nДевять условий.")));
        check(original.equals(before));
        check(c.knownBook("minecraft:written_book",0,source,author,original));
        check(!c.knownBook("minecraft:written_book",0,source,"DifferentPlayer",original));
        check(!c.knownBook("minecraft:written_book",0,source,author,Arrays.asList("Changed")));
        check(!c.knownBook("minecraft:written_book",0,"Other title",author,original));
        check(!c.knownBook("minecraft:written_book",0,source,author,null));
        check(c.pages("minecraft:written_book",0,source,"Another author",original,text,wrap)==null);
        check(c.pages("minecraft:written_book",0,"Another title",author,original,text,wrap)==null);
        check(c.pages("minecraft:written_book",0,source,author,Arrays.asList("Changed"),text,wrap)==null);
        check(c.pages("minecraft:written_book",0,source,author,original,missing,wrap)==null);
        List<String> many=c.pages("minecraft:written_book",0,source,author,original,text,(s,w)->Collections.nCopies(14,"Строка"));
        check(many.size()==4&&many.get(0).split("\n",-1).length==12&&many.get(2).split("\n",-1).length==12);
        List<String> shortParts=c.pages("minecraft:written_book",0,source,author,original,text,(s,w)->Collections.nCopies(s.startsWith("Первая")?10:4,"Строка"));
        check(shortParts.size()==2&&shortParts.get(0).split("\n",-1).length==10&&shortParts.get(1).split("\n",-1).length==4);
        try{pages.add("changed");throw new AssertionError("mutable view");}catch(UnsupportedOperationException expected){checks++;}
        check(!ItemViewCatalog.pageDigest(Arrays.asList("a","bc")).equals(ItemViewCatalog.pageDigest(Arrays.asList("ab","c"))));
        check(ItemViewCatalog.digest("abc").equals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
        check(ItemViewCatalog.jsonPage("Кавычки \"тест\"\\\n\t").equals("{\"text\":\"Кавычки \\\"тест\\\"\\\\\\u000a\\u0009\"}"));
        invalid(profile.replace("schema=1","schema=2"));
        invalid(profile+"schema=1\n");
        invalid(profile.replace("label.count=2","label.count=97"));
        invalid(profile.replace("label.0.meta=0","label.0.meta=-1"));
        invalid(profile.replace("label.0.field=name","label.0.field=nbt"));
        invalid(profile.replace("label.0.mode=exact","label.0.mode=global"));
        invalid(profile.replace(ItemViewCatalog.digest(source),"unreviewed"));
        invalid(profile.replace("book.0.parts=2","book.0.parts=0"));
        invalid(new String(new char[65537]).replace('\0','x'));
        try{ItemViewCatalog.read(null);throw new AssertionError("missing profile accepted");}catch(IOException expected){checks++;}
        try(InputStream profileStream=ItemViewCatalog.class.getResourceAsStream("/assets/omkalityclient/itemviews/dj2-2.23.4.properties")) {
            check(profileStream!=null&&ItemViewCatalog.read(profileStream)!=null);
        }
        System.out.println("item-view catalog checks="+checks);
    }
}
