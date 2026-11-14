package net.omkality.client.books;
import net.minecraft.client.resources.I18n;
public final class BookLocaleTextTest {
    private static int checks;
    private static void check(boolean value) { if(!value)throw new AssertionError("check "+checks);checks++; }
    public static void main(String[] args) {
        String key="omkalityclient.books.xu2.cover",original="original";
        I18n.values.put(key,"Руководство");
        for(String language:new String[]{"en_us","de_de","uk_ua","missing-key"}) {
            I18n.locale=language;check(BookLocaleText.label(key,original).equals(original));check(BookLocaleText.ordinal(3)==null);
        }
        I18n.locale="ru_ru";check(BookLocaleText.label(key,original).equals("Руководство"));
        for(int version:new int[]{1,2,3,4,11,12,13,21,100,101,Integer.MAX_VALUE})check(BookLocaleText.ordinal(version).equals(Integer.toString(version)));
        check(BookLocaleText.ordinal(0)==null);check(BookLocaleText.ordinal(-1)==null);check(BookLocaleText.ordinal(Integer.MIN_VALUE)==null);
        I18n.values.remove(key);check(BookLocaleText.label(key,original).equals(original));
        I18n.values.put(key,"");check(BookLocaleText.label(key,original).equals(original));
        I18n.values.put(key,null);check(BookLocaleText.label(key,original).equals(original));
        I18n.values.put(key,"Перезагрузка ресурсов");check(BookLocaleText.label(key,original).equals("Перезагрузка ресурсов"));
        I18n.values.put(key,"Первая\\nВторая\\n\\n");check(BookLocaleText.label(key,original).equals("Первая\nВторая\n\n"));
        I18n.values.put(key,"100% \\t");check(BookLocaleText.label(key,original).equals("100% \\t"));
        I18n.locale="en_us";check(BookLocaleText.label(key,original).equals(original));
        System.out.println("book locale helper checks="+checks);
    }
}
