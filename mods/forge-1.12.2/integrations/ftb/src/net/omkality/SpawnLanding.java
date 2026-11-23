package net.omkality;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Arrays;
import net.minecraftforge.fml.common.FMLCommonHandler;
import org.apache.logging.log4j.Logger;

/** Resolve the saved Overworld landing before its FTB claims are changed. */
final class SpawnLanding {
    private final Object world, previous, selected;
    private final Method x, y, z, setSpawn, rules, setRule, air, block, full, registry, blockType, top;
    private final Method border, insideBorder;
    private final Constructor<?> position;

    SpawnLanding(String relocation) throws Exception {
        Class<?> worldType = Class.forName("net.minecraft.world.World");
        Class<?> positionType = Class.forName("net.minecraft.util.math.BlockPos");
        Class<?> state = Class.forName("net.minecraft.block.state.IBlockState");
        Class<?> ruleType = Class.forName("net.minecraft.world.GameRules");
        world = Class.forName("net.minecraftforge.common.DimensionManager").getMethod("getWorld", int.class)
            .invoke(null, 0);
        if (world == null || FMLCommonHandler.instance().getMinecraftServerInstance() == null)
            throw new IllegalStateException("Overworld is not ready for spawn protection");
        position = positionType.getConstructor(int.class, int.class, int.class);
        x = positionType.getMethod("func_177958_n");
        y = positionType.getMethod("func_177956_o");
        z = positionType.getMethod("func_177952_p");
        setSpawn = worldType.getMethod("func_175652_B", positionType);
        rules = worldType.getMethod("func_82736_K");
        setRule = ruleType.getMethod("func_82764_b", String.class, String.class);
        top = worldType.getMethod("func_175672_r", positionType);
        border = worldType.getMethod("func_175723_af");
        insideBorder = border.getReturnType().getMethod("func_177746_a", positionType);
        air = worldType.getMethod("func_175623_d", positionType);
        block = worldType.getMethod("func_180495_p", positionType);
        full = state.getMethod("func_185913_b");
        blockType = state.getMethod("func_177230_c");
        registry = Class.forName("net.minecraft.block.Block").getMethod("getRegistryName");
        previous = worldType.getMethod("func_175694_M").invoke(world);
        selected = choose(relocation);
    }

    private Object choose(String relocation) throws Exception {
        int[] origin = coordinates(previous);
        if (relocation != null) {
            if (!relocation.matches("-?[0-9]{1,7}(:-?[0-9]{1,7}){5}"))
                throw new IllegalArgumentException("Invalid Overworld relocation");
            int[] points = Arrays.stream(relocation.split(":")).mapToInt(Integer::parseInt).toArray();
            if (Arrays.equals(origin, Arrays.copyOfRange(points, 0, 3))) {
                Object target = position.newInstance(points[3], points[4], points[5]);
                if (!safe(target)) throw new IllegalStateException("Configured Overworld spawn is no longer dry");
                return target;
            }
        }
        if (safe(previous)) return previous;
        for (int distance : new int[] {32, 96, 192, 384}) {
            for (int dx = -1; dx <= 1; dx++) {
                for (int dz = -1; dz <= 1; dz++) {
                    if (dx == 0 && dz == 0) continue;
                    Object target = top.invoke(world, position.newInstance(
                        origin[0] + dx * distance, 64, origin[2] + dz * distance));
                    if (safe(target)) return target;
                }
            }
        }
        throw new IllegalStateException("No dry place near the Overworld spawn");
    }

    private int[] coordinates(Object pos) throws Exception {
        return new int[] {(Integer) x.invoke(pos), (Integer) y.invoke(pos), (Integer) z.invoke(pos)};
    }

    private boolean safe(Object feet) throws Exception {
        int[] pos = coordinates(feet);
        if (pos[1] < 2 || pos[1] > 253 || !Boolean.TRUE.equals(insideBorder.invoke(border.invoke(world), feet)))
            return false;
        if (!Boolean.TRUE.equals(air.invoke(world, feet))
                || !Boolean.TRUE.equals(air.invoke(world, position.newInstance(pos[0], pos[1] + 1, pos[2]))))
            return false;
        Object floor = block.invoke(world, position.newInstance(pos[0], pos[1] - 1, pos[2]));
        String id = String.valueOf(registry.invoke(blockType.invoke(floor)));
        return Boolean.TRUE.equals(full.invoke(floor))
            && !id.equals("minecraft:magma") && !id.equals("minecraft:cactus")
            && !id.contains("leaves") && !id.equals("minecraft:ice");
    }

    int x() throws Exception { return (Integer) x.invoke(selected); }
    int z() throws Exception { return (Integer) z.invoke(selected); }

    void apply(Logger log) throws Exception {
        if (!previous.equals(selected)) setSpawn.invoke(world, selected);
        setRule.invoke(rules.invoke(world), "spawnRadius", "0");
        log.info("Omkality Overworld spawn aligned with FTB claims at {}", selected);
    }
}
