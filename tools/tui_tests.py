# /// script
# requires-python = ">=3.11"
# dependencies = ["textual>=1.0"]
# ///
"""Функциональные проверки atlas_tui (без терминала)."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import atlas_tui  # noqa: E402
from textual.events import MouseScrollDown  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(("  ok  " if cond else "  FAIL") + "  " + name +
          (("  — " + extra) if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def plain(widget) -> str:
    """Текст содержимого Static (может быть str или rich.Text)."""
    c = widget.content
    return c.plain if hasattr(c, "plain") else str(c)


async def scenario(name, keys, fn):
    app = atlas_tui.AtlasApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for k in keys:
            await pilot.press(k)
            await pilot.pause()
        await pilot.pause(0.15)
        print("\n=== %s ===" % name)
        try:
            await fn(app, pilot)
        except Exception as exc:  # noqa: BLE001
            check("%s: без исключений" % name, False, repr(exc))


async def main() -> None:
    async def t_start(app, pilot):
        check("заголовок отрисован",
              "A T L A S" in plain(app.query_one("#header")))
        check("список не пуст", len(app.rows) > 0)
        check("выделена первая строка",
              app.query_one("#results").highlighted is not None)

    async def t_search(app, pilot):
        app.query_one("#prompt").value = "ssh"
        await pilot.pause()
        check("поиск сузил список", len(app.rows) < 200, str(len(app.rows)))
        check("есть совпадения ssh",
              any("ssh" in r.prompt.plain.lower() for r in app.rows))

    async def t_slash(app, pilot):
        await pilot.press("slash")
        await pilot.pause()
        check("палитра команд открыта",
              any(r.command for r in app.rows))
        check("в первой строке /all", app.rows[0].command == "all")

    async def t_command(app, pilot):
        await pilot.press("slash")
        await pilot.pause()
        # набираем "node" — категория node, нет конфликта с диаг-командами
        for k in "node":
            await pilot.press(k)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        check("категория выставлена", app.category == "node", str(app.category))
        check("чип категории виден",
              "node" in plain(app.query_one("#chips")).lower())

    async def t_tab(app, pilot):
        await pilot.press("tab")
        await pilot.pause()
        check("режим сменился на цепочки", app.mode == "chain", app.mode)
        check("в цепочках есть заголовки групп",
              any(r.entry is None for r in app.rows))

    async def t_arrows(app, pilot):
        before = app.query_one("#results").highlighted
        for _ in range(3):
            await pilot.press("down")
        await pilot.pause()
        after = app.query_one("#results").highlighted
        check("стрелки двигают выделение", after != before,
              "%s -> %s" % (before, after))
        check("ввод не потерял фокус",
              app.query_one("#prompt").has_focus)

    async def t_escape(app, pilot):
        app.query_one("#prompt").value = "proxy"
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        check("escape очистил запрос", app.query_one("#prompt").value == "",
              repr(app.query_one("#prompt").value))

    async def t_grep(app, pilot):
        for _ in range(4):   # all→chain→env→pkg→grep
            await pilot.press("tab")
        await pilot.pause()
        check("режим grep", app.mode == "grep", app.mode)
        for k in "token":
            await pilot.press(k)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        check("grep нашёл совпадения", len(app.grep_hits) > 0,
              str(len(app.grep_hits)))
        check("в списке есть строки grep", len(app.rows) > 1)

    async def t_preview(app, pilot):
        app.query_one("#prompt").value = "zshrc"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        check("открылось превью",
              isinstance(app.screen, atlas_tui.PreviewScreen),
              type(app.screen).__name__)
        await pilot.press("escape")
        await pilot.pause()
        check("превью закрылось",
              not isinstance(app.screen, atlas_tui.PreviewScreen))

    async def t_help(app, pilot):
        await pilot.press("f1")
        await pilot.pause()
        check("справка открылась",
              isinstance(app.screen, atlas_tui.HelpScreen))
        await pilot.press("escape")
        await pilot.pause()

    async def t_mask(app, pilot):
        check("секреты скрыты по умолчанию", app.mask is True)
        await pilot.press("slash")
        await pilot.pause()
        for k in "secrets":
            await pilot.press(k)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        check("секреты показаны", app.mask is False)

    async def t_mouse(app, pilot):
        ol = app.query_one("#results")
        await pilot.hover(ol, offset=(3, 6))
        await pilot.pause()
        await pilot.click(ol, offset=(3, 6))
        await pilot.pause(0.3)
        check("клик мышью меняет выделение", ol.highlighted is not None)
        # Клик переводит фокус на список, on_focus возвращает его на Input
        await pilot.pause(0.3)
        check("после клика фокус на вводе",
              app.query_one("#prompt").has_focus)

    async def t_globals(app, pilot):
        check("глобальные включены по умолчанию", app.globals is True)
        for _ in range(2):
            await pilot.press("tab")
        await pilot.pause()
        check("режим env", app.mode == "env", app.mode)
        idx = app.env_index
        from_files = [v for v in idx if v.origin == "file"]
        from_proc = [v for v in idx if v.origin == "process"]
        check("есть переменные из файлов", len(from_files) > 0,
              str(len(from_files)))
        check("есть живые переменные", len(from_proc) > 0,
              str(len(from_proc)))
        check("у живых нет файла-источника",
              all(v.entry is None for v in from_proc))

    async def t_globals_off(app, pilot):
        await pilot.press("slash")
        await pilot.pause()
        for k in "globals":
            await pilot.press(k)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        check("глобальные выключены", app.globals is False)
        check("живых больше нет",
              all(v.origin == "file" for v in app.env_index))

    async def t_scroll(app, pilot):
        """Колесо мыши: подсветка следует за прокруткой."""
        ol = app.query_one("#results")
        await pilot.hover(ol, offset=(10, 5))
        for _ in range(8):
            ol.scroll_down(animate=False)
            await pilot.pause(0.03)
        await pilot.pause(0.4)
        check("прокрутка работает", ol.scroll_y > 0, str(ol.scroll_y))
        # Синхронизируем подсветку: y должен быть в пределах видимой области
        scroll_y = int(ol.scroll_y)
        ol._sync_highlight(scroll_y + 2)
        await pilot.pause(0.2)
        check("подсветка за прокруткой", ol.highlighted is not None and ol.highlighted > 0,
              str(ol.highlighted))
        # детали должны соответствовать выделенной строке
        row = app.rows[ol.highlighted]
        entry = row.entry
        detail = plain(app.query_one("#detail"))
        check("детали соответствуют выделенному",
              entry is not None and entry.app in detail,
              "%s | %s" % (entry.app if entry else "?", detail[:60]))

    async def t_scroll_resets_on_query(app, pilot):
        """Новый запрос — список перестраивается, позиция сбрасывается."""
        ol = app.query_one("#results")
        for _ in range(5):
            await pilot.press("down")
        await pilot.pause(0.3)
        moved = ol.highlighted
        check("стрелка сдвинула выделение", moved > 0, str(moved))
        await pilot.press("s")
        await pilot.pause(0.4)
        check("после запроса выделение сверху", ol.highlighted == 0,
              str(ol.highlighted))

    await scenario("старт", [], t_start)
    await scenario("поиск", [], t_search)
    await scenario("палитра команд", [], t_slash)
    await scenario("команда /ssh", [], t_command)
    await scenario("tab — режим цепочек", [], t_tab)
    await scenario("стрелки", [], t_arrows)
    await scenario("escape", [], t_escape)
    await scenario("grep", [], t_grep)
    await scenario("превью", [], t_preview)
    await scenario("справка", [], t_help)
    await scenario("секреты", [], t_mask)
    await scenario("мышь", [], t_mouse)
    await scenario("скролл колесом", [], t_scroll)
    await scenario("сброс при запросе", [], t_scroll_resets_on_query)
    await scenario("глобальные переменные", [], t_globals)
    await scenario("выключение глобальных", [], t_globals_off)

    print("\n" + "=" * 46)
    if FAILS:
        print("ПРОВАЛЕНО %d: %s" % (len(FAILS), ", ".join(FAILS)))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


asyncio.run(main())
