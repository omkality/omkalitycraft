import java.io.File;
import java.io.InputStream;
import java.lang.reflect.Method;

/** Read only: exercise the pinned WorldEdit ZIP path selection without Minecraft. */
public class WorldEditSnapshotProbe {
    public static void main(String[] args) throws Exception {
        Class<?> cls = Class.forName("com.sk89q.worldedit.world.storage.ZippedMcRegionChunkStore");
        Object store = cls.getConstructor(File.class).newInstance(new File(args[0]));
        Method method = cls.getDeclaredMethod("getInputStream", String.class, String.class);
        method.setAccessible(true);
        try {
            try (InputStream stream = (InputStream) method.invoke(store, "r.0.0.mca", "lab-world")) {
                byte[] marker = new byte[64];
                int count = stream.read(marker);
                System.out.println(new String(marker, 0, count, "UTF-8"));
            }
        } finally {
            cls.getMethod("close").invoke(store);
        }
    }
}
