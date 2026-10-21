#!/usr/bin/env python3
"""
Эмулятор терминала для проверки TUI.

В отличие от обычного pty, отвечает на запросы терминала:
  ESC[6n  → позиция курсора
  ESC[c   → тип терминала
  ESC[>c  → версия
  DA1/DA2 → идентификация

Это позволяет поймать баг, когда ответ терминала попадает в буфер ввода
после выхода приложения (в шелле остаётся мусор).
"""

import os
import pty
import re
import select
import struct
import sys
import termios
import time
import fcntl


class FakeTerminal:
    def __init__(self, command, cols=120, rows=40, respond=True):
        self.command = command
        self.cols = cols
        self.rows = rows
        self.respond = respond
        self.pending = b""
        self.raw = b""
        self.answered = 0

    def __enter__(self):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.environ["TERM"] = "xterm-256color"
            os.environ["COLUMNS"] = str(self.cols)
            os.environ["LINES"] = str(self.rows)
            os.execv(self.command[0], self.command)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ,
                    struct.pack("HHHH", self.rows, self.cols, 0, 0))
        return self

    def __exit__(self, *exc):
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass

    def pump(self, seconds=1.0, keys=b""):
        """Читает вывод, отвечает на запросы, доит ввод."""
        if keys:
            os.write(self.fd, keys)
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if not r:
                continue
            try:
                chunk = os.read(self.fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            self.raw += chunk
            self.pending += chunk
            self._answer()
        return self.raw

    def _answer(self) -> None:
        if not self.respond:
            return
        out = b""
        # позиция курсора
        while b"\x1b[6n" in self.pending:
            self.pending = self.pending.replace(b"\x1b[6n", b"", 1)
            out += b"\x1b[1;1R"
            self.answered += 1
        # тип терминала
        while b"\x1b[c" in self.pending:
            self.pending = self.pending.replace(b"\x1b[c", b"", 1)
            out += b"\x1b[?62;c"
            self.answered += 1
        while b"\x1b[>c" in self.pending:
            self.pending = self.pending.replace(b"\x1b[>c", b"", 1)
            out += b"\x1b[>0;276;0c"
            self.answered += 1
        if out:
            os.write(self.fd, out)

    def leftover(self) -> bytes:
        """Что осталось во входном буфере после выхода приложения."""
        time.sleep(0.3)
        data = b""
        while True:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if not r:
                break
            try:
                chunk = os.read(self.fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            data += chunk
        return data

    def send(self, data: bytes) -> None:
        os.write(self.fd, data)

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


def main() -> None:
    app = os.path.expanduser("~/.local/bin/config-atlas")
    print("=== терминал отвечает на запросы ===")
    with FakeTerminal(["/bin/sh", app]) as t:
        t.pump(4.0)
        print("ответов на запросы:", t.answered)
        # выходим через Ctrl+C
        t.send(b"\x03")
        t.pump(2.0)
        rest = t.leftover()
        print("осталось во входном буфере: %r" % rest[:200])
        if rest:
            print("!! мусор попал в буфер ввода — баг подтверждён")
        else:
            print("буфер ввода чист")

    print()
    print("=== терминал НЕ отвечает ===")
    with FakeTerminal(["/bin/sh", app], respond=False) as t:
        t.pump(4.0)
        t.send(b"\x03")
        t.pump(2.0)
        rest = t.leftover()
        print("осталось во входном буфере: %r" % rest[:200])


if __name__ == "__main__":
    main()
