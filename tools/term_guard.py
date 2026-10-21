#!/usr/bin/env python3
"""
Проверка того, что терминал остаётся в рабочем состоянии после выхода.

Эмулирует терминал, считает включённые/выключенные режимы (DECSET/DECRST)
и проверяет, что после SIGTERM/SIGHUP/SIGINT ничего не «залипло».

    python3 tools/term_guard.py
"""

import os
import re
import select
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_term import FakeTerminal  # noqa: E402

PY = os.path.expanduser(
    "~/.cache/uv/environments-v2/atlas-tui-9e97be41f211eb97/bin/python3")
APP = os.path.expanduser("~/Projects/config-atlas/atlas_tui.py")

# режимы, которые Textual включает и которые обязаны быть выключены
TRACKED = ("1049", "25", "7", "1000", "1003", "1004", "1006", "1015", "2004")


def modes(raw: bytes) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for mid, act in re.findall(rb"\x1b\[\?(\d+)([hl])", raw):
        m = out.setdefault(mid.decode(), {"h": 0, "l": 0})
        m["h" if act == b"h" else "l"] += 1
    return out


def run(label: str, killer) -> bool:
    # запускаем БЕЗ exec: обёртка должна остаться жить, чтобы поймать
    # смерть приложения и восстановить терминал
    with FakeTerminal(["/bin/sh", os.path.expanduser(
            "~/.local/bin/config-atlas")]) as t:
        t.pump(4.5)
        ps = os.popen("ps -Ao pid,command | grep atlas_tui.py | grep -v grep "
                      "| grep python3").read().strip()
        if not ps:
            print("  FAIL  %s — процесс не найден" % label)
            return False
        pid = int(ps.split()[0])
        os.kill(pid, killer)
        end = time.time() + 2.0
        while time.time() < end:
            r, _, _ = select.select([t.fd], [], [], 0.1)
            if r:
                try:
                    chunk = os.read(t.fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                t.raw += chunk
        m = modes(t.raw)
        # Проверяем, что в конце потока терминал в обычном режиме:
        # для каждого режима смотрим последнее вхождение.
        # (?25h и ?7h — это как раз «показать курсор» и «включить перенос
        # строк», их финальное состояние должно быть «включено».)
        WANT_FINAL = {"1049": "l", "25": "h", "7": "h", "1000": "l",
                      "1003": "l", "1004": "l", "1006": "l", "1015": "l",
                      "2004": "l"}
        stuck = []
        for mid, want in WANT_FINAL.items():
            last = None
            for mm, act in re.findall(rb"\x1b\[\?(\d+)([hl])", t.raw):
                if mm.decode() == mid:
                    last = act
            if last is None:
                continue
            if last.decode() != want:
                stuck.append("%s(=%s, ждали %s)" % (mid, last.decode(), want))
        if stuck:
            print("  FAIL  %s — неверное финальное состояние: %s"
                  % (label, ", ".join(stuck)))
            return False
        print("  ok    %s — терминал восстановлен" % label)
        return True


def main() -> None:
    print("=== терминал после выхода ===")
    ok = True
    ok &= run("SIGTERM", signal.SIGTERM)
    ok &= run("SIGHUP", signal.SIGHUP)
    ok &= run("SIGINT", signal.SIGINT)
    ok &= run("SIGQUIT", signal.SIGQUIT)
    ok &= run("SIGKILL", signal.SIGKILL)
    print()
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" if ok else "ЕСТЬ ПРОВАЛЫ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
