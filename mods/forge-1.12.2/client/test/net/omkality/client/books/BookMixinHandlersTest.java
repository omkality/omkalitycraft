package net.omkality.client.books;
import java.lang.reflect.Method;
import net.omkality.client.mixin.books.ExtraUtilitiesBookLabelsMixin;
import net.omkality.client.mixin.books.PatchouliEditionMixin;
import net.minecraft.client.resources.I18n;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
/** Calls the compiled handler methods; this is not a Mixin transformation test. */
public final class BookMixinHandlersTest {
    private static int checks;
    private static void check(boolean condition){if(!condition)throw new AssertionError("handler "+checks);checks++;}
    public static void main(String[] args)throws Exception {
        Method cover=ExtraUtilitiesBookLabelsMixin.class.getDeclaredMethod("omkality$cover",String.class);cover.setAccessible(true);
        Method toc=ExtraUtilitiesBookLabelsMixin.class.getDeclaredMethod("omkality$contents",String.class);toc.setAccessible(true);
        Method edition=PatchouliEditionMixin.class.getDeclaredMethod("omkality$russianEdition",int.class,CallbackInfoReturnable.class);edition.setAccessible(true);
        String original="Extra Utilities 2\nManual\n(temp GUI stand in)",originalToc="Table of Contents\n\n";
        I18n.values.put("omkalityclient.books.xu2.cover","Extra Utilities 2\\nРуководство");
        I18n.values.put("omkalityclient.books.xu2.contents","Оглавление\\n\\n");
        I18n.locale="ru_ru";
        check(cover.invoke(null,original).equals("Extra Utilities 2\nРуководство"));
        check(toc.invoke(null,originalToc).equals("Оглавление\n\n"));
        for(int number:new int[]{1,2,3,11,12,13,21,100,101,Integer.MAX_VALUE}) {
            CallbackInfoReturnable<String> result=new CallbackInfoReturnable<String>("test",true,"original ordinal");edition.invoke(null,number,result);
            check(result.isCancelled());check(result.getReturnValue().equals(Integer.toString(number)));
        }
        for(int number:new int[]{0,-1,Integer.MIN_VALUE}){
            CallbackInfoReturnable<String> result=new CallbackInfoReturnable<String>("test",true,"unchanged");edition.invoke(null,number,result);check(!result.isCancelled());check(result.getReturnValue().equals("unchanged"));
        }
        for(String locale:new String[]{"en_us","de_de","uk_ua"}){
            I18n.locale=locale;check(cover.invoke(null,original).equals(original));check(toc.invoke(null,originalToc).equals(originalToc));
            CallbackInfoReturnable<String> result=new CallbackInfoReturnable<String>("test",true,"3rd");edition.invoke(null,3,result);check(!result.isCancelled());check(result.getReturnValue().equals("3rd"));
        }
        I18n.locale="ru_ru";I18n.values.clear();check(cover.invoke(null,original).equals(original));check(toc.invoke(null,originalToc).equals(originalToc));
        System.out.println("compiled book handler checks="+checks);
    }
}
