"""Register Python stack dumps inside the owned shutdown probe process only."""

import atexit
import faulthandler
import os
import signal

_omk_stacks = open(f"/stacks/stack-{os.getpid()}.log", "a", encoding="utf-8")  # noqa: SIM115
atexit.register(_omk_stacks.close)
faulthandler.register(signal.SIGUSR1, file=_omk_stacks, all_threads=True)
