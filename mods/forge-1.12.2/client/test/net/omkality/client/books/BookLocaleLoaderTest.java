package net.omkality.client.books;

import java.util.Collections;
import net.omkality.client.bootstrap.BookLocaleMixinLoader;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.Side;
import zone.rong.mixinbooter.ILateMixinLoader;

/** Side/opt-in boundary fixture; actual Mixin transformation needs a real game. */
public final class BookLocaleLoaderTest {
    private static int checks;
    private static void check(boolean value) {
        if (!value) throw new AssertionError("late loader " + checks);
        checks++;
    }
    public static void main(String[] args) {
        String property = "omkality.books.locale.forge112";
        String previous = System.getProperty(property);
        Side previousSide = FMLLaunchHandler.selected;
        BookLocaleMixinLoader loader = new BookLocaleMixinLoader();
        try {
            check(loader instanceof ILateMixinLoader);
            for (Side side : Side.values()) {
                FMLLaunchHandler.selected = side;
                System.clearProperty(property);
                check(loader.getMixinConfigs().isEmpty());
                for (String value : new String[] { "true", "false", "invalid" }) {
                    System.setProperty(property, value);
                    check(loader.getMixinConfigs().equals(side == Side.CLIENT && value.equals("true")
                        ? Collections.singletonList("mixins.omkalityclient.books.json")
                        : Collections.emptyList()));
                }
            }
        } finally {
            FMLLaunchHandler.selected = previousSide;
            if (previous == null) System.clearProperty(property);
            else System.setProperty(property, previous);
        }
        System.out.println("book late loader checks=" + checks);
    }
}
