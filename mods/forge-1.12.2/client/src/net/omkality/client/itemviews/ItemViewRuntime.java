package net.omkality.client.itemviews;

import java.io.InputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiScreenBook;
import net.minecraft.client.resources.I18n;
import net.minecraft.item.ItemStack;
import net.minecraft.nbt.*;

/** Local rendering boundary. There are no ItemStack setters or NBT writes here. */
public final class ItemViewRuntime {
    private static volatile ItemViewCatalog catalog;
    private static boolean attempted;
    private static final AtomicBoolean warned=new AtomicBoolean();
    private static final ItemViewCatalog.Text TEXT=(key,args)->I18n.func_135052_a(key,args);
    private ItemViewRuntime() {}
    private static void warn(Throwable error) {
        if(warned.compareAndSet(false,true))System.err.println("[OmkalityClient] Item-view locale uses original display: "+error.getClass().getSimpleName());
    }
    private static synchronized ItemViewCatalog rules() {
        if(!Boolean.getBoolean("omkality.itemviews.locale.forge112")||!"ru_ru".equals(I18n.func_135052_a("omkalityclient.books.locale")))return null;
        if(attempted)return catalog;attempted=true;
        String profile=System.getProperty("omkality.itemviews.profile","");
        if(!profile.matches("[a-z0-9][a-z0-9._-]{0,63}"))return null;
        try(InputStream in=ItemViewCatalog.class.getResourceAsStream("/assets/omkalityclient/itemviews/"+profile+".properties")) {
            catalog=ItemViewCatalog.read(in);
        }catch(Exception|LinkageError error){warn(error);}
        return catalog;
    }
    private static String id(ItemStack stack) {
        return stack==null||stack.func_190926_b()||stack.func_77973_b().getRegistryName()==null?"":stack.func_77973_b().getRegistryName().toString();
    }
    private static NBTTagCompound tag(ItemStack stack) {return stack.func_77978_p();}
    private static List<String> sourcePages(NBTTagCompound tag) {
        if(tag==null||!tag.func_150297_b("pages",9))return null;
        NBTTagList list=tag.func_150295_c("pages",8);if(list.func_74745_c()>100)return null;
        List<String> result=new ArrayList<String>();
        for(int i=0;i<list.func_74745_c();i++)result.add(list.func_150307_f(i));
        return result;
    }
    private static String canonicalName(ItemStack stack,ItemViewCatalog rules) {
        NBTTagCompound tag=tag(stack);if(tag==null)return null;
        String item=id(stack);
        if("minecraft:written_book".equals(item)&&!rules.knownBook(item,stack.func_77960_j(),tag.func_74779_i("title"),tag.func_74779_i("author"),sourcePages(tag)))return null;
        NBTTagCompound display=tag.func_74775_l("display");
        if(display.func_150297_b("Name",8)) {
            String named=display.func_74779_i("Name");
            if("minecraft:written_book".equals(item)&&!named.equals(tag.func_74779_i("title")))return null;
            return named;
        }
        return "minecraft:written_book".equals(id(stack))&&tag.func_150297_b("title",8)?tag.func_74779_i("title"):null;
    }
    private static String replace(String line,String source,String replacement) {
        if(source==null||source.isEmpty()||replacement==null)return line;
        int start=line.indexOf(source);if(start<0||line.indexOf(source,start+source.length())>=0)return line;
        return line.substring(0,start)+replacement+line.substring(start+source.length());
    }
    /** Called only from the hotbar rendering call site, never ItemStack.getDisplayName globally. */
    public static String hotbarName(ItemStack stack) {
        String original=stack.func_82833_r();ItemViewCatalog rules=rules();if(rules==null)return original;
        String raw=canonicalName(stack,rules);return replace(original,raw,rules.label(id(stack),stack.func_77960_j(),"name",raw,TEXT));
    }
    public static void tooltip(ItemStack stack,List<String> visible) {
        ItemViewCatalog rules=rules();if(rules==null||visible==null||visible.isEmpty()||id(stack).isEmpty())return;
        String item=id(stack),raw=canonicalName(stack,rules);int meta=stack.func_77960_j();
        visible.set(0,replace(visible.get(0),raw,rules.label(item,meta,"name",raw,TEXT)));
        NBTTagCompound tag=tag(stack);if(tag==null)return;
        NBTTagList lore=tag.func_74775_l("display").func_150295_c("Lore",8);if(lore.func_74745_c()>64)return;
        for(int row=0;row<lore.func_74745_c();row++) {
            raw=lore.func_150307_f(row);String translated=rules.label(item,meta,"lore",raw,TEXT);if(translated==null)continue;
            for(int line=1;line<visible.size();line++)visible.set(line,replace(visible.get(line),raw,translated));
        }
    }
    private static Field field(String name)throws ReflectiveOperationException {
        Field f=GuiScreenBook.class.getDeclaredField(name);f.setAccessible(true);return f;
    }
    public static void book(GuiScreenBook screen) {
        ItemViewCatalog rules=rules();if(rules==null||screen.getClass()!=GuiScreenBook.class)return;
        try {
            if(field("field_146475_i").getBoolean(screen))return;
            ItemStack stack=(ItemStack)field("field_146474_h").get(screen);
            NBTTagCompound tag=tag(stack);if(tag==null)return;
            List<String> original=sourcePages(tag);if(original==null)return;
            List<String> translated=rules.pages(id(stack),stack.func_77960_j(),tag.func_74779_i("title"),tag.func_74779_i("author"),original,TEXT,(text,width)->Minecraft.func_71410_x().field_71466_p.func_78271_c(text,width));
            if(translated==null||translated.isEmpty())return;
            NBTTagList detached=new NBTTagList();
            for(String page:translated)detached.func_74742_a(new NBTTagString(ItemViewCatalog.jsonPage(page)));
            // The GUI's list is detached; the canonical stack and network data are never changed.
            Field pages=field("field_146483_y"),total=field("field_146476_w"),current=field("field_146484_x"),cache=field("field_175386_A"),cachedPage=field("field_175387_B");
            Method buttons=GuiScreenBook.class.getDeclaredMethod("func_146464_h");buttons.setAccessible(true);
            int selected=Math.min(current.getInt(screen),translated.size()-1);
            pages.set(screen,detached);total.setInt(screen,translated.size());current.setInt(screen,selected);cache.set(screen,null);cachedPage.setInt(screen,-1);buttons.invoke(screen);
        }catch(ReflectiveOperationException|RuntimeException|LinkageError error){warn(error);}
    }
}
