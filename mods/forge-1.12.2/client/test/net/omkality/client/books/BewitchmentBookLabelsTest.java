package net.omkality.client.books;

import java.lang.reflect.Method;
import net.minecraft.client.resources.I18n;
import net.omkality.client.mixin.books.BewitchmentRitualLabelsMixin;

/** Compiled handlers with a locale fixture; actual processor runs in the game. */
public final class BewitchmentBookLabelsTest {
    private static int checks;
    private static void check(boolean value) {
        if (!value) throw new AssertionError("ritual label " + checks);
        checks++;
    }
    public static void main(String[] args) throws Exception {
        Method start = BewitchmentRitualLabelsMixin.class.getDeclaredMethod("omkality$startingCost",String.class);
        Method run = BewitchmentRitualLabelsMixin.class.getDeclaredMethod("omkality$runningCost",String.class);
        start.setAccessible(true); run.setAccessible(true);
        String sk = "omkalityclient.books.ritual.starting", rk = "omkalityclient.books.ritual.running";
        String so = "Starting Cost: ", ro = "Running Cost: ";
        I18n.values.put(sk,"Запуск:"); I18n.values.put(rk,"Расход:");
        I18n.locale = "ru_ru";
        check(start.invoke(null,so).equals("Запуск: "));
        check(run.invoke(null,ro).equals("Расход: "));
        for (String locale : new String[] {"en_us","de_de","uk_ua"}) {
            I18n.locale = locale;
            check(start.invoke(null,so).equals(so)); check(run.invoke(null,ro).equals(ro));
        }
        I18n.locale = "ru_ru";
        I18n.values.clear();
        check(start.invoke(null,so).equals(so)); check(run.invoke(null,ro).equals(ro));
        I18n.values.put(sk,""); I18n.values.put(rk,"");
        check(start.invoke(null,so).equals(so)); check(run.invoke(null,ro).equals(ro));
        I18n.values.put(sk,null); I18n.values.put(rk,null);
        check(start.invoke(null,so).equals(so)); check(run.invoke(null,ro).equals(ro));
        I18n.values.put(sk,"Новый запуск:"); I18n.values.put(rk,"Новый расход:");
        check(start.invoke(null,so).equals("Новый запуск: "));
        check(run.invoke(null,ro).equals("Новый расход: "));
        System.out.println("ritual label checks=" + checks);
    }
}
