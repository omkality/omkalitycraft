package net.minecraft.client.resources;
import java.util.HashMap;
import java.util.Map;
/** JVM fixture only, never a runtime resource or game class. */
public final class I18n {
    public static final Map<String,String> values=new HashMap<String,String>();
    public static String locale="en_us";
    public static String func_135052_a(String key,Object... arguments) {
        if(key.equals("omkalityclient.books.locale")) return locale;
        return values.containsKey(key)?values.get(key):key;
    }
}
