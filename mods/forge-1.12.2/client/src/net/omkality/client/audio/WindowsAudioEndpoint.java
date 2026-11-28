package net.omkality.client.audio;

import com.sun.jna.Function;
import com.sun.jna.Memory;
import com.sun.jna.Native;
import com.sun.jna.NativeLibrary;
import com.sun.jna.Pointer;
import com.sun.jna.ptr.PointerByReference;
import java.util.UUID;
import org.apache.logging.log4j.LogManager;

/** Read the default Windows playback device in one daemon-owned COM apartment. */
final class WindowsAudioEndpoint implements Runnable {
    private static final int COINIT_MULTITHREADED = 0;
    private static final int CLSCTX_INPROC_SERVER = 1;
    private static final int E_RENDER = 0;
    private static final int E_CONSOLE = 0;
    private static final int E_NOTFOUND = 0x80070490;
    private static final int RELEASE = 2;
    private static final int GET_DEFAULT_ENDPOINT = 4;
    private static final int GET_DEVICE_ID = 5;
    private volatile String current;

    String current() { return current; }

    @Override public void run() {
        try {
            NativeLibrary ole = NativeLibrary.getInstance("Ole32");
            checked(function(ole, "CoInitializeEx").invokeInt(
                new Object[] {null, COINIT_MULTITHREADED}), "CoInitializeEx");
            try {
                poll(ole);
            } finally {
                function(ole, "CoUninitialize").invokeVoid(new Object[0]);
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (RuntimeException | LinkageError error) {
            LogManager.getLogger("OmkalityClient").warn("Windows playback device monitoring stopped", error);
        }
    }

    private void poll(NativeLibrary ole) throws InterruptedException {
        PointerByReference value = new PointerByReference();
        checked(function(ole, "CoCreateInstance").invokeInt(new Object[] {
            guid("bcde0395-e52f-467c-8e3d-c4579291692e"), null, CLSCTX_INPROC_SERVER,
            guid("a95664d2-9614-4f35-a746-de8db63617e6"), value
        }), "CoCreateInstance");
        Pointer enumerator = value.getValue();
        try {
            String previous = null;
            while (!Thread.currentThread().isInterrupted()) {
                String actual = read(ole, enumerator);
                // Switch only after two matching observations. Windows can briefly
                // report no default device while a USB or Bluetooth route settles.
                if (current == null || actual.equals(previous)) {
                    current = actual;
                }
                previous = actual;
                Thread.sleep(1000L);
            }
        } finally {
            invoke(enumerator, RELEASE).invokeInt(new Object[] {enumerator});
        }
    }

    private static String read(NativeLibrary ole, Pointer enumerator) {
        PointerByReference value = new PointerByReference();
        int result = invoke(enumerator, GET_DEFAULT_ENDPOINT).invokeInt(
            new Object[] {enumerator, E_RENDER, E_CONSOLE, value});
        if (result == E_NOTFOUND) {
            return "";
        }
        checked(result, "GetDefaultAudioEndpoint");
        Pointer device = value.getValue();
        try {
            PointerByReference name = new PointerByReference();
            checked(invoke(device, GET_DEVICE_ID).invokeInt(new Object[] {device, name}), "GetId");
            Pointer buffer = name.getValue();
            try {
                return buffer.getWideString(0);
            } finally {
                function(ole, "CoTaskMemFree").invokeVoid(new Object[] {buffer});
            }
        } finally {
            invoke(device, RELEASE).invokeInt(new Object[] {device});
        }
    }

    private static Function function(NativeLibrary library, String name) {
        return library.getFunction(name, Function.ALT_CONVENTION);
    }

    private static Function invoke(Pointer object, int method) {
        Pointer table = object.getPointer(0);
        return Function.getFunction(table.getPointer((long) method * Native.POINTER_SIZE), Function.ALT_CONVENTION);
    }

    private static Memory guid(String value) {
        UUID uuid = UUID.fromString(value);
        long head = uuid.getMostSignificantBits();
        long tail = uuid.getLeastSignificantBits();
        Memory guid = new Memory(16);
        guid.setInt(0, (int) (head >>> 32));
        guid.setShort(4, (short) (head >>> 16));
        guid.setShort(6, (short) head);
        for (int i = 0; i < 8; i++) {
            guid.setByte(8 + i, (byte) (tail >>> (56 - 8 * i)));
        }
        return guid;
    }

    private static void checked(int result, String operation) {
        if (result < 0) {
            throw new IllegalStateException(operation + " returned HRESULT 0x" + Integer.toHexString(result));
        }
    }
}
