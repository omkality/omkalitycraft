package net.omkality.client.audio;

import java.lang.reflect.Field;
import java.util.Locale;
import net.minecraft.client.Minecraft;
import net.minecraft.client.audio.SoundHandler;
import net.minecraft.client.audio.SoundManager;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.fml.common.gameevent.TickEvent;
import net.minecraftforge.fml.relauncher.Side;
import org.apache.logging.log4j.LogManager;

/** Reopen the legacy OpenAL sound engine when Windows changes its default output. */
@Mod.EventBusSubscriber(modid = "omkalityclient", value = Side.CLIENT)
public final class FollowSystemAudio {
    private static final boolean WINDOWS = System.getProperty("os.name", "").toLowerCase(Locale.ROOT).startsWith("windows");
    private static WindowsAudioEndpoint watcher;
    private static Field manager;
    private static Field loaded;
    private static String applied;
    private static boolean unavailable;

    @SubscribeEvent
    public static void tick(TickEvent.ClientTickEvent event) {
        if (!WINDOWS || unavailable || event.phase != TickEvent.Phase.END) {
            return;
        }
        try {
            if (watcher == null) {
                manager = soundField(SoundHandler.class, "field_147694_f");
                loaded = soundField(SoundManager.class, "field_148617_f");
                watcher = new WindowsAudioEndpoint();
                Thread worker = new Thread(watcher, "Omkality playback device");
                worker.setDaemon(true);
                worker.start();
                return;
            }
            String output = watcher.current();
            if (output == null || output.equals(applied)) {
                return;
            }
            if (applied == null || output.isEmpty()) {
                applied = output;
                return;
            }
            SoundHandler handler = Minecraft.func_71410_x().func_147118_V();
            SoundManager sound = handler == null ? null : (SoundManager) manager.get(handler);
            if (sound != null && loaded.getBoolean(sound)) {
                sound.func_148596_a();
                applied = output;
                LogManager.getLogger("OmkalityClient").info("Reopened game audio for the Windows default playback device");
            }
        } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
            unavailable = true;
            LogManager.getLogger("OmkalityClient").warn("Could not follow the Windows playback device", error);
        }
    }

    private static Field soundField(Class<?> type, String name) throws NoSuchFieldException {
        Field field = type.getDeclaredField(name);
        field.setAccessible(true);
        return field;
    }

    private FollowSystemAudio() {}
}
