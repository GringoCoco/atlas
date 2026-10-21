#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2"]
# ///
"""
Config Atlas — MCP-сервер.

Отдаёт агентам (Claude Code, opencode, любым другим) знание о том, где
на этой машине лежат конфиги, какой из них реально применяется и где заданы
переменные окружения.

Транспорт: stdio. Запуск:

    uv run --script atlas_mcp.py

Подключение к Claude Code:
    claude mcp add config-atlas -- uv run --script ~/Projects/config-atlas/atlas_mcp.py

К opencode — в ~/.config/opencode/opencode.jsonc:
    "mcp": {"servers": {"config-atlas": {
        "type": "local",
        "command": ["uv", "run", "--script", "/path/to/atlas_mcp.py"],
        "enabled": true}}}

Инструменты:
    find_configs   — найти конфиги по названию/пути/описанию
    read_config    — прочитать конфиг (секреты маскируются)
    explain_config — какой файл из цепочки применяется и почему
    grep_configs   — поиск по содержимому файлов
    list_env       — переменные окружения: из файлов и живые
    list_chains    — список цепочек приоритета
    map_overview   — общая карта: сколько чего и где
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_atlas as ca  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402

server = MCPServer(name="config-atlas")

# Карта строится один раз при старте — полный скан занимает ~0.05 с.
_ENTRIES: list[ca.Entry] | None = None


def entries() -> list[ca.Entry]:
    global _ENTRIES
    if _ENTRIES is None:
        _ENTRIES = ca.build_map()
    return _ENTRIES


def _env_source() -> dict[str, str]:
    """Окружение для раздела переменных.

    MCP-сервер запускает агент, у которого окружение может быть урезанным,
    поэтому берём переменные из login-shell — это то же, что получит
    новый терминал. Если shell недоступен — падаем на os.environ.
    """
    env = ca.login_shell_env()
    if env:
        return env
    return dict(os.environ)


def _mask(text: str) -> str:
    return "\n".join(ca.mask_secrets(text.split("\n")))


def _short(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path


@server.tool(
    name="find_configs",
    title="Найти конфиги",
    description=(
        "Ищет конфиги на этой машине по названию, пути или описанию. "
        "Возвращает список кандидатов с путём, категорией и тем, существует "
        "ли файл. Используй, когда нужно понять, «где лежит конфиг для X». "
        "Поиск нечёткий: «прокси» найдёт и PROXY, и proxy."
    ),
)
def find_configs(
    query: str,
    category: str = "",
    include_missing: bool = False,
    limit: int = 30,
) -> dict:
    """Найти конфиги по запросу."""
    pool = entries()
    if category:
        pool = [e for e in pool if e.category == category]
    if not include_missing:
        pool = [e for e in pool if e.exists]
    found = ca.search(pool, query) if query.strip() else pool
    items = []
    for e in found[:max(1, limit)]:
        items.append({
            "path": e.path,
            "app": e.app,
            "category": ca.CAT_TITLE.get(e.category, e.category),
            "note": e.note,
            "exists": e.exists,
            "is_symlink": e.is_link,
            "size": e.size,
            "modified": e.mtime_str(),
            "chain": e.chain_title or None,
            "chain_role": e.chain_role or None,
        })
    return {
        "query": query,
        "found": len(found),
        "shown": len(items),
        "results": items,
    }


@server.tool(
    name="read_config",
    title="Прочитать конфиг",
    description=(
        "Читает содержимое конфигурационного файла. По умолчанию секреты "
        "(токены, пароли, ключи) маскируются — увидишь «••••••» вместо "
        "значения. Параметр reveal_secrets нужен редко и только если "
        "пользователь явно попросил."
    ),
)
def read_config(
    path: str,
    reveal_secrets: bool = False,
    max_lines: int = 400,
) -> dict:
    """Прочитать файл конфига по абсолютному пути."""
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        p = os.path.join(os.path.expanduser("~"), p)
    if not os.path.exists(p):
        return {"path": p, "error": "файл не найден"}
    if os.path.isdir(p):
        try:
            names = sorted(os.listdir(p))
        except OSError as exc:
            return {"path": p, "error": str(exc)}
        return {"path": p, "is_directory": True, "entries": names[:500]}
    lines, is_bin = ca.read_preview(p)
    if is_bin:
        return {"path": p, "error": "двоичный файл"}
    truncated = len(lines) > max_lines
    lines = lines[:max_lines]
    text = "\n".join(lines)
    if not reveal_secrets:
        text = _mask(text)
    return {
        "path": p,
        "lines": len(lines),
        "truncated": truncated,
        "masked": not reveal_secrets,
        "content": text,
    }


@server.tool(
    name="explain_config",
    title="Кой файл применяется",
    description=(
        "Объясняет, какой из нескольких конфигов реально применяется. "
        "Возвращает цепочку кандидатов с ролями: winner (применяется), "
        "shadow (перекрыт) и absent (файла нет), плюс уровень каждого. "
        "Используй, когда настройка «не работает» — почти всегда причина "
        "в том, что правится не тот файл."
    ),
)
def explain_config(name: str = "") -> dict:
    """Разобрать цепочку приоритета по имени (например «git», «zsh»)."""
    q = name.strip().lower()
    rows = ca.chain_rows(entries())
    chains = []
    for chain in ca.CHAIN_GROUPS:
        if q and q not in chain.id.lower() and q not in chain.title.lower():
            continue
        items = []
        for e, _role in rows:
            if e.chain != chain.id:
                continue
            items.append({
                "path": e.path,
                "level": e.chain_level,
                "role": e.chain_role,
                "role_text": ca.CHAIN_ROLE_LABEL.get(e.chain_role, ""),
                "exists": e.exists,
            })
        if not items:
            continue
        chains.append({
            "id": chain.id,
            "title": chain.title,
            "note": chain.note,
            "candidates": items,
        })
    if not chains:
        return {"query": name, "error": "цепочка не найдена",
                "available": [c.id for c in ca.CHAIN_GROUPS]}
    return {"query": name, "chains": chains}


@server.tool(
    name="grep_configs",
    title="Поиск по содержимому",
    description=(
        "Ищет текст внутри файлов конфигурации. Возвращает совпадения с "
        "номером строки. Используй, когда нужно найти, где именно "
        "прописано значение (например «где задаётся токен»)."
    ),
)
def grep_configs(query: str, limit: int = 50) -> dict:
    """Поиск по содержимому конфигов."""
    if not query.strip():
        return {"error": "пустой запрос"}
    hits = ca.grep_entries(entries(), query, limit=limit)
    out = []
    for e, lineno, text in hits:
        out.append({
            "path": e.path,
            "line": lineno,
            "app": e.app,
            "text": ca.mask_secrets([text])[0][:300],
        })
    return {"query": query, "matches": len(hits), "results": out}


@server.tool(
    name="list_env",
    title="Переменные окружения",
    description=(
        "Показывает переменные окружения и, главное, ГДЕ они заданы: "
        "в каком файле и на какой строке. Отдельным источником идут "
        "переменные, которых нет ни в одном конфиге — они заданы системой "
        "или родительским процессом. Секреты маскируются."
    ),
)
def list_env(query: str = "", include_process: bool = True) -> dict:
    """Индекс переменных окружения."""
    idx = ca.build_env_index_with_shell(entries(),
                                        include_process=include_process)
    if query.strip():
        q = query.lower()
        idx = [v for v in idx
               if q in v.name.lower() or q in v.value.lower()]
    out = []
    for v in idx:
        out.append({
            "name": v.name,
            "value": ca.mask_value(v.name, v.value) if v.value else "",
            "source": "file" if v.origin == "file" else "process",
            "file": _short(v.entry.path) if v.entry else None,
            "line": v.lineno or None,
            "note": v.note or None,
        })
    from_files = sum(1 for v in idx if v.origin == "file")
    return {
        "total": len(out),
        "from_config_files": from_files,
        "from_process_only": len(out) - from_files,
        "variables": out,
    }


@server.tool(
    name="list_chains",
    title="Цепочки приоритета",
    description=(
        "Список всех цепочек приоритета: какие настройки конфликтуют между "
        "собой и в каком порядке читаются. Без аргумента — только имена, "
        "чтобы выбрать нужную цепочку для explain_config."
    ),
)
def list_chains() -> dict:
    """Список цепочек приоритета."""
    return {
        "count": len(ca.CHAIN_GROUPS),
        "chains": [
            {"id": c.id, "title": c.title, "note": c.note,
             "category": ca.CAT_TITLE.get(c.category, c.category)}
            for c in ca.CHAIN_GROUPS
        ],
    }


@server.tool(
    name="map_overview",
    title="Общая карта",
    description=(
        "Сводка по всей карте конфигов: сколько путей известно, сколько "
        "реально лежит на диске, сколько цепочек приоритета и переменных "
        "окружения. Быстрый вход в задачу, когда непонятно, с чего начать."
    ),
)
def map_overview() -> dict:
    """Сводка по карте."""
    ents = entries()
    exist = sum(1 for e in ents if e.exists)
    by_cat: dict[str, int] = {}
    for e in ents:
        if e.exists:
            by_cat[ca.CAT_TITLE.get(e.category, e.category)] = \
                by_cat.get(ca.CAT_TITLE.get(e.category, e.category), 0) + 1
    return {
        "total_paths": len(ents),
        "existing": exist,
        "chains": len(ca.CHAIN_GROUPS),
        "env_vars": len(ca.build_env_index(ents)),
        "by_category": dict(sorted(by_cat.items(), key=lambda x: -x[1])),
    }


@server.tool(
    name="get_dev_context",
    title="Контекст разработчика",
    description=(
        "Компактный снимок среды разработчика: git user/email/signing, "
        "shell, editor, версии node/python/go/rust/ruby, SSH-ключи, "
        "проблемы PATH и конфликты переменных окружения. "
        "Вызывай один раз вместо десятка read_config + list_env — "
        "экономит токены и даёт полную картину за один запрос."
    ),
)
def get_dev_context() -> dict:
    """Контекст разработчика одним запросом."""
    ctx = ca.get_dev_context()
    return {
        "git": {
            "user": ctx.git_user,
            "email": ctx.git_email,
            "signing": ctx.git_signing,
            "signing_key": ctx.git_signing_key,
        },
        "shell": ctx.shell,
        "editor": ctx.editor,
        "runtimes": {
            "node": {"version": ctx.node_version, "manager": ctx.node_manager},
            "python": {"version": ctx.python_version, "path": ctx.python_path},
            "go": {"version": ctx.go_version},
            "ruby": {"version": ctx.ruby_version},
            "rust": {"version": ctx.rust_version},
        },
        "ssh_keys": ctx.ssh_keys,
        "path_issues": ctx.path_issues,
        "env_conflicts": ctx.env_conflicts,
        "summary": ca.dev_context_text(ctx),
    }


@server.tool(
    name="list_packages",
    title="Установленные пакеты",
    description=(
        "Список установленных пакетов по менеджерам: brew, npm (global), "
        "pip, uv tools, cargo, nvm (Node versions), go binaries. "
        "manager='' — все менеджеры сразу. Используй вместо запуска "
        "brew list / npm list / pip list — быстрее и не тратит токены на "
        "парсинг вывода в агенте."
    ),
)
def list_packages(
    manager: str = "",
    query: str = "",
) -> dict:
    """Список пакетов по менеджерам.

    manager: "brew" | "npm" | "pip" | "uv" | "cargo" | "nvm" | "go" | ""
    query:   фильтр по имени пакета (регистронезависимый)
    """
    managers = [manager] if manager else None
    pkgs = ca.scan_packages(managers)
    ql = query.lower()
    result = {}
    for mgr, items in pkgs.items():
        filtered = [
            {"name": p.name, "version": p.version,
             **({"extra": p.extra} if p.extra else {})}
            for p in items
            if not ql or ql in p.name.lower()
        ]
        if filtered:
            result[mgr] = filtered
    return {
        "managers": list(result.keys()),
        "total": sum(len(v) for v in result.values()),
        "packages": result,
    }


@server.tool(
    name="trace_env_var",
    title="Трассировка переменной окружения",
    description=(
        "Показывает ВСЕ места где задана переменная окружения: "
        "в каком файле конфига, на какой строке и с каким значением. "
        "Незаменимо когда непонятно откуда берётся PATH, JAVA_HOME, NODE_ENV "
        "и почему IDE видит одно значение, а терминал другое."
    ),
)
def trace_env_var(name: str) -> dict:
    """Трассировка: откуда берётся переменная name."""
    tr = ca.trace_env_var(name.upper())
    sources = []
    for s in tr.sources:
        sources.append({
            "file":   _short(s["file"]),
            "line":   s["line"],
            "value":  _mask(s["raw"]) if s["raw"] else "",
            "origin": s["origin"],
        })
    return {
        "name":          tr.name,
        "current_value": _mask(tr.process_value),
        "sources_count": len(sources),
        "sources":       sources,
    }


@server.tool(
    name="diff_env",
    title="Расхождение IDE vs терминал",
    description=(
        "Сравнивает os.environ текущего процесса (IDE/агент) с окружением "
        "нового терминала (login shell). Показывает переменные, которые "
        "расходятся — причина большинства «у меня не воспроизводится» багов."
    ),
)
def diff_env() -> dict:
    """Расхождение текущего процесса и login shell."""
    diffs = ca.diff_env()
    result = {"total": len(diffs), "conflicts": [], "only_process": [], "only_shell": []}
    for d in diffs:
        item = {
            "name":          d.name,
            "process_value": _mask(d.process_val),
            "shell_value":   _mask(d.shell_val),
        }
        result[d.status + ("s" if not d.status.endswith("s") else "")].append(item)  # type: ignore[index]
    # проще переделать:
    conflicts, only_p, only_s = [], [], []
    for d in diffs:
        item = {"name": d.name,
                "process": _mask(d.process_val),
                "shell":   _mask(d.shell_val)}
        if d.status == "conflict":
            conflicts.append(item)
        elif d.status == "only_process":
            only_p.append(item)
        else:
            only_s.append(item)
    return {
        "total":        len(diffs),
        "conflicts":    conflicts,
        "only_process": only_p,
        "only_shell":   only_s,
        "summary": ("Расхождений нет" if not diffs else
                    "%d конфликтов, %d только в IDE, %d только в shell"
                    % (len(conflicts), len(only_p), len(only_s))),
    }


@server.tool(
    name="git_audit",
    title="Git email по репозиториям",
    description=(
        "Проверяет каждый git-репозиторий в ~/Projects и ~: "
        "какой user.name/email будет у следующего коммита — "
        "глобальный или локальный. Выявляет репо где нет локального конфига "
        "и коммиты уйдут с личным email вместо рабочего (и наоборот)."
    ),
)
def git_audit(
    search_dirs: str = "",
) -> dict:
    """Аудит git-репозиториев.

    search_dirs: пути через запятую, пусто = ~/Projects и ~
    """
    dirs = [d.strip() for d in search_dirs.split(",") if d.strip()] or None
    repos = ca.git_audit(dirs)
    global_email = repos[0].global_email if repos else ""
    items = []
    for r in repos:
        items.append({
            "path":          _short(r.path),
            "effective_email": r.effective_email,
            "effective_name":  r.effective_name,
            "local_config":  r.has_local_config,
            "uses_global":   not r.has_local_config,
            "unsigned":      r.unsigned,
        })
    problems = [i for i in items if i["unsigned"] or
                (i["effective_email"] != global_email and not i["local_config"])]
    return {
        "global_email":   global_email,
        "repos_total":    len(items),
        "with_local":     sum(1 for i in items if i["local_config"]),
        "problems_count": len(problems),
        "repos":          items,
    }


@server.tool(
    name="ssh_audit",
    title="Аудит SSH",
    description=(
        "Полный аудит SSH: парсит ~/.ssh/config, проверяет существование "
        "каждого ключа, наличие в ssh-agent, ForwardAgent-риски. "
        "Показывает ключи не привязанные ни к одному Host. "
        "Используй вместо ручного ssh -vT git@github.com."
    ),
)
def ssh_audit_tool() -> dict:
    """Аудит SSH конфигурации."""
    sa = ca.ssh_audit()
    hosts = []
    for h in sa.hosts:
        hosts.append({
            "host":           h.name,
            "hostname":       h.hostname,
            "user":           h.user,
            "identity_file":  _short(h.identity_file) if h.identity_file else "",
            "key_exists":     h.key_exists,
            "key_in_agent":   h.key_in_agent,
            "port":           h.port,
            "forward_agent":  h.forward_agent,
        })
    return {
        "hosts_count":    len(hosts),
        "agent_keys":     sa.agent_keys,
        "issues_count":   len(sa.known_issues),
        "issues":         sa.known_issues,
        "hosts":          hosts,
    }


@server.tool(
    name="find_stale_refs",
    title="Захардкоженные пути к версиям",
    description=(
        "Находит конфиги со ссылками на конкретные версии пакетов: "
        "/opt/homebrew/Cellar/python@3.11/3.11.2/, node/v18.12.0/ и т.п. "
        "Такие пути ломаются после brew upgrade или обновления Node. "
        "Показывает файл, строку и тип проблемы."
    ),
)
def find_stale_refs_tool() -> dict:
    """Конфиги с захардкоженными путями к версиям."""
    stale = ca.find_stale_refs()
    files: dict[str, list] = {}
    for s in stale:
        p = _short(s.entry.path)
        files.setdefault(p, []).append({
            "line":   s.line,
            "text":   s.raw_line,
            "reason": s.reason,
        })
    return {
        "total_refs":  len(stale),
        "files_count": len(files),
        "files":       [{"path": p, "refs": refs} for p, refs in files.items()],
    }


@server.tool(
    name="find_orphans",
    title="Конфиги удалённых приложений",
    description=(
        "Находит конфиги приложений, которых уже нет в системе: "
        "не установлено через brew, нет в /Applications, нет CLI-бинаря. "
        "Безопасно показать что можно удалить при переезде на новый Mac."
    ),
)
def find_orphans_tool() -> dict:
    """Конфиги приложений которых нет в системе."""
    orphans = ca.find_orphans()
    return {
        "count": len(orphans),
        "orphans": [
            {"app": o.app_name,
             "path": _short(o.entry.path),
             "reason": o.reason}
            for o in orphans
        ],
    }


@server.tool(
    name="scan_secret_leaks",
    title="Секреты в git-tracked файлах",
    description=(
        "Сканирует конфиги на наличие токенов, паролей, API-ключей "
        "и проверяет — отслеживается ли файл git'ом. "
        "ВНИМАНИЕ: файл с секретом в git = возможная утечка в историю. "
        "Все значения в ответе замаскированы."
    ),
)
def scan_secret_leaks_tool() -> dict:
    """Файлы с секретами, потенциально попавшие в git."""
    leaks = ca.scan_secret_leaks()
    in_git = [l for l in leaks if l.in_git]
    files: dict[str, dict] = {}
    for lk in leaks:
        p = _short(lk.entry.path)
        if p not in files:
            files[p] = {"path": p, "in_git": lk.in_git,
                        "git_repo": _short(lk.git_repo) if lk.git_repo else "",
                        "lines": []}
        files[p]["lines"].append({"line": lk.line, "text": lk.raw_line})
    return {
        "total_matches": len(leaks),
        "in_git_count":  len(in_git),
        "severity":      "HIGH" if in_git else ("MEDIUM" if leaks else "OK"),
        "files":         list(files.values()),
    }


@server.tool(
    name="generate_export",
    title="Генерация setup.sh",
    description=(
        "Генерирует скрипт воспроизведения текущей среды разработчика: "
        "git config, brew install, npm install -g, uv tool install, cargo install, "
        "nvm install. Используй при переезде на новый Mac или онбординге. "
        "format: 'sh' (bash-скрипт) | 'brew' (Brewfile) | 'all' (оба)."
    ),
)
def generate_export_tool(
    format: str = "sh",
) -> dict:
    """Сгенерировать скрипт воспроизведения среды."""
    script = ca.generate_export(format)
    return {
        "format":       format,
        "lines_count":  len(script.splitlines()),
        "script":       script,
    }


@server.resource(
    "atlas://categories",
    name="Категории конфигов",
    description="Список категорий и сколько файлов в каждой.",
)
def categories_resource() -> str:
    ents = entries()
    counts: dict[str, int] = {}
    for e in ents:
        if e.exists:
            title = ca.CAT_TITLE.get(e.category, e.category)
            counts[title] = counts.get(title, 0) + 1
    return json.dumps(
        [{"category": k, "files": v} for k, v in
         sorted(counts.items(), key=lambda x: -x[1])],
        ensure_ascii=False, indent=2)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
