import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

from asciio import storage
from asciio.tui import terminal_key


def test_terminal_control_keys_reach_editor_actions():
    assert terminal_key("\x13") == "Ctrl+s"
    assert terminal_key("\x11") == "Ctrl+q"
    assert terminal_key("\n") == "Return"


def test_real_terminal_can_insert_save_and_quit(tmp_path):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 110, 0, 0))
    environment = {**os.environ, "TERM": "xterm-256color"}
    process = subprocess.Popen(
        [sys.executable, "-m", "asciio", "tui"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=environment,
    )
    os.close(slave)
    transcript = bytearray()

    def wait_for(predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if predicate():
                return
            ready, _, _ = select.select([master], [], [], 0.05)
            if ready:
                try:
                    transcript.extend(os.read(master, 65536))
                except OSError:
                    break
            if process.poll() is not None:
                break
        assert predicate(), transcript.decode(errors="replace")

    try:
        wait_for(lambda: b"Asciio Python" in transcript)
        path = tmp_path / "terminal.pasciio"
        os.write(master, f"b:save {path}\n".encode())
        wait_for(path.exists)
        os.write(master, b"\x11")
        wait_for(lambda: process.poll() is not None)
        assert process.wait(timeout=5) == 0, transcript.decode(errors="replace")
        diagram = storage.load(path)
        assert len(diagram.elements) == 1
        assert diagram.elements[0].kind == "box"
        assert b"Traceback" not in transcript
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        os.close(master)
