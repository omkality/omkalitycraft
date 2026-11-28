/** Compile-only ABI for the bundled LWJGL 2 keyboard. */
package org.lwjgl.input;

public final class Keyboard {
    public static final int KEY_Z = 44;
    public static int getEventKey() { throw new UnsupportedOperationException("ABI only"); }
    public static boolean getEventKeyState() { throw new UnsupportedOperationException("ABI only"); }
    public static boolean isRepeatEvent() { throw new UnsupportedOperationException("ABI only"); }
    public static boolean isKeyDown(int key) { throw new UnsupportedOperationException("ABI only"); }
}
