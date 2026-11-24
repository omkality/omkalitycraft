package net.omkality.patches;

import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** Keep the native portal search and its possible exits inside the DJ2 border. */
public final class NetherPortalBorder {
    // Vanilla searches 128 blocks outward. A frame can span 21 blocks and
    // its exit needs space for the player's offset and bounding box.
    private static final double PORTAL_MARGIN = 128 + 21 + 3;

    private static Field destination;
    private static Field provider;
    private static Field entityX;
    private static Field entityY;
    private static Field entityZ;
    private static Method getDimension;
    private static Method getBorder;
    private static Method minX;
    private static Method minZ;
    private static Method maxX;
    private static Method maxZ;
    private static Method setPosition;

    public static void install() throws ReflectiveOperationException {
        Class<?> teleporter = Class.forName("net.minecraft.world.Teleporter");
        Class<?> world = Class.forName("net.minecraft.world.World");
        Class<?> border = Class.forName("net.minecraft.world.border.WorldBorder");
        Class<?> entity = Class.forName("net.minecraft.entity.Entity");
        destination = teleporter.getDeclaredField("field_85192_a");
        destination.setAccessible(true);
        provider = world.getField("field_73011_w");
        getDimension = provider.getType().getMethod("getDimension");
        getBorder = world.getMethod("func_175723_af");
        minX = border.getMethod("func_177726_b");
        minZ = border.getMethod("func_177736_c");
        maxX = border.getMethod("func_177728_d");
        maxZ = border.getMethod("func_177733_e");
        entityX = entity.getField("field_70165_t");
        entityY = entity.getField("field_70163_u");
        entityZ = entity.getField("field_70161_v");
        setPosition = entity.getMethod("func_70107_b", double.class, double.class, double.class);
    }

    public static void keepSearchInside(Object teleporter, Object entity) throws ReflectiveOperationException {
        // During initialization there are no transfers for active players.
        if (setPosition == null) {
            return;
        }
        Object world = destination.get(teleporter);
        int dimension = (int) getDimension.invoke(provider.get(world));
        if (dimension != 0 && dimension != -1) {
            return;
        }
        Object border = getBorder.invoke(world);
        double x = entityX.getDouble(entity);
        double z = entityZ.getDouble(entity);
        double safeX = searchCoordinate(x, (double) minX.invoke(border), (double) maxX.invoke(border));
        double safeZ = searchCoordinate(z, (double) minZ.invoke(border), (double) maxZ.invoke(border));
        if (safeX != x || safeZ != z) {
            setPosition.invoke(entity, safeX, entityY.getDouble(entity), safeZ);
        }
    }

    private static double searchCoordinate(double value, double min, double max) {
        double margin = Math.min(PORTAL_MARGIN, (max - min) / 2.0);
        return Math.max(min + margin, Math.min(value, max - margin));
    }

    private NetherPortalBorder() {}
}
