package net.omkality.client.mixin.guides;

import net.minecraft.client.gui.ChatLine;
import net.minecraft.util.text.ITextComponent;
import net.omkality.client.guides.GuideChatLifetime;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/** Keep vanilla wrapping, deletion/history and fade; adjust only matched lines' age. */
@Mixin(targets="net.minecraft.client.gui.GuiNewChat",remap=false)
public abstract class GuideChatLifetimeMixin {
    @Redirect(method="func_146237_a(Lnet/minecraft/util/text/ITextComponent;IIZ)V",at=@At(value="NEW",target="net/minecraft/client/gui/ChatLine"),require=2,allow=2,remap=false)
    private ChatLine omkality$remember(int counter,ITextComponent fragment,int id,ITextComponent original,int originalId,int originalCounter,boolean refresh) {
        ChatLine line=new ChatLine(counter,fragment,id);
        GuideChatLifetime.remember(line,original.func_150260_c());return line;
    }
    @Redirect(method="func_146230_a(I)V",at=@At(value="INVOKE",target="Lnet/minecraft/client/gui/ChatLine;func_74540_b()I"),require=1,allow=1,remap=false)
    private int omkality$age(ChatLine line,int current) {return GuideChatLifetime.counter(line,line.func_74540_b(),current);}
}
