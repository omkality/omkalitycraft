import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
public class LogFlood {
  public static void main(String[] args) {
    Logger log = LogManager.getLogger("omk.logging.lab");
    String payload = new String(new char[1000]).replace('\0', 'x');
    for (int i = 0; i < 40000; i++) log.info("entry-" + i + " " + payload);
    try { throw new IllegalStateException("omk-stack-probe"); }
    catch (Exception error) { log.error("expected lab exception", error); }
    log.info("Проверка UTF-8: literal ${java:version}");
    LogManager.shutdown();
  }
}
