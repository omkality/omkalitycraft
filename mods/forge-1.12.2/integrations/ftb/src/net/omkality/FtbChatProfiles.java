package net.omkality;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.UUID;

/** Read the reviewed FTB command wrapper and historical chat nickname. */
final class FtbChatProfiles {
    private final Field mirrored;
    private final Method universe, player, playerData, nickname;

    FtbChatProfiles() throws ReflectiveOperationException {
        Class<?> ranksCommand = Class.forName("com.feed_the_beast.ftbutilities.ranks.CommandOverride");
        Class<?> universeType = Class.forName("com.feed_the_beast.ftblib.lib.data.Universe");
        Class<?> playerType = Class.forName("com.feed_the_beast.ftblib.lib.data.ForgePlayer");
        Class<?> data = Class.forName("com.feed_the_beast.ftbutilities.data.FTBUtilitiesPlayerData");
        mirrored = ranksCommand.getField("mirrored");
        universe = universeType.getMethod("get");
        player = universeType.getMethod("getPlayer", UUID.class);
        playerData = data.getMethod("get", playerType);
        nickname = data.getMethod("getNickname");
    }

    Object original(Object command) throws IllegalAccessException {
        return mirrored.getDeclaringClass().isInstance(command) ? mirrored.get(command) : command;
    }

    String nickname(UUID id) throws ReflectiveOperationException {
        Object current = universe.invoke(null);
        if (current == null) return "";
        Object entry = player.invoke(current, id);
        if (entry == null) return "";
        return (String) nickname.invoke(playerData.invoke(null, entry));
    }
}
