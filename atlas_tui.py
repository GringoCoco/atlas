#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["textual>=1.0"]
# ///
"""
Config Atlas — интерактивная карта конфигов (интерфейс в стиле Claude Code).

Одна колонка: заголовок, результаты, строка ввода, футер. Превью файла —
во всплывающем окне. Данные и сканирование берутся из config_atlas.py.

Запуск:
    uv run --script atlas_tui.py          # интерфейс
    uv run --script atlas_tui.py --list   # CLI-режимы (см. config_atlas.py)
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_atlas as ca  # noqa: E402

from rich.cells import cell_len  # noqa: E402
from rich.syntax import Syntax  # noqa: E402
from rich.text import Text  # noqa: E402
from textual import on  # noqa: E402
from textual.app import App, ComposeResult  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: E402
from textual.screen import ModalScreen  # noqa: E402
from textual.message import Message  # noqa: E402
from textual.widgets import Input, OptionList, Static  # noqa: E402
from textual.widgets.option_list import Option  # noqa: E402

HOME = os.path.expanduser("~")

# ── Phosphor Amber CRT palette ──────────────────────────────────────────────
ACCENT  = "#e8a020"   # янтарь — главный акцент
BRIGHT  = "#ffd050"   # яркий янтарь — логотип, badges
DIM     = "#7a6030"   # приглушённый янтарь
FAINT   = "#3e3018"   # очень приглушённый
OK      = "#58b840"   # фосфорный зелёный — файл существует
WARN    = "#e06820"   # тёплое предупреждение
BG      = "#080806"   # почти чёрный с тёплым оттенком
PANEL   = "#0e0c08"   # чуть теплее для панелей
TEXT    = "#c8a860"   # основной текст
BORDER  = "#2a2010"   # цвет рамок в обычном состоянии

MODES = [
    ("all",   "Все конфиги"),
    ("chain", "Приоритет конфигов"),
    ("env",   "Переменные окружения"),
    ("pkg",   "Пакеты и версии"),
    ("grep",  "Поиск по тексту"),
]
MODE_TITLE = dict(MODES)

PLACEHOLDER = {
    "all":   " Найти конфиг: ssh, proxy, opencode…  · / — команды",
    "chain": " Фильтр по цепочкам: git, zsh, npm…  · / — команды",
    "env":   " Фильтр по переменным: PATH, NODE…  · / — команды",
    "pkg":   " Фильтр: brew, npm, node, python, cargo…  · / — команды",
    "grep":  " Что искать внутри файлов? Enter — искать",
}

PKG_MANAGER_LABEL = {
    "brew":  "Homebrew",
    "npm":   "npm global",
    "pip":   "pip",
    "uv":    "uv tools",
    "cargo": "Cargo",
    "nvm":   "nvm (Node versions)",
    "go":    "Go binaries",
}

SOURCE_TITLE = {0: "все источники", 1: "только курируемые",
                2: "только найденные"}

PREVIEW_MAX_LINES = 4000


def short(path: str) -> str:
    return "~" + path[len(HOME):] if path.startswith(HOME) else path


def fit(text: Text, width: int) -> Text:
    """Обрезает каждую строку по ширине, сохраняя стили.

    rich не умеет no_wrap у многострочных Text, а truncate() теряет
    оформление, поэтому режем сами.
    """
    out = Text()
    for i, line in enumerate(text.split("\n")):
        if i:
            out.append("\n")
        out.append_text(cut(line, width))
    return out


def cut(text: Text, width: int) -> Text:
    """Обрезает одну строку Text по ширине (в колонках), сохраняя стили."""
    if width <= 1 or text.cell_len <= width:
        return text
    limit = width - 1
    spans = list(text.spans)
    out = Text()
    used = 0
    for i, ch in enumerate(text.plain):
        w = cell_len(ch)
        if used + w > limit:
            break
        style = text.style
        for s0, s1, name in spans:
            if s0 <= i < s1:
                style = name
                break
        out.append(ch, style=style)
        used += w
    out.append("…")
    return out


@dataclass
class Row:
    entry: ca.Entry | None
    prompt: Text
    line: int = 0
    command: str = ""


@dataclass
class Command:
    name: str
    desc: str


def build_commands() -> list[Command]:
    cmds = [
        Command("all",      "режим: все конфиги"),
        Command("chains",   "режим: приоритет конфигов"),
        Command("env",      "режим: переменные окружения"),
        Command("pkg",      "режим: пакеты и версии"),
        Command("grep",     "режим: поиск по содержимому"),
        Command("context",  "контекст разработчика → буфер обмена"),
        # ── 8 диагностик ──────────────────────────────────────────────────────
        Command("trace",    "trace VAR — откуда берётся переменная окружения"),
        Command("diff",     "diff env — расхождение IDE vs терминал"),
        Command("gitaudit", "git-audit — какой email у каждого репо"),
        Command("sshcheck", "ssh-check — аудит ключей и ~/.ssh/config"),
        Command("stale",    "stale — захардкоженные пути к версиям"),
        Command("orphan",   "orphan — конфиги удалённых приложений"),
        Command("scan",     "scan — файлы с секретами в git"),
        Command("export",   "export — сгенерировать setup.sh"),
    ]
    for key, title in ca.CATEGORIES:
        cmds.append(Command(key, "категория: %s" % title))
    cmds += [
        Command("clear",   "сбросить категорию и запрос"),
        Command("missing", "показать/скрыть отсутствующие"),
        Command("secrets", "показать/скрыть секреты"),
        Command("globals", "глобальные переменные окружения"),
        Command("source",  "фильтр по источнику"),
        Command("rescan",  "пересканировать систему"),
        Command("help",    "клавиши и команды"),
        Command("quit",    "выход"),
    ]
    return cmds


COMMANDS = build_commands()


# --------------------------------------------------------------------------- #
#  Превью
# --------------------------------------------------------------------------- #


class PreviewScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape,q", "dismiss", "закрыть"),
        Binding("c", "copy", "копировать путь"),
        Binding("o", "open", "открыть"),
        Binding("f", "finder", "Finder"),
        Binding("m", "mask", "секреты"),
    ]

    def __init__(self, app_ref: "AtlasApp", entry: ca.Entry, line: int = 0):
        super().__init__()
        self.atlas = app_ref
        self.entry = entry
        self.line = line

    def compose(self) -> ComposeResult:
        with Vertical(id="pv-box"):
            yield Static(id="pv-path")
            yield Static(id="pv-head")
            with VerticalScroll(id="pv-body"):
                yield Static(id="pv-code")
            yield Static(id="pv-keys")

    def on_mount(self) -> None:
        box = self.query_one("#pv-box")
        box.border_title = " ░▒▓ ATLAS :: PREVIEW ▓▒░ "
        box.border_subtitle = " esc — close "
        self.render_body()
        if self.line > 3:
            self.call_after_refresh(
                lambda: self.query_one("#pv-body").scroll_to(
                    y=self.line - 3, animate=False))

    def render_body(self) -> None:
        e = self.entry
        path = Text()
        path.append("■ " if e.exists else "□ ", style=OK if e.exists else FAINT)
        path.append(short(e.path), style="bold")
        if e.is_link and e.link_target:
            path.append("  → " + short(e.link_target), style=ACCENT)
        self.query_one("#pv-path", Static).update(path)
        self.query_one("#pv-head", Static).update(entry_details(e))
        keys = Text()
        for k, label in (("esc", "close"), ("c", "copy path"),
                         ("o", "open editor"), ("f", "Finder"),
                         ("m", "secrets:" + ("hidden" if self.atlas.mask
                                             else "VISIBLE"))):
            keys.append(" %s " % k, style="bold " + BG + " on " + DIM)
            keys.append(" " + label + "  ", style=FAINT)
        self.query_one("#pv-keys", Static).update(keys)

        code = self.query_one("#pv-code", Static)
        if not e.exists:
            code.update(Text("Файла нет на диске — здесь он был бы.",
                             style=DIM))
            return
        if e.is_dir:
            try:
                names = sorted(os.listdir(e.path))
            except OSError as exc:
                code.update(Text(str(exc), style=WARN))
                return
            t = Text()
            for n in names[:2000]:
                is_dir = os.path.isdir(os.path.join(e.path, n))
                t.append(("▸ " if is_dir else "  ") + n + "\n",
                         style=ACCENT if is_dir else "")
            code.update(t if names else Text("пустая папка", style=DIM))
            return
        lines, is_bin = ca.read_preview(e.path)
        if is_bin:
            code.update(Text("Двоичный файл — превью недоступно.", style=DIM))
            return
        cut = len(lines) > PREVIEW_MAX_LINES
        lines = lines[:PREVIEW_MAX_LINES]
        if self.atlas.mask:
            lines = ca.mask_secrets(lines)
        body = "\n".join(lines)
        syn = Syntax(body, Syntax.guess_lexer(e.path, body), theme="gruvbox-dark",
                     line_numbers=True, word_wrap=False, background_color="#0a0900",
                     highlight_lines={self.line} if self.line else None)
        code.update(syn)
        if cut:
            self.atlas.notify("Показаны первые %d строк" % PREVIEW_MAX_LINES)

    def action_copy(self) -> None:
        self.atlas.copy_path(self.entry)

    def action_open(self) -> None:
        self.atlas.open_editor(self.entry)

    def action_finder(self) -> None:
        self.atlas.reveal(self.entry)

    def action_mask(self) -> None:
        self.atlas.mask = not self.atlas.mask
        self.render_body()


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,q,f1", "dismiss", "закрыть")]

    def compose(self) -> ComposeResult:
        keys = Text(no_wrap=True, overflow="ellipsis")
        keys.append("── КЛАВИШИ ──────────────────\n\n", style="bold " + ACCENT)
        for k, d in (
            ("↑ ↓  PgUp PgDn", "выбор в списке"),
            ("Enter", "открыть превью"),
            ("Tab / Shift+Tab", "сменить режим"),
            ("Esc", "очистить запрос"),
            ("Ctrl+Y", "копировать путь"),
            ("Ctrl+O", "открыть в редакторе"),
            ("Ctrl+F", "показать в Finder"),
            ("Ctrl+T", "цель симлинка"),
            ("Ctrl+R", "пересканировать"),
            ("Ctrl+C", "выход"),
        ):
            keys.append("  %-18s" % k, style="bold " + TEXT)
            keys.append(d + "\n", style=DIM)

        keys.append("\n── ЗНАЧКИ ───────────────────\n\n", style="bold " + ACCENT)
        for k, d in (("■", "файл существует"), ("□", "файл не найден"),
                     ("►", "директория"), ("⇒", "симлинк"),
                     ("[OK]", "применяется"), ("[--]", "перекрыт"),
                     ("[ACT]", "активный конфиг"), ("[off]", "не активен")):
            keys.append("  %-6s" % k, style="bold " + ACCENT)
            keys.append(d + "\n", style=DIM)

        cmds = Text(no_wrap=True, overflow="ellipsis")
        cmds.append("── КОМАНДЫ (вводи /) ─────────\n\n", style="bold " + ACCENT)
        for c in COMMANDS:
            cmds.append("  /%-14s" % c.name, style="bold " + ACCENT)
            cmds.append(c.desc + "\n", style=DIM)

        with Vertical(id="help-box"):
            with Horizontal(id="help-cols"):
                with VerticalScroll(id="help-left"):
                    yield Static(keys)
                with VerticalScroll(id="help-right"):
                    yield Static(cmds)
            yield Static(Text(
                " esc / q — закрыть  │  F1 — открыть справку",
                style=DIM), id="help-foot")

    def on_mount(self) -> None:
        self.query_one("#help-box").border_title = " ░▒▓ ATLAS :: HELP ▓▒░ "


# --------------------------------------------------------------------------- #
#  Описание записи
# --------------------------------------------------------------------------- #


def entry_details(e: ca.Entry, full: bool = False) -> Text:
    """Сводка по записи. full=True — с абсолютным путём (для превью)."""
    t = Text(no_wrap=True, overflow="ellipsis")
    t.append(e.app or "—", style="bold")
    t.append("  ·  " + ca.CAT_TITLE.get(e.category, e.category), style=DIM)
    if e.chain_role == "winner":
        t.append("  ·  [ACT]", style="bold " + OK)
    elif e.chain_role == "shadow":
        t.append("  ·  [off]", style=WARN)
    if e.chain_level:
        t.append("  ·  " + e.chain_level, style=DIM)
    if e.exists:
        if not e.is_dir:
            t.append("  ·  " + ca.human_size(e.size), style=DIM)
        t.append("  ·  изменён " + e.mtime_str(), style=DIM)
    else:
        t.append("  ·  файла нет", style=DIM)
    if e.is_link and e.link_target:
        t.append("  ·  → " + short(e.link_target), style=ACCENT)
    if e.note:
        t.append("\n" + e.note, style=DIM)
    if full:
        t.append("\n" + e.path, style=FAINT)
    return t


# --------------------------------------------------------------------------- #
#  Приложение
# --------------------------------------------------------------------------- #


class AtlasInput(Input):
    """Поле ввода, у которого Tab переключает режим, а не фокус."""

    BINDINGS = [
        Binding("tab", "app.cycle_mode(1)", show=False, priority=True),
        Binding("shift+tab", "app.cycle_mode(-1)", show=False, priority=True),
    ]


class AtlasList(OptionList):
    """Список результатов.

    Колесо мыши прокручивает список и синхронизирует подсветку со строкой
    под курсором.
    """

    class Scrolled(Message):
        """Список прокрутили."""

    def _on_mouse_scroll_down(self, event) -> None:
        super()._on_mouse_scroll_down(event)
        self.call_after_refresh(self._sync_highlight, int(event.y))

    def _on_mouse_scroll_up(self, event) -> None:
        super()._on_mouse_scroll_up(event)
        self.call_after_refresh(self._sync_highlight, int(event.y))

    def _sync_highlight(self, y: int) -> None:
        """Подсветить строку под курсором мыши."""
        line = y - int(self.scroll_offset.y)
        if 0 <= line < len(self._options):
            if line != self.highlighted:
                self.highlighted = line
            self.post_message(self.Scrolled())

    def on_focus(self, event) -> None:
        """Фокус всегда остаётся на строке ввода."""
        try:
            self.app.query_one("#prompt").focus()
        except Exception:
            pass


class AtlasApp(App[None]):
    TITLE = "ATLAS"

    CSS = f"""
    Screen {{
        background: {BG};
        scrollbar-color: {BORDER};
        scrollbar-background: {BG};
        scrollbar-color-hover: {DIM};
        scrollbar-color-active: {ACCENT};
    }}
    #header {{
        height: 4;
        margin: 0 1;
        padding: 0 1;
        border-bottom: solid {BORDER};
        color: {TEXT};
    }}
    VerticalScroll {{
        scrollbar-color: {BORDER};
        scrollbar-background: {BG};
        scrollbar-color-hover: {DIM};
        scrollbar-color-active: {ACCENT};
    }}
    #results {{
        height: 1fr;
        margin: 0 0 0 0;
        padding: 0;
        background: {BG};
    }}
    OptionList {{
        scrollbar-color: {BORDER};
        scrollbar-background: {BG};
        scrollbar-color-hover: {DIM};
        scrollbar-color-active: {ACCENT};
    }}
    #results > .option-list--option {{
        padding: 0 2;
        color: {TEXT};
    }}
    #results > .option-list--option-highlighted {{
        background: {FAINT};
        color: {BRIGHT};
        text-style: bold;
        border-left: thick {ACCENT};
    }}
    #results > .option-list--option-disabled {{
        color: {ACCENT};
        text-style: bold;
    }}
    #detail {{
        height: auto;
        max-height: 3;
        margin: 0 0;
        padding: 0 2;
        color: {DIM};
        border-top: solid {BORDER};
        border-bottom: solid {BORDER};
    }}
    #prompt-row {{
        height: 3;
        margin: 0 0;
        border-top: solid {BORDER};
        border-bottom: solid {BORDER};
        background: {BG};
        padding: 0 1;
    }}
    #prompt-row:focus-within {{
        border-top: solid {ACCENT};
        border-bottom: solid {ACCENT};
    }}
    #caret {{
        width: 3;
        height: 1;
        color: {ACCENT};
        text-style: bold;
    }}
    #prompt {{
        width: 1fr;
        height: 1;
        border: none;
        background: {BG};
        padding: 0;
        color: {TEXT};
    }}
    #prompt:focus {{
        border: none;
    }}
    #prompt > .input--placeholder {{
        color: {FAINT};
    }}
    #prompt > .input--cursor {{
        background: {ACCENT};
        color: {BG};
        text-style: bold;
    }}
    #modeline {{
        height: 1;
        margin: 0 0;
        padding: 0 2;
        background: {FAINT};
    }}
    #chips {{
        width: 1fr;
        height: 1;
    }}
    #hints {{
        width: auto;
        height: 1;
        text-align: right;
    }}

    PreviewScreen, HelpScreen {{
        align: center middle;
        background: {BG};
        scrollbar-color: {BORDER};
        scrollbar-background: {BG};
        scrollbar-color-hover: {DIM};
        scrollbar-color-active: {ACCENT};
    }}
    #pv-box {{
        width: 100%;
        height: 100%;
        border: solid {ACCENT};
        background: {PANEL};
        padding: 0 2;
    }}
    #pv-head {{
        width: 1fr;
        height: auto;
        padding: 0 0 1 0;
        border-bottom: solid {BORDER};
    }}
    #pv-path {{
        width: 1fr;
        height: 1;
        color: {TEXT};
    }}
    #pv-body {{
        width: 1fr;
        height: 1fr;
        background: {PANEL};
        scrollbar-color: {BORDER};
        scrollbar-background: {PANEL};
        scrollbar-color-hover: {DIM};
        scrollbar-color-active: {ACCENT};
    }}
    #pv-code {{
        width: 1fr;
        height: auto;
    }}
    #pv-keys {{
        width: 1fr;
        height: 1;
        border-top: solid {BORDER};
        color: {DIM};
    }}
    #help-box {{
        width: 100;
        max-width: 96%;
        height: 80%;
        border: solid {ACCENT};
        border-title-color: {BRIGHT};
        border-title-style: bold;
        background: {PANEL};
        padding: 1 2;
    }}
    #help-cols {{
        height: 1fr;
    }}
    #help-left {{
        width: 42;
        border-right: solid {BORDER};
    }}
    #help-right {{
        width: 1fr;
        padding-left: 2;
    }}
    #help-foot {{
        height: 1;
        color: {DIM};
    }}
    """
    BINDINGS = [
        Binding("up", "move(-1)", show=False, priority=True),
        Binding("down", "move(1)", show=False, priority=True),
        Binding("pageup", "move(-10)", show=False, priority=True),
        Binding("pagedown", "move(10)", show=False, priority=True),
        Binding("tab", "cycle_mode(1)", show=False, priority=True),
        Binding("shift+tab", "cycle_mode(-1)", show=False, priority=True),
        Binding("escape", "escape", show=False),
        Binding("ctrl+y", "copy", show=False),
        Binding("ctrl+o", "open", show=False),
        Binding("ctrl+f", "finder", show=False),
        Binding("ctrl+t", "target", show=False),
        Binding("ctrl+r", "rescan", show=False),
        Binding("f1", "help", show=False),
        Binding("ctrl+c", "quit", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[ca.Entry] = ca.build_map()
        self.mode = "all"
        self.category: str | None = None
        self.source = 0
        self.mask = True
        self.show_missing = False
        self.globals = True       # показывать переменные окружения процесса
        self.grep_query = ""
        self.grep_hits: list[tuple[ca.Entry, int, str]] = []
        self.rows: list[Row] = []
        self._diag_cmd = ""   # текущая диагностика: "trace", "diff", …
        self._diag_arg = ""   # аргумент, напр. "PATH"
        # индекс окружения считаем лениво: чтение login-shell занимает ~0.6 с
        self._env_index: list[ca.EnvVar] | None = None

    # -- разметка ---------------------------------------------------------- #

    @property
    def env_index(self) -> list[ca.EnvVar]:
        """Индекс переменных окружения (считается при первом обращении)."""
        if self._env_index is None:
            self._env_index = ca.build_env_index_with_shell(
                self.entries, include_process=self.globals)
        return self._env_index

    def invalidate_env(self) -> None:
        self._env_index = None

    def _env_count(self) -> int:
        """Число переменных без запуска login-shell (для заголовка)."""
        if self._env_index is not None:
            return len(self._env_index)
        try:
            return len(ca.build_env_index(self.entries,
                                          include_process=False))
        except Exception:
            return 0

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        yield AtlasList(id="results")
        yield Static(id="detail")
        with Horizontal(id="prompt-row"):
            yield Static("▶ ", id="caret")
            yield AtlasInput(id="prompt")
        with Horizontal(id="modeline"):
            yield Static(id="chips")
            yield Static(id="hints")

    def on_mount(self) -> None:
        self.query_one("#prompt", Input).focus()
        self.render_header()
        self.refresh_rows()

    def dump_screen(self) -> None:
        """Выгрузить экран в файл — для проверки на живом терминале."""
        dump = os.environ.get("ATLAS_DUMP")
        if not dump:
            return
        try:
            strips = self.screen._compositor.render_strips()
            lines = [s.text.rstrip() for s in strips]
            with open(dump, "w") as fh:
                fh.write("\n".join(lines) + "\n")
        except Exception:
            pass

    def render_header(self) -> None:
        exist = sum(1 for e in self.entries if e.exists)
        t = Text()
        # строка 1: логотип + описание
        t.append("▓▒░", style=DIM)
        t.append(" A T L A S ", style="bold " + BRIGHT)
        t.append("░▒▓", style=DIM)
        t.append("  config map // ", style=FAINT)
        t.append("macOS", style=DIM)
        t.append("   ─── ", style=FAINT)
        # статс-блок
        t.append("paths:", style=FAINT)
        t.append("%d" % len(self.entries), style=ACCENT)
        t.append("  exist:", style=FAINT)
        t.append("%d" % exist, style=ACCENT)
        t.append("  chains:", style=FAINT)
        t.append("%d" % len(ca.CHAIN_GROUPS), style=ACCENT)
        t.append("  env:", style=FAINT)
        t.append("%d" % self._env_count(), style=ACCENT)
        # строка 2: tabs режимов
        t.append("\n ")
        for mode_id, mode_title in MODES:
            active = (mode_id == self.mode) or (
                self.mode == "diag" and mode_id == "grep")  # diag не в табах
            if active and self.mode != "diag":
                t.append(" %s " % mode_title, style="bold " + BG + " on " + ACCENT)
            else:
                t.append(" %s " % mode_title, style=DIM)
            t.append(" ", style=FAINT)
        if self.mode == "diag":
            diag_label = {
                "trace": "trace", "diff": "diff", "gitaudit": "git-audit",
                "ssh": "ssh-check", "stale": "stale", "orphan": "orphan",
                "scan": "scan", "export": "export",
            }.get(self._diag_cmd, self._diag_cmd)
            label = " /%s%s " % (diag_label,
                                  " " + self._diag_arg if self._diag_arg else "")
            t.append(label, style="bold " + BG + " on " + WARN)
        self.query_one("#header", Static).update(t)

    # -- построение списка ------------------------------------------------- #

    @property
    def query_text(self) -> str:
        return self.query_one("#prompt", Input).value

    def pool(self) -> list[ca.Entry]:
        out = self.entries
        if self.source == 1:
            out = [e for e in out if e.source == "curated"]
        elif self.source == 2:
            out = [e for e in out if e.source == "auto"]
        if self.category:
            out = [e for e in out if e.category == self.category]
        return out

    def refresh_rows(self, keep: bool = False) -> None:
        q = self.query_text
        if q.startswith("/"):
            self.rows = self.command_rows(q[1:])
        elif self.mode == "all":
            self.rows = self.all_rows(q.strip())
        elif self.mode == "chain":
            self.rows = self.chain_rows(q.strip().lower())
        elif self.mode == "env":
            self.rows = self.env_rows(q.strip().lower())
        elif self.mode == "pkg":
            self.rows = self.pkg_rows(q.strip())
        elif self.mode == "diag":
            self.rows = self.diag_rows(self._diag_cmd, self._diag_arg)
        else:
            self.rows = self.grep_rows(q.strip())

        ol = self.query_one("#results", AtlasList)
        old = ol.highlighted if keep else None
        # clear_options() обнуляет scroll_y, поэтому запоминаем позицию
        # и восстанавливаем её после перестроения списка
        prev_scroll = ol.scroll_y
        width = max(20, ol.scrollable_content_region.width or
                    (self.size.width - 4))
        ol.clear_options()
        ol.add_options([
            Option(fit(r.prompt, width), id=str(i),
                   disabled=(r.entry is None and not r.command))
            for i, r in enumerate(self.rows)
        ])
        target = None
        if old is not None and old < len(self.rows) and not self._disabled(old):
            target = old
        else:
            target = self._next_enabled(-1, 1)
        if target is not None:
            ol.highlighted = target
        # если список перестроили из-за запроса — возвращаем прокрутку
        # scroll_to после add_options нужно отложить до следующего layout
        if keep and prev_scroll:
            self.call_after_refresh(
                lambda: ol.scroll_to(y=prev_scroll, animate=False))
        self.update_detail()
        self.update_chrome()

    def _disabled(self, i: int) -> bool:
        r = self.rows[i]
        return r.entry is None and not r.command

    def _next_enabled(self, start: int, step: int) -> int | None:
        i = start + step
        while 0 <= i < len(self.rows):
            if not self._disabled(i):
                return i
            i += step
        return None

    def command_rows(self, q: str) -> list[Row]:
        q = q.strip().lower()
        out = []
        for c in COMMANDS:
            if q and q not in c.name and q not in c.desc.lower():
                continue
            t = Text()
            t.append("/" + c.name.ljust(12), style="bold " + ACCENT)
            t.append(c.desc, style=DIM)
            out.append(Row(None, t, command=c.name))
        if not out:
            out.append(Row(None, Text("Нет такой команды", style=DIM)))
        return out

    def entry_prompt(self, e: ca.Entry) -> Text:
        if e.is_link:
            icon, style = "⇒", ACCENT
        elif e.is_dir:
            icon, style = "►", ACCENT
        elif e.exists:
            icon, style = "■", OK
        else:
            icon, style = "□", FAINT
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append(icon + " ", style=style)
        path = short(e.path)
        if e.relative:
            path = "(проект) " + path
        t.append(path, style=TEXT if e.exists else FAINT)
        if e.chain_role == "winner":
            t.append("  [OK]", style="bold " + OK)
        elif e.chain_role == "shadow":
            t.append("  [--]", style=WARN)
        if e.app:
            t.append("   " + e.app, style=DIM)
        return t
    def all_rows(self, q: str) -> list[Row]:
        pool = self.pool()
        if not self.show_missing:
            pool = [e for e in pool if e.exists]
        if q:
            found = ca.search(pool, q)
        else:
            found = pool if self.category else [e for e in pool
                                                 if not e.alias]
        rows = [Row(e, self.entry_prompt(e)) for e in found]
        if not rows:
            rows = [Row(None, Text("Ничего не нашлось. Попробуй другое слово"
                                   " или /missing.", style=DIM))]
        return rows

    def chain_rows(self, q: str) -> list[Row]:
        by_chain: dict[str, list[ca.Entry]] = {}
        for e, _ in ca.chain_rows(self.entries):
            by_chain.setdefault(e.chain, []).append(e)
        rows: list[Row] = []
        for ch in ca.CHAIN_GROUPS:
            if self.category and ch.category != self.category:
                continue
            items = by_chain.get(ch.id, [])
            if not self.show_missing:
                items = [e for e in items if e.chain_role != "absent"]
            if q:
                if q not in ch.title.lower() and q not in ch.id:
                    items = [e for e in items if q in e.path.lower()]
            if not items:
                continue
            head = Text(no_wrap=True, overflow="ellipsis")
            head.append(ch.title, style="bold " + ACCENT)
            head.append("   " + ch.note, style=DIM)
            rows.append(Row(None, head))
            for e in items:
                t = Text(no_wrap=True, overflow="ellipsis")
                if e.chain_role == "winner":
                    t.append("  ► ", style="bold " + OK)
                    pstyle = TEXT
                elif e.chain_role == "shadow":
                    t.append("  · ", style=WARN)
                    pstyle = DIM
                else:
                    t.append("  · ", style=FAINT)
                    pstyle = FAINT
                path = short(e.path)
                if e.relative:
                    path = "(проект) " + path
                t.append(path, style=pstyle)
                t.append("   " + e.chain_level, style=FAINT)
                rows.append(Row(e, t))
        if not rows:
            rows = [Row(None, Text("Нет подходящих цепочек.", style=DIM))]
        return rows

    def env_rows(self, q: str) -> list[Row]:
        items = list(self.env_index)
        if self.category:
            items = [v for v in items
                     if v.entry and v.entry.category == self.category]
        if q:
            items = [v for v in items
                     if q in v.name.lower() or q in v.value.lower()]
        items.sort(key=lambda v: (v.name, v.origin != "file",
                                  v.entry.path if v.entry else "",
                                  v.lineno))
        rows: list[Row] = []
        last = None
        for v in items:
            if v.name != last:
                n = sum(1 for x in items if x.name == v.name)
                head = Text(no_wrap=True)
                head.append(v.name, style="bold " + ACCENT)
                if n > 1:
                    head.append("   задана %d раз — действует последняя"
                                % n, style=DIM)
                rows.append(Row(None, head))
                last = v.name
            val = ca.mask_value(v.name, v.value) if self.mask else v.value
            t = Text(no_wrap=True, overflow="ellipsis")
            if v.entry:
                t.append("  %s:%d" % (short(v.entry.path), v.lineno), style=DIM)
            else:
                t.append("  ⚙ только в окружении", style=FAINT)
            t.append("   " + val)
            rows.append(Row(v.entry, t, line=v.lineno))
        if not rows:
            rows = [Row(None, Text("Переменных не найдено.", style=DIM))]
        return rows

    def pkg_rows(self, q: str) -> list[Row]:
        """Пакеты и версии инструментов, сгруппированные по менеджеру."""
        pkgs = ca.scan_packages()
        rows: list[Row] = []

        # Строка с контекстом разработчика наверху
        ctx = ca.get_dev_context()
        summary = Text(no_wrap=True)
        summary.append("⚡ ", style="bold " + ACCENT)
        parts = []
        if ctx.node_version:
            parts.append("node %s" % ctx.node_version)
        if ctx.python_version:
            parts.append("python %s" % ctx.python_version)
        if ctx.go_version:
            parts.append("go %s" % ctx.go_version)
        if ctx.rust_version:
            parts.append("rust %s" % ctx.rust_version)
        summary.append("  ".join(parts) if parts else "версии не определены",
                       style=DIM)
        if ctx.path_issues:
            summary.append("   ⚠ PATH: %d проблем" % len(ctx.path_issues),
                            style="bold " + WARN)
        if ctx.env_conflicts:
            summary.append("   ⚡ конфликты: %d" % len(ctx.env_conflicts),
                           style="bold " + WARN)
        rows.append(Row(None, summary, command="context"))

        if not pkgs:
            rows.append(Row(None, Text("Пакетные менеджеры не найдены.", style=DIM)))
            return rows

        ql = q.lower()
        for mgr, items in pkgs.items():
            label = PKG_MANAGER_LABEL.get(mgr, mgr)
            # фильтрация по запросу
            filtered = [p for p in items
                        if not ql or ql in p.name.lower()
                        or ql in p.version.lower()
                        or ql in mgr.lower()
                        or ql in label.lower()]
            if not filtered:
                continue

            # заголовок группы
            head = Text(no_wrap=True)
            head.append(label, style="bold " + ACCENT)
            head.append("  %d пакетов" % len(filtered), style=DIM)
            rows.append(Row(None, head))

            for pkg in filtered:
                t = Text(no_wrap=True, overflow="ellipsis")
                t.append("  %-32s" % pkg.name[:32])
                t.append(pkg.version, style=DIM)
                if pkg.extra and pkg.extra not in ("global",):
                    t.append("  %s" % pkg.extra, style=FAINT)
                rows.append(Row(None, t, command="copy_pkg:%s@%s" % (pkg.name, pkg.version)))

        if not rows or (len(rows) == 1):  # только summary
            rows.append(Row(None, Text("По «%s» ничего не найдено." % q, style=DIM)))
        return rows

    # ── 8 диагностик ─────────────────────────────────────────────────────── #

    def diag_rows(self, cmd: str, arg: str) -> list[Row]:
        """Универсальный рендерер для /trace /diff /gitaudit /ssh /stale /orphan /scan /export."""
        rows: list[Row] = []

        def head(text: str, style: str = "bold " + ACCENT) -> None:
            rows.append(Row(None, Text(text, style=style, no_wrap=True)))

        def line(text: str, style: str = "") -> None:
            t = Text(no_wrap=True, overflow="ellipsis")
            if style:
                t.append(text, style=style)
            else:
                t.append(text)
            rows.append(Row(None, t))

        def entry_row(e: ca.Entry, extra: str = "", warn: bool = False) -> None:
            t = Text(no_wrap=True, overflow="ellipsis")
            icon = "■" if e.exists else "□"
            t.append("  %s " % icon, style=OK if e.exists else FAINT)
            t.append(short(e.path), style=TEXT if e.exists else FAINT)
            if extra:
                t.append("   " + extra, style=WARN if warn else DIM)
            rows.append(Row(e, t))

        def copy_row(text: str, label: str) -> None:
            t = Text(no_wrap=True, overflow="ellipsis")
            t.append("  ► ", style=ACCENT)
            t.append(label, style=DIM)
            t.append("   ", style=FAINT)
            t.append(text, style=TEXT)
            rows.append(Row(None, t, command="copy_text:" + text))

        # ── /trace VAR ──────────────────────────────────────────────────────
        if cmd == "trace":
            var = arg.strip().upper() or "PATH"
            head("── trace %s ────────────────────────────────" % var)
            tr = ca.trace_env_var(var, self.entries)
            if tr.process_value:
                val_display = (ca.mask_value(var, tr.process_value)
                               if self.mask else tr.process_value)
                line("  Текущее значение:  " + val_display[:120])
            else:
                line("  Переменная не задана в текущем окружении", style=WARN)
            line("")
            if tr.sources:
                line("  Определена в %d месте(ах):" % len(tr.sources), style=DIM)
                for s in tr.sources:
                    t = Text(no_wrap=True, overflow="ellipsis")
                    t.append("  %s" % ("⇒" if s["origin"] == "process" else "■"), style=ACCENT)
                    t.append("  %s" % short(s["file"]), style=TEXT)
                    if s["line"]:
                        t.append(":%d" % s["line"], style=DIM)
                    raw = (ca.mask_value(var, s["raw"]) if self.mask else s["raw"])
                    t.append("   %s" % raw[:80], style=FAINT)
                    rows.append(Row(None, t))
            else:
                line("  Источник не найден в конфиг-файлах", style=FAINT)
            return rows

        # ── /diff env ──────────────────────────────────────────────────────
        if cmd == "diff":
            head("── diff env: IDE/агент  vs  login shell ───────")
            diffs = ca.diff_env(self.entries)
            conflicts = [d for d in diffs if d.status == "conflict"]
            only_proc = [d for d in diffs if d.status == "only_process"]
            only_sh   = [d for d in diffs if d.status == "only_shell"]
            if not diffs:
                line("  ✓ Расхождений нет — IDE и терминал видят одинаковое окружение",
                     style=OK)
                return rows
            line("  %d конфликтов · %d только в IDE · %d только в shell"
                 % (len(conflicts), len(only_proc), len(only_sh)), style=DIM)
            line("")
            for d in conflicts[:30]:
                t = Text(no_wrap=True, overflow="ellipsis")
                t.append("  ≠ ", style="bold " + WARN)
                t.append("%-20s" % d.name, style="bold " + TEXT)
                pv = ca.mask_value(d.name, d.process_val) if self.mask else d.process_val
                sv = ca.mask_value(d.name, d.shell_val)   if self.mask else d.shell_val
                t.append("  IDE: ", style=FAINT)
                t.append(pv[:40], style=WARN)
                t.append("  shell: ", style=FAINT)
                t.append(sv[:40], style=OK)
                rows.append(Row(None, t))
            if only_proc:
                line("")
                line("  Только в IDE:", style=DIM)
                for d in only_proc[:10]:
                    pv = ca.mask_value(d.name, d.process_val) if self.mask else d.process_val
                    line("    %-20s  %s" % (d.name, pv[:60]), style=FAINT)
            if only_sh:
                line("")
                line("  Только в shell:", style=DIM)
                for d in only_sh[:10]:
                    sv = ca.mask_value(d.name, d.shell_val) if self.mask else d.shell_val
                    line("    %-20s  %s" % (d.name, sv[:60]), style=FAINT)
            return rows

        # ── /gitaudit ──────────────────────────────────────────────────────
        if cmd == "gitaudit":
            head("── git-audit: на какой email пойдёт следующий коммит ──")
            self.notify("Сканирую репозитории…")
            repos = ca.git_audit()
            if not repos:
                line("  Репозитории не найдены", style=FAINT)
                return rows

            global_email = repos[0].global_email if repos else ""
            global_name  = repos[0].global_name  if repos else ""

            # Строка с глобальным дефолтом — контекст для всего остального
            line("")
            t = Text(no_wrap=True)
            t.append("  Глобальный ~/.gitconfig:  ", style=FAINT)
            t.append("%s " % global_name, style=TEXT)
            t.append("<%s>" % global_email, style=DIM)
            t.append("  — используется везде, где нет локального .git/config",
                     style=FAINT)
            rows.append(Row(None, t))
            line("")

            # Группа 1: репо с локальным override
            local_repos = [r for r in repos if r.has_local_config]
            if local_repos:
                t = Text(no_wrap=True)
                t.append("  ── Локальный override (%d репо) " % len(local_repos),
                         style="bold " + ACCENT)
                t.append("— email берётся из .git/config этого репо", style=FAINT)
                rows.append(Row(None, t))
                for r in sorted(local_repos, key=lambda x: x.path):
                    t = Text(no_wrap=True, overflow="ellipsis")
                    t.append("  ► ", style=ACCENT)
                    t.append("%-38s" % short(r.path)[:38], style=TEXT)
                    t.append("  коммит пойдёт как: ", style=FAINT)
                    if r.local_name:
                        t.append(r.local_name + " ", style=DIM)
                    t.append("<%s>" % r.effective_email, style=ACCENT)
                    if r.unsigned:
                        t.append("  ⚠ signing не задан", style=WARN)
                    rows.append(Row(None, t))
                line("")

            # Группа 2: используют глобальный
            global_repos = [r for r in repos if not r.has_local_config]
            if global_repos:
                t = Text(no_wrap=True)
                t.append("  ── Глобальный дефолт (%d репо) " % len(global_repos),
                         style=DIM)
                t.append("— коммит пойдёт как <%s>" % global_email, style=FAINT)
                rows.append(Row(None, t))
                for r in sorted(global_repos, key=lambda x: x.path):
                    t = Text(no_wrap=True, overflow="ellipsis")
                    t.append("  · ", style=FAINT)
                    t.append(short(r.path), style=FAINT)
                    rows.append(Row(None, t))

            return rows

        # ── /ssh ──────────────────────────────────────────────────────────
        if cmd == "ssh":
            head("── ssh-audit: ключи и ~/.ssh/config ──────────")
            sa = ca.ssh_audit()
            if sa.known_issues:
                line("  ⚠ %d проблем:" % len(sa.known_issues), style=WARN)
                for issue in sa.known_issues:
                    line("    " + issue, style=WARN)
                line("")
            else:
                line("  ✓ Проблем не найдено", style=OK)
                line("")
            line("  Агент (%d ключей):" % len(sa.agent_keys), style=DIM)
            for k in sa.agent_keys:
                line("    " + k[:90], style=FAINT)
            line("")
            line("  Хосты в ~/.ssh/config:", style=DIM)
            for h in sa.hosts:
                t = Text(no_wrap=True, overflow="ellipsis")
                ok_icon = "■" if h.key_exists else "□"
                agent_icon = "●" if h.key_in_agent else "○"
                warn = not h.key_exists
                t.append("  %s%s " % (ok_icon, agent_icon),
                          style=WARN if warn else OK)
                t.append("%-25s" % h.name, style=TEXT)
                t.append("  " + (h.hostname or "*"), style=DIM)
                if h.identity_file:
                    t.append("  key: " + short(h.identity_file), style=FAINT)
                if h.forward_agent:
                    t.append("  [ForwardAgent]", style=ACCENT)
                rows.append(Row(None, t))
            return rows

        # ── /stale ────────────────────────────────────────────────────────
        if cmd == "stale":
            head("── stale: захардкоженные пути к версиям ───────")
            self.notify("Сканирую файлы…")
            stale = ca.find_stale_refs(self.entries)
            if not stale:
                line("  ✓ Захардкоженных путей к конкретным версиям не найдено",
                     style=OK)
                return rows
            line("  %d ссылок в %d файлах"
                 % (len(stale), len({s.entry.path for s in stale})), style=DIM)
            last_path = ""
            for s in stale:
                if s.entry.path != last_path:
                    t = Text(no_wrap=True)
                    t.append("  ■ ", style=WARN)
                    t.append(short(s.entry.path), style="bold " + TEXT)
                    rows.append(Row(s.entry, t))
                    last_path = s.entry.path
                t = Text(no_wrap=True, overflow="ellipsis")
                t.append("    :%d  " % s.line, style=FAINT)
                t.append(s.raw_line[:100], style=DIM)
                t.append("   // " + s.reason, style=WARN)
                rows.append(Row(None, t))
            return rows

        # ── /orphan ───────────────────────────────────────────────────────
        if cmd == "orphan":
            head("── orphan: конфиги удалённых приложений ───────")
            self.notify("Сканирую установленные приложения…")
            orphans = ca.find_orphans(self.entries)
            if not orphans:
                line("  ✓ Конфигов удалённых приложений не найдено", style=OK)
                return rows
            line("  %d приложений с осиротевшими конфигами" % len(orphans),
                 style=DIM)
            line("")
            for o in orphans:
                t = Text(no_wrap=True, overflow="ellipsis")
                t.append("  □ ", style=FAINT)
                t.append("%-30s" % o.app_name, style=TEXT)
                t.append("  " + short(o.entry.path), style=DIM)
                rows.append(Row(o.entry, t))
            return rows

        # ── /scan (secret leaks) ──────────────────────────────────────────
        if cmd == "scan":
            head("── scan: секреты в git-tracked файлах ─────────")
            self.notify("Сканирую файлы на секреты…")
            leaks = ca.scan_secret_leaks(self.entries)
            if not leaks:
                line("  ✓ Секреты в git-tracked файлах не обнаружены", style=OK)
                return rows
            git_leaks = [l for l in leaks if l.in_git]
            line("  %d потенциальных утечек · %d в git-репозиториях"
                 % (len(leaks), len(git_leaks)), style=WARN if git_leaks else DIM)
            last_path = ""
            for lk in leaks:
                if lk.entry.path != last_path:
                    t = Text(no_wrap=True)
                    icon = "■" if lk.in_git else "·"
                    t.append("  %s " % icon, style=WARN if lk.in_git else FAINT)
                    t.append(short(lk.entry.path), style="bold " + TEXT)
                    if lk.in_git:
                        t.append("  ⚠ TRACKED BY GIT: " + lk.git_repo, style="bold " + WARN)
                    rows.append(Row(lk.entry, t))
                    last_path = lk.entry.path
                t = Text(no_wrap=True, overflow="ellipsis")
                t.append("    :%d  " % lk.line, style=FAINT)
                t.append(lk.raw_line[:100], style=DIM)
                rows.append(Row(None, t))
            return rows

        # ── /export ───────────────────────────────────────────────────────
        if cmd == "export":
            fmt = arg.strip() or "sh"
            head("── export: генерация setup.sh ──────────────────")
            script = ca.generate_export(fmt)
            lines_list = script.splitlines()
            line("  %d строк · скопировать: Enter" % len(lines_list), style=DIM)
            line("")
            # preview первых 40 строк
            for ln in lines_list[:40]:
                t = Text(no_wrap=True, overflow="ellipsis")
                if ln.startswith("#"):
                    t.append("  " + ln, style=FAINT)
                elif ln.startswith("git ") or ln.startswith("brew ") or \
                     ln.startswith("npm ") or ln.startswith("cargo ") or \
                     ln.startswith("uv "):
                    t.append("  ", style="")
                    t.append(ln, style=TEXT)
                else:
                    t.append("  " + ln, style=DIM)
                rows.append(Row(None, t))
            if len(lines_list) > 40:
                line("  … ещё %d строк" % (len(lines_list) - 40), style=FAINT)
            # строка «копировать всё» — команда
            rows.append(Row(None,
                Text("  ► скопировать весь скрипт → буфер обмена",
                     style="bold " + ACCENT),
                command="copy_export:" + fmt))
            return rows

        line("Неизвестная команда: " + cmd, style=WARN)
        return rows

    def grep_rows(self, q: str) -> list[Row]:
        if not self.grep_query:
            return [Row(None, Text("Введи текст и нажми Enter — поищу его "
                                   "внутри всех конфигов.", style=DIM))]
        rows: list[Row] = []
        if q and q != self.grep_query:
            rows.append(Row(None, Text("Enter — искать «%s»" % q,
                                       style=DIM)))
        hits = self.grep_hits
        if self.category:
            hits = [h for h in hits if h[0].category == self.category]
        last = None
        for e, lineno, line in hits:
            if e.path != last:
                rows.append(Row(None, Text(short(e.path),
                                           style="bold " + ACCENT)))
                last = e.path
            shown = ca.mask_secrets([line])[0] if self.mask else line
            t = Text(no_wrap=True, overflow="ellipsis")
            t.append("  %5d  " % lineno, style=FAINT)
            t.append(shown[:300])
            t.highlight_words([self.grep_query], style="bold " + ACCENT,
                              case_sensitive=False)
            rows.append(Row(e, t, line=lineno))
        if not hits:
            rows.append(Row(None, Text("По «%s» ничего не нашлось."
                                       % self.grep_query, style=DIM)))
        return rows

    # -- нижняя часть ------------------------------------------------------ #

    def current_row(self) -> Row | None:
        ol = self.query_one("#results", AtlasList)
        i = ol.highlighted
        if i is None or i >= len(self.rows):
            return None
        return self.rows[i]

    def current_entry(self) -> ca.Entry | None:
        r = self.current_row()
        return r.entry if r else None

    def update_detail(self) -> None:
        w = self.query_one("#detail", Static).size.width or 100
        row = self.current_row()
        e = self.current_entry()
        if row is not None and e is None and self.mode == "env":
            # глобальная переменная: файла-источника нет
            var = self._env_var_for(row)
            if var is not None:
                t = Text(no_wrap=True, overflow="ellipsis")
                t.append(var.name, style="bold")
                t.append("  ·  только в окружении процесса", style=DIM)
                t.append("\n")
                t.append(ca.mask_value(var.name, var.value) if self.mask
                         else var.value)
                self.query_one("#detail", Static).update(fit(t, w))
                return
        if e is None:
            self.query_one("#detail", Static).update(Text(""))
            return
        t = entry_details(e)
        t.append("\n" + e.path, style=FAINT)
        self.query_one("#detail", Static).update(fit(t, w))

    def _env_var_for(self, row: Row) -> ca.EnvVar | None:
        """Найти EnvVar по строке списка (у переменной из файла есть entry)."""
        name = row.prompt.plain.strip()
        for v in self.env_index:
            if v.name == name:
                return v
        return None

    def update_chrome(self) -> None:
        left = Text()
        if self.category:
            left.append("▐", style=ACCENT)
            left.append(" %s " % ca.CAT_TITLE[self.category],
                        style="bold " + BG + " on " + ACCENT)
            left.append("▌ ", style=ACCENT)
        if self.source:
            left.append("▐", style=DIM)
            left.append(" %s " % SOURCE_TITLE[self.source],
                        style="bold " + BG + " on " + DIM)
            left.append("▌ ", style=DIM)
        if self.show_missing:
            left.append("▐", style=DIM)
            left.append(" +скрытые ", style="bold " + BG + " on " + DIM)
            left.append("▌ ", style=DIM)
        if not self.mask:
            left.append("▐", style=WARN)
            left.append(" SECRETS ", style="bold " + BG + " on " + WARN)
            left.append("▌ ", style=WARN)
        if self.mode == "env" and self.globals:
            left.append("▐", style=DIM)
            left.append(" global env ", style="bold " + BG + " on " + DIM)
            left.append("▌ ", style=DIM)

        right = Text()
        q = self.query_text
        if q.startswith("/"):
            right.append("CMD: ", style="bold " + DIM)
            for name, desc in (("chains", "приоритет"), ("env", "окружение"),
                                ("pkg", "пакеты"), ("grep", "поиск"),
                                ("missing", "скрытые"), ("secrets", "секреты"),
                                ("context", "контекст")):
                right.append("/" + name, style="bold " + ACCENT)
                right.append(" " + desc + "  ", style=FAINT)
        else:
            right.append("[ ", style=DIM)
            right.append(MODE_TITLE.get(self.mode, self.mode), style="bold " + BRIGHT)
            right.append(" ]  ", style=DIM)
            n = sum(1 for r in self.rows if r.entry is not None)
            right.append("%d  " % n, style=DIM)
            if self.mode == "pkg":
                for k, d in (("/", "cmd"), ("enter", "copy"), ("^r", "rescan")):
                    right.append(k, style="bold " + ACCENT)
                    right.append(" %s  " % d, style=FAINT)
            elif self.mode == "diag":
                diag_label = {
                    "trace": "trace", "diff": "diff",
                    "gitaudit": "git-audit", "ssh": "ssh-check",
                    "stale": "stale", "orphan": "orphan",
                    "scan": "scan", "export": "export",
                }.get(self._diag_cmd, self._diag_cmd)
                right.append("[ ", style=DIM)
                right.append(diag_label, style="bold " + WARN)
                if self._diag_arg:
                    right.append(" %s" % self._diag_arg, style=BRIGHT)
                right.append(" ]  ", style=DIM)
                for k, d in (("/", "cmd"), ("enter", "copy"), ("^r", "refresh")):
                    right.append(k, style="bold " + ACCENT)
                    right.append(" %s  " % d, style=FAINT)
            else:
                for k, d in (("/", "cmd"), ("enter", "open"),
                             ("^y", "path"), ("^o", "edit")):
                    right.append(k, style="bold " + ACCENT)
                    right.append(" %s  " % d, style=FAINT)

        self.query_one("#chips", Static).update(left)
        self.query_one("#hints", Static).update(right)
        inp = self.query_one("#prompt", Input)
        if q.startswith("/"):
            inp.placeholder = " /trace VAR  /diff  /gitaudit  /ssh  /stale  /orphan  /scan  /export"
        else:
            inp.placeholder = PLACEHOLDER.get(self.mode, " / — команды  ·  esc — назад")

    def on_resize(self) -> None:
        self.update_chrome()

    # -- события ----------------------------------------------------------- #

    @on(Input.Changed, "#prompt")
    def _changed(self) -> None:
        self.refresh_rows()

    @on(Input.Submitted, "#prompt")
    def _submitted(self) -> None:
        self.activate()

    @on(OptionList.OptionHighlighted, "#results")
    def _highlighted(self) -> None:
        self.update_detail()
    @on(OptionList.OptionSelected, "#results")
    def _selected(self) -> None:
        self.activate()

    def activate(self) -> None:
        q = self.query_text
        row = self.current_row()
        if q.startswith("/"):
            if row and row.command:
                self.run_command(row.command)
            return
        if self.mode == "grep" and q.strip() and q.strip() != self.grep_query:
            self.run_grep(q.strip())
            return
        if self.mode in ("pkg", "diag") and row and row.command:
            self.run_command(row.command)
            return
        if row and row.entry:
            self.push_screen(PreviewScreen(self, row.entry, row.line))

    def run_grep(self, q: str) -> None:
        self.grep_query = q
        self.grep_hits = ca.grep_entries(self.pool(), q)
        files = len({e.path for e, _, _ in self.grep_hits})
        self.notify("«%s»: %d совпадений в %d файлах" % (
            q, len(self.grep_hits), files))
        self.refresh_rows()

    def run_command(self, name: str) -> None:
        inp = self.query_one("#prompt", Input)

        # ── диагностические команды (/trace PATH, /diff, /ssh, …) ─────────
        diag_cmds = {
            "trace":    "trace",
            "diff":     "diff",
            "gitaudit": "gitaudit",
            "sshcheck": "ssh",
            "stale":    "stale",
            "orphan":   "orphan",
            "scan":     "scan",
            "export":   "export",
        }
        # поддержка "/trace PATH" — аргумент идёт после пробела
        cmd_base = name.split()[0] if name.split() else name
        cmd_arg  = name[len(cmd_base):].strip()

        if cmd_base in diag_cmds:
            self._diag_cmd = diag_cmds[cmd_base]
            self._diag_arg = cmd_arg
            self.mode = "diag"
            self.render_header()
            inp.value = ""
            self.refresh_rows()
            return

        modes = {"all": "all", "chains": "chain", "env": "env",
                 "pkg": "pkg", "grep": "grep"}
        if name in modes:
            self.mode = modes[name]
            self.render_header()
        elif name in ca.CAT_TITLE:
            self.category = name
        elif name == "clear":
            self.category = None
        elif name == "missing":
            self.show_missing = not self.show_missing
        elif name == "secrets":
            self.mask = not self.mask
        elif name == "globals":
            self.globals = not self.globals
            self.invalidate_env()
        elif name == "source":
            self.source = (self.source + 1) % 3
        elif name == "rescan":
            inp.value = ""
            self.action_rescan()
            return
        elif name == "help":
            inp.value = ""
            self.action_help()
            return
        elif name == "quit":
            self.exit()
            return
        elif name == "context":
            text = ca.dev_context_text()
            try:
                subprocess.run(["pbcopy"], input=text.encode(), check=True)
                self.notify("Контекст скопирован в буфер обмена")
            except Exception:
                self.notify("Не удалось скопировать", severity="error")
            return
        elif name.startswith("copy_pkg:"):
            pkg_str = name[len("copy_pkg:"):]
            try:
                subprocess.run(["pbcopy"], input=pkg_str.encode(), check=True)
                self.notify("Скопировано: " + pkg_str)
            except Exception:
                self.notify("Не удалось скопировать", severity="error")
            return
        elif name.startswith("copy_text:"):
            text = name[len("copy_text:"):]
            try:
                subprocess.run(["pbcopy"], input=text.encode(), check=True)
                self.notify("Скопировано")
            except Exception:
                self.notify("Не удалось скопировать", severity="error")
            return
        elif name.startswith("copy_export:"):
            fmt = name[len("copy_export:"):] or "sh"
            try:
                script = ca.generate_export(fmt)
                subprocess.run(["pbcopy"], input=script.encode(), check=True)
                self.notify("setup.sh скопирован (%d строк)" % len(script.splitlines()))
            except Exception:
                self.notify("Не удалось скопировать", severity="error")
            return
        inp.value = ""

        self.refresh_rows()

    # -- действия ---------------------------------------------------------- #

    def action_move(self, d: int) -> None:
        if not self.rows:
            return
        ol = self.query_one("#results", AtlasList)
        cur = ol.highlighted if ol.highlighted is not None else -1
        step = 1 if d > 0 else -1
        target = cur
        for _ in range(abs(d)):
            nxt = self._next_enabled(target, step)
            if nxt is None:
                break
            target = nxt
        if target != cur and target >= 0:
            ol.highlighted = target

    def action_cycle_mode(self, d: int) -> None:
        keys = [m for m, _ in MODES]
        self.mode = keys[(keys.index(self.mode) + d) % len(keys)]
        inp = self.query_one("#prompt", Input)
        if inp.value.startswith("/"):
            inp.value = ""
        self.render_header()
        if self.mode == "grep" and inp.value.strip() and \
                inp.value.strip() != self.grep_query:
            self.run_grep(inp.value.strip())
            return
        self.refresh_rows()

    def action_escape(self) -> None:
        inp = self.query_one("#prompt", Input)
        if inp.value:
            inp.value = ""
        elif self.category or self.source or self.show_missing:
            self.category = None
            self.source = 0
            self.show_missing = False
            self.refresh_rows()
        elif self.mode != "all":
            self.mode = "all"
            self.refresh_rows()

    def copy_path(self, e: ca.Entry | None) -> None:
        if e is None:
            return
        try:
            subprocess.run(["pbcopy"], input=e.path.encode(), check=True)
            self.notify("Скопировано: " + short(e.path))
        except Exception as exc:  # noqa: BLE001
            self.notify("Не удалось скопировать: %s" % exc, severity="error")

    def open_editor(self, e: ca.Entry | None) -> None:
        if e is None:
            return
        if not e.exists:
            self.notify("Файла нет на диске", severity="warning")
            return
        editor = os.environ.get("EDITOR", "").strip()
        try:
            if editor and not e.is_dir:
                subprocess.Popen(editor.split() + [e.path],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                self.notify("Открыто в " + editor)
            else:
                subprocess.run(["open", "-t" if not e.is_dir else "-R", e.path])
                self.notify("Открыто")
        except Exception as exc:  # noqa: BLE001
            self.notify("Ошибка: %s" % exc, severity="error")

    def reveal(self, e: ca.Entry | None) -> None:
        if e is None:
            return
        target = e.path if e.exists else os.path.dirname(e.path)
        subprocess.run(["open", "-R", target])
        self.notify("Показано в Finder")

    def action_copy(self) -> None:
        self.copy_path(self.current_entry())

    def action_open(self) -> None:
        self.open_editor(self.current_entry())

    def action_finder(self) -> None:
        self.reveal(self.current_entry())

    def action_target(self) -> None:
        e = self.current_entry()
        if e is None or not e.is_link or not e.link_target:
            self.notify("Это не симлинк", severity="warning")
            return
        target = e.link_target
        if not os.path.isabs(target):
            target = os.path.join(os.path.dirname(e.path), target)
        target = os.path.normpath(target)
        for i, r in enumerate(self.rows):
            if r.entry and r.entry.path == target:
                self.query_one("#results", AtlasList).highlighted = i
                self.notify("Цель: " + short(target))
                return
        found = next((x for x in self.entries if x.path == target), None)
        if found:
            self.push_screen(PreviewScreen(self, found))
        else:
            self.notify("Цель вне карты: " + short(target))

    def action_rescan(self) -> None:
        self.entries = ca.build_map()
        self.invalidate_env()
        if self.grep_query:
            self.grep_hits = ca.grep_entries(self.pool(), self.grep_query)
        self.render_header()
        self.refresh_rows(keep=True)
        self.notify("Пересканировано: %d путей" % len(self.entries))

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_quit(self) -> None:
        self.dump_screen()
        self.exit()


def main() -> None:
    if len(sys.argv) > 1:
        # CLI-режимы остались на чистом stdlib
        ca.main()
        return
    install_terminal_guard()
    AtlasApp().run()


# --------------------------------------------------------------------------- #
#  Страховка терминала
# --------------------------------------------------------------------------- #

# Последовательности, которыми Textual включает режимы терминала. Если
# приложение умрёт нештатно (SIGTERM, SIGKILL, исключение), терминал
# останется в альт-экране со скрытым курсором и выключенным переносом
# строк — «пустой терминал», из которого не выйти.
RESTORE_TERMINAL = (
    # сначала выключаем всё, что включал Textual
    "\x1b[?1000l\x1b[?1003l\x1b[?1015l\x1b[?1006l"
    "\x1b[?1000l\x1b[?1003l\x1b[?1015l\x1b[?1006l"
    "\x1b[?1004l"      # focus-reporting
    "\x1b[?2004l"      # bracketed paste
    "\x1b[?1016l"      # mouse-pixels
    "\x1b[?2026l"      # synchronized output
    "\x1b[<u"          # kitty-протокол
    # потом возвращаем терминал в обычный режим
    "\x1b[?7h"         # перенос строк
    "\x1b[?25h"        # показать курсор
    "\x1b[?1049l"      # выйти из альт-экрана
)


def install_terminal_guard() -> None:
    """Восстановить терминал при любом выходе, даже аварийном.

    Textual перенаправляет sys.stdout/sys.stderr в свои буферы, поэтому
    писать через них бесполезно — нужен исходный файловый дескриптор
    терминала. Запоминаем его при старте, до запуска приложения.
    """
    import atexit
    import signal

    # исходный дескриптор терминала (Textual перенаправит stdout/stderr)
    try:
        tty_fd = os.dup(2)
    except OSError:
        tty_fd = None

    def _restore(*_: object) -> None:
        data = RESTORE_TERMINAL.encode("utf-8")
        for fd in (tty_fd, 1, 2):
            if fd is None or fd < 0:
                continue
            try:
                os.write(fd, data)
                return
            except OSError:
                continue

    def _handler(signum, frame):
        _restore()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass

    atexit.register(_restore)


if __name__ == "__main__":
    main()
