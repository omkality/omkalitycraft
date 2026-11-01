package omk.lab.trace;

import java.lang.instrument.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import net.minecraft.launchwrapper.IClassTransformer;
import org.objectweb.asm.*;

/** Temporary diagnostics. Never bundled with the launcher or a modpack release. */
public final class StartupTraceAgent {
    private static Path directory;
    private static final AtomicInteger sequence = new AtomicInteger();
    private static final Set<String> hashes = new HashSet<String>();
    private static final ThreadLocal<Integer> depth = new ThreadLocal<Integer>() {
        protected Integer initialValue() { return 0; }
    };
    private static long written;
    private static final ThreadLocal<String> activeDeobf = new ThreadLocal<String>();
    private static final Set<String> lazyDefinitions = new HashSet<String>();
    private static final boolean exclusionsOnly = "exclusions".equals(System.getProperty("omkality.lab.traceMode", "full"));
    private static final ThreadLocal<String> metadataTarget = new ThreadLocal<String>();

    public static void premain(String args, Instrumentation instrumentation) throws Exception {
        directory = Paths.get(args).toRealPath();
        if (!Files.isRegularFile(directory.resolve("lab-trace-owner"))) {
            throw new IllegalArgumentException("Expected an isolated lab trace directory");
        }
        write("agent-ready");
        write("trace-mode=" + (exclusionsOnly ? "exclusions" : "full"));
        instrumentation.addTransformer(new ClassFileTransformer() {
            public byte[] transform(ClassLoader loader, String name, Class<?> redef,
                    ProtectionDomain domain, byte[] bytes) {
                final boolean launchLoader = "net/minecraft/launchwrapper/LaunchClassLoader".equals(name);
                final boolean mixinLegacy = "org/spongepowered/asm/service/mojang/LegacyTransformerHandle".equals(name);
                final boolean mixinService = "org/spongepowered/asm/service/mojang/MixinServiceLaunchWrapper".equals(name);
                final boolean reentryLock = "org/spongepowered/asm/util/ReEntranceLock".equals(name);
                if (exclusionsOnly && !mixinService) return null;
                if (name != null && name.startsWith("mirror/normalasm/") && activeDeobf.get() != null) {
                    lazyDefinition(name);
                }
                if (!launchLoader && !mixinLegacy && !mixinService && !reentryLock) return null;
                try {
                    final AtomicInteger patched = new AtomicInteger();
                    ClassReader reader = new ClassReader(bytes);
                    ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
                    reader.accept(new ClassVisitor(Opcodes.ASM5, writer) {
                        public MethodVisitor visitMethod(int access, String method, String desc,
                                String signature, String[] exceptions) {
                            MethodVisitor delegate = super.visitMethod(access, method, desc, signature, exceptions);
                            if (mixinService && exclusionsOnly && "applyTransformers".equals(method)) {
                                patched.incrementAndGet();
                                return new MethodVisitor(Opcodes.ASM5, delegate) {
                                    public void visitCode() {
                                        super.visitCode();
                                        super.visitVarInsn(Opcodes.ALOAD, 1);
                                        super.visitVarInsn(Opcodes.ALOAD, 2);
                                        super.visitMethodInsn(Opcodes.INVOKESTATIC, "omk/lab/trace/StartupTraceAgent", "metadata", "(Ljava/lang/String;Ljava/lang/String;)V", false);
                                    }
                                };
                            }
                            if (reentryLock && "check".equals(method) && "()Z".equals(desc)) {
                                patched.incrementAndGet();
                                return new MethodVisitor(Opcodes.ASM5, delegate) {
                                    public void visitInsn(int opcode) {
                                        if (opcode == Opcodes.IRETURN) {
                                            super.visitInsn(Opcodes.DUP);
                                            super.visitMethodInsn(Opcodes.INVOKESTATIC, "omk/lab/trace/StartupTraceAgent", "reentry", "(Z)V", false);
                                        }
                                        super.visitInsn(opcode);
                                    }
                                };
                            }
                            if (reentryLock) return delegate;
                            if (mixinService && "addTransformerExclusion".equals(method) && "(Ljava/lang/String;)V".equals(desc)) {
                                patched.incrementAndGet();
                                return new MethodVisitor(Opcodes.ASM5, delegate) {
                                    public void visitCode() {
                                        super.visitCode();
                                        super.visitVarInsn(Opcodes.ALOAD, 1);
                                        super.visitMethodInsn(Opcodes.INVOKESTATIC, "omk/lab/trace/StartupTraceAgent", "exclusion", "(Ljava/lang/String;)V", false);
                                    }
                                };
                            }
                            if (mixinService) return delegate;
                            if (!(launchLoader ? "runTransformers" : "transformClassBytes").equals(method)) return delegate;
                            return new MethodVisitor(Opcodes.ASM5, delegate) {
                                public void visitMethodInsn(int opcode, String owner, String called,
                                        String desc, boolean itf) {
                                    if (opcode == Opcodes.INVOKEINTERFACE
                                            && "net/minecraft/launchwrapper/IClassTransformer".equals(owner)
                                            && "transform".equals(called)
                                            && "(Ljava/lang/String;Ljava/lang/String;[B)[B".equals(desc)) {
                                        patched.incrementAndGet();
                                        super.visitMethodInsn(Opcodes.INVOKESTATIC,
                                            "omk/lab/trace/StartupTraceAgent", "apply",
                                            "(Lnet/minecraft/launchwrapper/IClassTransformer;Ljava/lang/String;Ljava/lang/String;[B)[B", false);
                                    } else super.visitMethodInsn(opcode, owner, called, desc, itf);
                                }
                            };
                        }
                    }, 0);
                    if (patched.get() != (launchLoader || (mixinService && exclusionsOnly) ? 2 : 1)) throw new IllegalStateException("Unexpected transformer call count");
                    byte[] output = writer.toByteArray();
                    Files.write(directory.resolve((launchLoader ? "LaunchClassLoader" : mixinLegacy ? "LegacyTransformerHandle" : mixinService ? "MixinServiceLaunchWrapper" : "ReEntranceLock") + "-instrumented.class"), output, StandardOpenOption.CREATE_NEW);
                    write(launchLoader ? "launchclassloader-hook-armed" : mixinLegacy ? "mixin-legacy-hook-armed" : mixinService ? "mixin-service-hook-armed" : "reentry-lock-hook-armed");
                    return output;
                } catch (Throwable failure) {
                    write("instrumentation-failed " + failure.getClass().getName());
                    return null;
                }
            }
        });
    }

