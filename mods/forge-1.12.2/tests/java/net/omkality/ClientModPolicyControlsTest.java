package net.omkality;

import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

public final class ClientModPolicyControlsTest {
    public static void main(String[] args) {
        Properties configured = new Properties();
        configured.setProperty("forge", "14.23.5.2860");
        configured.setProperty("legacy", "");
        Map<String, String> client = new HashMap<>();
        client.put("forge", "14.23.5.2860");
        client.put("legacy", "");
        ClientModPolicy exact = new ClientModPolicy(configured);
        require(exact.accepts(client), "The original client must still pass");
        configured.setProperty("?example", "1.2.3");
        ClientModPolicy withOptional = new ClientModPolicy(configured);
        require(withOptional.accepts(client), "An optional mod must not block existing clients");
        client.put("example", "1.2.3");
        require(!exact.accepts(client), "Unconfigured mods must still be rejected");
        require(withOptional.accepts(client), "The configured optional version must pass");
        client.put("example", "1.2.4");
        require(!withOptional.accepts(client), "A different optional version must be rejected");
        client.put("example", "1.2.3");
        client.put("unlisted", "");
        require(!withOptional.accepts(client), "Additional undeclared mods must be rejected");
        client.remove("unlisted");
        client.remove("legacy");
        require(!withOptional.accepts(client), "Optional mods must not replace required mods");
        System.out.println("Client mod policy controls verified");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
