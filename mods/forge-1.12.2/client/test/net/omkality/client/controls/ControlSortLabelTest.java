package net.omkality.client.controls;

import java.lang.reflect.Method;
import java.util.Collections;
import net.minecraft.client.resources.I18n;
import net.omkality.client.bootstrap.ControlsLocaleMixinLoader;
import net.omkality.client.mixin.controls.ControlSortLabelMixin;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.Side;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import zone.rong.mixinbooter.ILateMixinLoader;

/** Compiled handler/opt-in controls; real transformation and layout need the game. */
public final class ControlSortLabelTest {
    private static int checks;
    private static void check(boolean value){if(!value)throw new AssertionError("controls "+checks);checks++;}
    public static void main(String[] args)throws Exception {
        Method handler=ControlSortLabelMixin.class.getDeclaredMethod("omkality$sortLabel",CallbackInfoReturnable.class);handler.setAccessible(true);
        ControlSortLabelMixin target=new ControlSortLabelMixin(){};
        String[] original={"Default","A->Z","Z->A"},keys={"sortnone","sortaz","sortza"},translated={"Группы","А-Я","Я-А"};
        for(int i=0;i<3;i++)I18n.values.put("endermodpacktweaks.options."+keys[i],translated[i]);
        for(String locale:new String[]{"ru_ru","en_us","de_de","uk_ua"}) {
            I18n.locale=locale;
            for(int i=0;i<3;i++) {
                CallbackInfoReturnable<String> result=new CallbackInfoReturnable<String>("test",true,original[i]);handler.invoke(target,result);
                check(result.getReturnValue().equals(locale.equals("ru_ru")?translated[i]:original[i])&&result.isCancelled()==locale.equals("ru_ru"));
            }
        }
        I18n.locale="ru_ru";
        CallbackInfoReturnable<String> unknown=new CallbackInfoReturnable<String>("test",true,"Future mode");handler.invoke(target,unknown);check(!unknown.isCancelled()&&unknown.getReturnValue().equals("Future mode"));
        String key="endermodpacktweaks.options.sortnone";
        for(String missing:new String[]{key,"",null}) {
            I18n.values.put(key,missing);CallbackInfoReturnable<String> result=new CallbackInfoReturnable<String>("test",true,"Default");handler.invoke(target,result);check(!result.isCancelled()&&result.getReturnValue().equals("Default"));
        }
        String property="omkality.appearance.forge112",before=System.getProperty(property);Side sideBefore=FMLLaunchHandler.selected;
        ControlsLocaleMixinLoader loader=new ControlsLocaleMixinLoader();check(loader instanceof ILateMixinLoader);
        try {
            for(Side side:Side.values()) {
                FMLLaunchHandler.selected=side;System.clearProperty(property);check(loader.getMixinConfigs().isEmpty());
                for(String value:new String[]{"true","false","invalid"}) {
                    System.setProperty(property,value);check(loader.getMixinConfigs().equals(side==Side.CLIENT&&value.equals("true")?Collections.singletonList("mixins.omkalityclient.controls.json"):Collections.emptyList()));
                }
            }
        }finally {
            FMLLaunchHandler.selected=sideBefore;
            if(before==null)System.clearProperty(property);else System.setProperty(property,before);
        }
        System.out.println("controls locale checks="+checks);
    }
}
