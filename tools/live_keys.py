#!/usr/bin/env python3
"""
Проверка клавиш в ЖИВОМ терминале: настоящие escape-последовательности.

run_test() из Textual подменяет ввод, поэтому часть проблем не ловит.
Здесь запускаем приложение в pty и шлём настоящие байты:
    стрелка вниз  →  ESC [ B
    tab           →  \\t
    ctrl+q        →  выход

Приложение пишет текущий экран в ATLAS_DUMP при выходе.

    python3 tools/live_keys.py
"""

import os
import pty
import select
import struct
import sys
import termios
import fcntl
import time

DUMP = "/tmp/atlas_live_screen.txt"
LOG = "/tmp/atlas_live_log.txt"

KEYS = {
    "down": b"\x1b[B",
    "up": b"\x1b[A",
    "tab": b"\t",
    "shift+tab": b"\x1b[Z",
    "ctrl+q": b"\x11",
}


def make_spy_script() -> str:
    """Создаём скрипт-обёртку, логирующий действия."""
    return f"""\
import sys, os
sys.path.insert(0, os.path.expanduser("~/Projects/config-atlas"))
import atlas_tui
os.environ["ATLAS_DUMP"] = {DUMP!r}

_log = open({LOG!r}, "w", buffering=1)

orig_move = atlas_tui.AtlasApp.action_move
def spy_move(self, d):
    ol = self.query_one("#results")
    _log.write(f"move({{d}}) highlighted={{ol.highlighted}}\\n")
    return orig_move(self, d)
atlas_tui.AtlasApp.action_move = spy_move

orig_tab = atlas_tui.AtlasApp.action_cycle_mode
def spy_tab(self, d):
    _log.write(f"cycle_mode({{d}}) mode={{self.mode}}\\n")
    return orig_tab(self, d)
atlas_tui.AtlasApp.action_cycle_mode = spy_tab

atlas_tui.main()
"""


def run(keys: list[str]) -> str:
    spy = "/tmp/_live_spy.py"
    with open(spy, "w") as fh:
        fh.write(make_spy_script())

    for f in (DUMP, LOG):
        if os.path.exists(f):
            os.unlink(f)

    PY = os.path.expanduser(
        "~/.cache/uv/environments-v2/atlas-tui-9e97be41f211eb97/bin/python3"
    )
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.execv(PY, [PY, spy])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    out = b""

    def pump(seconds: float) -> None:
        nonlocal out
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    return
                if not chunk:
                    return
                out += chunk

    pump(4.5)
    for k in keys:
        try:
            os.write(fd, KEYS[k])
        except OSError:
            break
        pump(0.6)
    try:
        os.write(fd, KEYS["ctrl+q"])
    except OSError:
        pass
    pump(2.0)
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    return open(LOG).read() if os.path.exists(LOG) else ""


def main() -> None:
    fails = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "  ok  " if cond else "  FAIL"
        print(status + "  " + name + (("  — " + extra) if extra and not cond else ""))
        if not cond:
            fails.append(name)

    print("=== стрелка вниз (ESC [ B) ===")
    log = run(["down", "down", "down"])
    moves = [l for l in log.splitlines() if l.startswith("move(")]
    check("action_move вызван 3 раза", len(moves) == 3, f"вызовов: {len(moves)}")
    if moves:
        # Проверяем что highlighted растёт
        highlights = []
        for m in moves:
            try:
                h = int(m.split("highlighted=")[1])
                highlights.append(h)
            except (IndexError, ValueError):
                pass
        check("highlighted увеличивается", highlights == sorted(highlights) and len(set(highlights)) > 1,
              str(highlights))
        for m in moves:
            print("     ", m)

    print()
    print("=== tab ===")
    log = run(["tab"])
    tabs = [l for l in log.splitlines() if l.startswith("cycle_mode")]
    check("cycle_mode вызван", len(tabs) >= 1, f"вызовов: {len(tabs)}")
    if tabs:
        check("режим сменился с all", "mode=all" in tabs[0], tabs[0])
        for t in tabs:
            print("     ", t)

    print()
    print("=== shift+tab ===")
    log = run(["tab", "shift+tab"])
    tabs = [l for l in log.splitlines() if l.startswith("cycle_mode")]
    check("shift+tab вызван", len(tabs) >= 2, str(tabs))
    if len(tabs) >= 2:
        print("     ", tabs[0])
        print("     ", tabs[1])

    print()
    print("=== много стрелок и tab ===")
    log = run(["down", "down", "down", "down", "down", "tab", "up", "up"])
    all_actions = log.splitlines()
    check("комбо: >4 действий", len(all_actions) >= 7, f"действий: {len(all_actions)}")
    for a in all_actions:
        print("     ", a)

    print()
    print("=" * 46)
    if fails:
        print("ПРОВАЛЕНО %d: %s" % (len(fails), ", ".join(fails)))
        sys.exit(1)
    print("ВСЕ КЛАВИШИ РАБОТАЮТ")


if __name__ == "__main__":
    main()
