package net.omkality;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Collections;
import java.util.Map;
import net.minecraftforge.fml.common.FMLCommonHandler;

/** Identifies the player's current server dimension without a client update. */
final class WorldCommand {
    private static final String NAME = "world";

    static void install(int resource) throws Exception {
        Object server = FMLCommonHandler.instance().getMinecraftServerInstance();
        Object manager = server.getClass().getMethod("func_71187_D").invoke(server);
        Class<?> command = Class.forName("net.minecraft.command.ICommand");
        Class<?> player = Class.forName("net.minecraft.entity.player.EntityPlayerMP");
        Class<?> text = Class.forName("net.minecraft.util.text.ITextComponent");
        Field dimension = player.getField("field_71093_bK");
        Method send = player.getMethod("func_145747_a", text);
        Method name = command.getMethod("func_71517_b");
        Constructor<?> message = Class.forName("net.minecraft.util.text.TextComponentString").getConstructor(String.class);
        Map<?, ?> registered = (Map<?, ?>) manager.getClass().getMethod("func_71555_a").invoke(manager);
        if (registered.containsKey(NAME)) throw new IllegalStateException("World command already registered");
        Object handler = Proxy.newProxyInstance(command.getClassLoader(), new Class<?>[] {command},
            (proxy, method, args) -> {
                switch (method.getName()) {
                    case "hashCode": return System.identityHashCode(proxy);
                    case "equals": return proxy == args[0];
                    case "toString":
                    case "func_71517_b": return NAME;
                    case "func_71518_a": return "/world";
                    case "func_71514_a":
                    case "func_184883_a": return Collections.emptyList();
                    case "func_82358_a": return false;
                    case "compareTo": return NAME.compareTo(String.valueOf(name.invoke(args[0])));
                    case "func_184882_a": return player.isInstance(args[1]);
                    case "func_184881_a":
                        if (player.isInstance(args[1])) send.invoke(args[1], message.newInstance(
                            "Вы сейчас в мире: " + label(dimension.getInt(args[1]), resource)));
                        return null;
                    default: throw new UnsupportedOperationException("Unknown world command callback");
                }
            });
        manager.getClass().getMethod("func_71560_a", command).invoke(manager, handler);
    }

    private static String label(int dimension, int resource) {
        if (dimension == resource) return "Ресурсный мир";
        switch (dimension) {
            case 0: return "Основной мир";
            case -1: return "Ад";
            case 1: return "Край";
            case 7: return "Сумеречный лес";
            default: return "Измерение " + dimension;
        }
    }
}