    public static byte[] apply(IClassTransformer transformer, String name, String transformedName, byte[] bytes) {
        final String stage = transformer.getClass().getName();
        final boolean deobf = "net.minecraftforge.fml.common.asm.transformers.DeobfuscationTransformer".equals(stage);
        final String previous = activeDeobf.get();
        if (deobf) activeDeobf.set(transformedName);
        if (!"net.minecraft.item.ItemBlock".equals(transformedName) && !"net/minecraft/item/ItemBlock".equals(transformedName)) {
            try {
            return transformer.transform(name, transformedName, bytes);
            } finally {
                if (deobf) activeDeobf.set(previous);
            }
        }
        final int id = sequence.incrementAndGet();
        final int nesting = depth.get();
        depth.set(nesting + 1);
        write(id + " CALL name=" + name + " transformed=" + transformedName + " caller=" + new Throwable().getStackTrace()[1].getClassName());
        capture(id, "IN", stage, bytes, nesting);
        try {
            byte[] output = transformer.transform(name, transformedName, bytes);
            capture(id, "OUT", stage, output, nesting);
            return output;
        } catch (Throwable failure) {
            write(id + " ERROR " + stage + " " + failure.getClass().getName() + " " + failure.getMessage());
            for (StackTraceElement frame : failure.getStackTrace()) {
                write("  " + frame.toString());
            }
            throw failure;
        } finally {
            depth.set(nesting);
            if (deobf) activeDeobf.set(previous);
        }
    }

    public static void exclusion(String name) {
        if ("net.minecraftforge.fml.common.asm.transformers.DeobfuscationTransformer".equals(name)) {
            write("DEOBF-EXCLUDED metadata=" + metadataTarget.get());
            int count = 0;
            for (StackTraceElement frame : new Throwable().getStackTrace()) {
                if (count++ < 48) write("  " + frame.toString());
            }
        }
    }

    public static void metadata(String name, String transformedName) {
        metadataTarget.set(name + " -> " + transformedName);
    }

    private static int reentries;
    public static synchronized void reentry(boolean entered) {
        if (!entered || activeDeobf.get() == null || reentries++ >= 32) return;
        write("DEOBF-REENTRY outer=" + activeDeobf.get());
        int count = 0;
        for (StackTraceElement frame : new Throwable().getStackTrace()) {
            if (count++ < 64) write("  " + frame.toString());
        }
    }

    private static synchronized void lazyDefinition(String name) {
        if (lazyDefinitions.size() >= 32 || !lazyDefinitions.add(name)) return;
        write("DEOBF-LAZY-DEFINE " + name + " outer=" + activeDeobf.get());
        int count = 0;
        for (StackTraceElement frame : new Throwable().getStackTrace()) {
            if (count++ < 48) write("  " + frame.toString());
        }
    }

    private static synchronized void capture(int id, String phase, String stage, byte[] bytes, int nesting) {
        if (id > 500 || bytes == null || bytes.length > 512 * 1024) return;
        try {
            final List<String> fields = new ArrayList<String>();
            ClassReader reader = new ClassReader(bytes);
            reader.accept(new ClassVisitor(Opcodes.ASM5) {
                public FieldVisitor visitField(int access, String name, String desc, String signature, Object value) {
                    if (fields.size() < 100) fields.add(name + ":" + desc);
                    return null;
                }
            }, ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
            String hash = hex(MessageDigest.getInstance("SHA-256").digest(bytes));
            write(id + " " + phase + " depth=" + nesting + " " + stage + " class=" + reader.getClassName()
                + " sha=" + hash + " fields=" + fields.toString());
            if (hashes.add(hash) && written + bytes.length < 16 * 1024 * 1024) {
                Files.write(directory.resolve(hash + ".class"), bytes, StandardOpenOption.CREATE_NEW);
                written += bytes.length;
            }
        } catch (Throwable failure) {
            write("capture-failed " + failure.getClass().getName());
        }
    }

    private static String hex(byte[] data) {
        StringBuilder text = new StringBuilder();
        for (byte value : data) text.append(String.format("%02x", value & 255));
        return text.toString();
    }

    private static synchronized void write(String line) {
        try {
            Path log = directory.resolve("trace.txt");
            if (!Files.exists(log) || Files.size(log) < 1024 * 1024) {
                Files.write(log, (line + "\n").getBytes("UTF-8"), StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            }
        } catch (Throwable ignored) {
            System.err.println("[omk-startup-trace] trace write failed");
        }
    }
}
