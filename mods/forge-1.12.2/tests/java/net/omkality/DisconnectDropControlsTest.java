package net.omkality;

import java.util.concurrent.atomic.AtomicBoolean;
import net.omkality.patches.DisconnectDropScope;

/** The compatibility exception must never escape its native close callback. */
public final class DisconnectDropControlsTest {
    private static int checks;
    private static void check(boolean value) {if(!value)throw new AssertionError();checks++;}
    public static void main(String[] args)throws Exception {
        final Object actor=new Object(),other=new Object(),stack=new String("item");
        Object[] sources={stack};
        check(!DisconnectDropScope.permits(actor,stack));
        try(DisconnectDropScope outer=DisconnectDropScope.enter(actor,sources)) {
            check(DisconnectDropScope.permits(actor,stack));
            check(!DisconnectDropScope.permits(other,stack));
            check(!DisconnectDropScope.permits(actor,new String("item")));
            check(!DisconnectDropScope.permits(actor,null));
            sources[0]=other;
            check(DisconnectDropScope.permits(actor,stack)&&!DisconnectDropScope.permits(actor,other));
            AtomicBoolean escaped=new AtomicBoolean(true);
            Thread child=new Thread(new Runnable(){public void run(){escaped.set(DisconnectDropScope.active()||DisconnectDropScope.permits(actor,stack));}});
            child.start();child.join();check(!escaped.get());
            try(DisconnectDropScope inner=DisconnectDropScope.enter(other,new Object[]{other})) {
                check(DisconnectDropScope.permits(other,other)&&!DisconnectDropScope.permits(actor,stack));
                try{outer.close();throw new AssertionError();}catch(IllegalStateException expected){check(DisconnectDropScope.permits(other,other));}
            }
            check(DisconnectDropScope.permits(actor,stack));
        }
        check(!DisconnectDropScope.active()&&!DisconnectDropScope.permits(actor,stack));
        try(DisconnectDropScope scope=DisconnectDropScope.enter(actor,new Object[]{stack})) {
            throw new IllegalArgumentException("expected native failure fixture");
        }catch(IllegalArgumentException expected){check(!DisconnectDropScope.active());}
        try{DisconnectDropScope.enter(actor,new Object[15]);throw new AssertionError();}
        catch(IllegalArgumentException expected){check(!DisconnectDropScope.active());}
        System.out.println("Native disconnect drop scope controls passed: "+checks);
    }
}
