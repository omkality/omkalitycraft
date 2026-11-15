package net.omkality.client.defaults;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import net.omkality.client.bootstrap.DefaultOptionsMixinLoader;
import net.minecraftforge.fml.relauncher.FMLLaunchHandler;
import net.minecraftforge.fml.relauncher.Side;

/** JVM-only parser/policy contract; real DefaultOptions call sites are tested in game. */
public final class KnownKeySnapshotTest {
    private static int checks;
    private static void check(boolean value) {
        if (!value) throw new AssertionError("known-key snapshot " + checks);
        checks++;
    }
    private static Set<String> parse(String text) throws IOException {
        return KnownKeySnapshot.parse(text.getBytes(StandardCharsets.UTF_8));
    }
    private static void invalid(byte[] bytes) throws Exception {
        try { KnownKeySnapshot.parse(bytes); throw new AssertionError("invalid bytes accepted"); }
        catch (IOException expected) { checks++; }
    }
    public static void main(String[] args) throws Exception {
        String ru = "Переключить режим Очков с сенсорами";
        String original = "lang:ru_ru\r\nkey_quests:37\r\nkey_" + ru + ":88\r\nkey_shift:24:SHIFT\nkey_ctrl:31:CONTROL\nkey_off:0:NONE\nkey_attack:-100\nkey_alt:18:ALT\n";
        Set<String> saved = parse(original);
        check(saved.equals(new HashSet<String>(Arrays.asList("quests",ru,"shift","ctrl","off","attack","alt"))));
        check(parse(original + "key_quests:41\n").equals(saved));
        check(parse("# comment\nresourcePacks:[\"FM_NewFont\"]\nnot-a-key:value\n").isEmpty());
        check(parse("key_invalid:value\nkey_no_code:\n").isEmpty());
        check(parse("").isEmpty());
        try { saved.add("other"); throw new AssertionError("mutable snapshot"); }
        catch (UnsupportedOperationException expected) { checks++; }

        List<Object> known = new ArrayList<Object>();
        // Previously premature records must not suppress still-unsaved pack defaults.
        check(!KnownKeySnapshot.record(known,"unsaved",saved) && known.isEmpty());
        check(KnownKeySnapshot.record(known,"quests",saved));
        check(KnownKeySnapshot.record(known,ru,saved));
        check(!KnownKeySnapshot.record(known,"another_new_default",saved));
        check(known.equals(Arrays.<Object>asList("quests",ru)));
        // An unreadable snapshot keeps the original mod's behavior.
        check(KnownKeySnapshot.record(known,"fallback",null));
        check(known.equals(Arrays.<Object>asList("quests",ru,"fallback")));
        check(!KnownKeySnapshot.record(known,"not_saved",Collections.<String>emptySet()));

        invalid(new byte[] {(byte)0xc3,(byte)0x28});
        invalid(new byte[KnownKeySnapshot.MAX_BYTES+1]);
        StringBuilder huge = new StringBuilder();
        for(int n=0;n<4097;n++)huge.append("key_test.").append(n).append(":0\n");
        invalid(huge.toString().getBytes(StandardCharsets.UTF_8));

        Path directory = Files.createTempDirectory("omk-knownkeys-");
        Path file = directory.resolve("options.txt");
        try {
            check(KnownKeySnapshot.read(file).isEmpty());
            byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
            Files.write(file,bytes);
            check(KnownKeySnapshot.read(file).equals(saved));
            check(Arrays.equals(bytes,Files.readAllBytes(file)));
            try { KnownKeySnapshot.read(directory); throw new AssertionError("directory accepted"); }
            catch(IOException expected) { checks++; }
            Path link=directory.resolve("linked-options.txt");
            Files.createSymbolicLink(link,file.getFileName());
            try {
                try { KnownKeySnapshot.read(link); throw new AssertionError("link accepted"); }
                catch(IOException expected) { checks++; }
            } finally { Files.delete(link); }
        } finally { Files.deleteIfExists(file); Files.delete(directory); }

        String property="omkality.defaults.persist.forge112";
        String previous=System.getProperty(property);
        Side before=FMLLaunchHandler.selected;
        DefaultOptionsMixinLoader loader=new DefaultOptionsMixinLoader();
        try {
            for(Side side:Side.values()) {
                FMLLaunchHandler.selected=side;
                System.clearProperty(property);check(loader.getMixinConfigs().isEmpty());
                for(String value:new String[]{"false","true","invalid"}) {
                    System.setProperty(property,value);
                    check(loader.getMixinConfigs().equals(side==Side.CLIENT && value.equals("true")
                        ?Collections.singletonList("mixins.omkalityclient.defaults.json")
                        :Collections.emptyList()));
                }
            }
        } finally {
            FMLLaunchHandler.selected=before;
            if(previous==null)System.clearProperty(property);else System.setProperty(property,previous);
        }
        System.out.println("known-key persistence checks="+checks);
    }
}
