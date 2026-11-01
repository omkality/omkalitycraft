package omk.lab.fixture;

import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/** Test-only agent. Never included in player bundles, manifests or OmkalityCore. */
public final class ClientCrashAgent {
    private static final String CANARY = "omk_lab_canary_not_a_credential";

    public static void premain(String argument, final Instrumentation instrumentation) {
        final Path marker = Paths.get(argument).toAbsolutePath().normalize();
        if (!marker.getFileName().toString().equals("request-client-crash")
                || !marker.getParent().getFileName().toString().startsWith("client-crash-lab-")) {
            throw new IllegalArgumentException("Expected an isolated client crash lab marker");
        }
        Thread thread = new Thread(new Runnable() {
            public void run() {
                try {
                    for (int attempt = 0; attempt < 4800; attempt++) {
                        if (Files.isRegularFile(marker)) {
                            Object client = requestCrash(instrumentation);
                            Path exit = marker.resolveSibling("request-client-exit");
                            for (int wait = 0; wait < 4800; wait++) {
                                if (Files.isRegularFile(exit)) {
                                    method(client.getClass(), "func_71400_g", "shutdown").invoke(client);
                                    return;
                                }
                                Thread.sleep(250);
                            }
                            return;
                        }
                        Thread.sleep(250);
                    }
                    System.err.println("[OMK_LAB] Controlled crash marker timed out");
                } catch (Throwable error) {
                    System.err.println("[OMK_LAB] Crash fixture failed: " + error.getClass().getName());
                }
            }
        }, "omk-lab-controlled-client-crash");
        thread.setDaemon(true);
        thread.start();
    }

    private static Class<?> loaded(Instrumentation instrumentation, String name) {
        for (Class<?> type : instrumentation.getAllLoadedClasses()) {
            if (type.getName().equals(name)) return type;
        }
        throw new IllegalStateException("Expected Minecraft class was not loaded");
    }

    private static Method method(Class<?> type, String srg, String mcp, Class<?>... arguments)
            throws Exception {
        try { return type.getMethod(srg, arguments); }
        catch (NoSuchMethodException absent) { return type.getMethod(mcp, arguments); }
    }

    private static Object requestCrash(Instrumentation instrumentation) throws Exception {
        Class<?> minecraft = loaded(instrumentation, "net.minecraft.client.Minecraft");
        Class<?> reportType = Class.forName("net.minecraft.crash.CrashReport", true, minecraft.getClassLoader());
        final Object client = method(minecraft, "func_71410_x", "getMinecraft").invoke(null);
        Throwable reason = new ControlledClientCrash("Omkality controlled client crash; access_token=" + CANARY);
        final Object report = method(reportType, "func_85055_a", "makeCrashReport", Throwable.class, String.class)
                .invoke(null, reason, "Omkality controlled client crash validation");
        final Method crashed = method(minecraft, "func_71404_a", "crashed", reportType);
        method(minecraft, "func_152344_a", "addScheduledTask", Runnable.class).invoke(client, new Runnable() {
            public void run() {
                try {
                    crashed.invoke(client, report);
                    System.err.println("[OMK_LAB] Requested a controlled Minecraft crash");
                } catch (Exception error) {
                    throw new IllegalStateException("Controlled crash request failed", error);
                }
            }
        });
        return client;
    }

    public static final class ControlledClientCrash extends RuntimeException {
        public ControlledClientCrash(String message) { super(message); }
    }
}
