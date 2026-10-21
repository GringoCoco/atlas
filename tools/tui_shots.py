# /// script
# requires-python = ">=3.11"
# dependencies = ["textual>=1.0"]
# ///
"""Снимает SVG-скриншоты atlas_tui в разных состояниях (без терминала).

    uv run --script tools/tui_shots.py /tmp/shots
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import atlas_tui  # noqa: E402

SCENARIOS = {
    "1-start": [],
    "2-search": list("proxy"),
    "3-commands": ["slash"],
    "4-chains": ["tab"],
    "5-env": ["tab", "tab"],
    "6-grep": ["tab", "tab", "tab", *"token", "enter"],
    "7-preview": [*"zshrc", "enter"],
    "8-category": ["slash", *"ssh", "enter"],
    "9-help": ["f1"],
}


async def shoot(name: str, keys: list[str], out: str) -> None:
    app = atlas_tui.AtlasApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for k in keys:
            await pilot.press(k)
            await pilot.pause()
        await pilot.pause(0.3)
        app.save_screenshot(os.path.join(out, name + ".svg"))


async def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots"
    os.makedirs(out, exist_ok=True)
    only = sys.argv[2:] or list(SCENARIOS)
    for name in only:
        await shoot(name, SCENARIOS[name], out)
        print("ok", name)


asyncio.run(main())
