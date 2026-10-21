#!/usr/bin/env python3
"""
Пример использования config_atlas как библиотеки.

    python3 examples/find_config.py proxy          # где прокси?
    python3 examples/find_config.py gh --cat       # только в категории GitHub
    python3 examples/find_config.py npmrc --show   # + показать содержимое
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import config_atlas as ca


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        return

    query = args[0]
    entries = ca.build_map()

    if "--cat" in flags:
        cat = args[1] if len(args) > 1 else ""
        entries = [e for e in entries if e.category == cat]

    hits = ca.search(entries, query)
    if not hits:
        print("Ничего не найдено по запросу: %s" % query)
        return

    print("Найдено %d записей по запросу «%s»\n" % (len(hits), query))
    for e in hits[:20]:
        mark = "★" if e.source == "curated" else "○"
        state = "" if e.exists else "  [НЕ СУЩЕСТВУЕТ]"
        print("%s %-52s %s%s" % (mark, e.path.replace(
            os.path.expanduser("~"), "~"), e.note, state))

    if "--show" in flags:
        print("\n" + "=" * 60)
        for e in hits[:3]:
            print("\n### %s" % e.path)
            lines, is_bin = ca.read_preview(e.path)
            if is_bin:
                print("[двоичный файл]")
                continue
            for ln in ca.mask_secrets(lines)[:40]:
                print("  " + ln)


if __name__ == "__main__":
    main()
