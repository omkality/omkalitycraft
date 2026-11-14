package net.omkality.client.books;

import net.minecraft.client.resources.I18n;

/** Presentation only; read the current locale on every call to support reloads. */
public final class BookLocaleText {
    private BookLocaleText() {}
    private static boolean russian() {
        return "ru_ru".equals(I18n.func_135052_a("omkalityclient.books.locale"));
    }
    public static String label(String key, String original) {
        if (!russian()) return original;
        String translated=I18n.func_135052_a(key);
        // Minecraft .lang values retain escaped newlines; decode only our two labels.
        return translated==null || translated.isEmpty() || translated.equals(key) ? original : translated.replace("\\n","\n");
    }
    /** Null preserves the original target behavior, including invalid versions. */
    public static String ordinal(int version) {
        return version>0 && russian() ? Integer.toString(version) : null;
    }
}
