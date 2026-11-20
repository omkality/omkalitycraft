"""Request stack dumps from Python in the owned container namespace."""

import os
import signal

for item in os.listdir("/proc"):
    if not item.isdigit() or int(item) == os.getpid():
        continue
    try:
        if "python" in os.readlink("/proc/" + item + "/exe"):
            os.kill(int(item), signal.SIGUSR1)
    except OSError:
        pass
