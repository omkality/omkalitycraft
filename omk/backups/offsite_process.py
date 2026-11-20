"""Bound a REST-only worker's lifetime and both pipes without logging secrets."""

import contextlib
import os
import signal
import subprocess
import threading


class OffsiteError(RuntimeError):
    """A fixed operator-facing error without child output or credentials."""


def terminate(process):
    with contextlib.suppress(ProcessLookupError):
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()


def bounded(command, *, environment, directory, timeout, maximum, inherited=()):
    """Return stdout only after exit 0; never echo child output in exceptions."""
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            cwd=directory,
            start_new_session=os.name == "posix",
            **({"pass_fds": inherited} if inherited else {}),
        )
    except OSError:
        raise OffsiteError("Offsite worker could not start") from None
    overflow = threading.Event()
    output = bytearray()

    def drain(stream, keep):
        count = 0
        try:
            while block := stream.read(8192):
                count += len(block)
                if count > maximum:
                    overflow.set()
                    terminate(process)
                    break
                if keep:
                    output.extend(block)
        finally:
            stream.close()

    threads = [
        threading.Thread(target=drain, args=(process.stdout, True), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, False), daemon=True),
    ]
    for thread in threads:
        thread.start()
    expired = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        expired = True
        terminate(process)
        process.wait(timeout=10)
    finally:
        for thread in threads:
            thread.join(timeout=2)
        if any(thread.is_alive() for thread in threads):
            terminate(process)
            for thread in threads:
                thread.join(timeout=2)
            overflow.set()
    if overflow.is_set() or expired:
        raise OffsiteError("Offsite worker exceeded its output or time bound")
    if process.returncode != 0:
        # In particular, restic exit 3 means a partial snapshot, never success.
        raise OffsiteError(
            "Offsite worker failed (exit "
            + str(process.returncode)
            + "); inspect the same transfer"
        )
    return bytes(output)
