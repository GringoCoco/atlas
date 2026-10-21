# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2"]
# ///
"""Проверка MCP-сервера config-atlas через настоящий MCP-клиент."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(("  ok  " if cond else "  FAIL") + "  " + name +
          (("  — " + extra) if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


async def main() -> None:
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "atlas_mcp.py")
    uv = os.path.expanduser("~/.local/bin/uv")
    if not os.path.exists(uv):
        uv = "uv"
    params = StdioServerParameters(
        command=uv,
        args=["run", "--quiet", "--script", script],
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print("сервер: %s %s\n" % (init.server_info.name,
                                       init.server_info.version))

            tools = {t.name for t in (await s.list_tools()).tools}
            for name in ("find_configs", "read_config", "explain_config",
                         "grep_configs", "list_env", "list_chains",
                         "map_overview"):
                check("инструмент %s" % name, name in tools)

            res = (await s.list_resources()).resources
            check("ресурс atlas://categories",
                  any(str(x.uri) == "atlas://categories" for x in res))

            async def call(tool, args):
                out = await s.call_tool(tool, args)
                return json.loads(out.content[0].text)

            ov = await call("map_overview", {})
            check("map_overview вернул пути", ov["total_paths"] > 100,
                  str(ov.get("total_paths")))
            check("map_overview вернул цепочки", ov["chains"] > 10)

            fc = await call("find_configs", {"query": "proxy"})
            check("find_configs нашёл прокси", fc["found"] > 0,
                  str(fc.get("found")))
            check("в результатах есть пути",
                  all("path" in r for r in fc["results"]))

            ex = await call("explain_config", {"name": "zsh"})
            check("explain_config нашёл цепочку zsh", len(ex["chains"]) == 1)
            roles = [c["role"] for c in ex["chains"][0]["candidates"]]
            check("в цепочке есть winner", "winner" in roles, str(roles))
            check("в цепочке есть перекрытые", "shadow" in roles, str(roles))

            env = await call("list_env", {"query": "NVM"})
            names = [v["name"] for v in env["variables"]]
            check("list_env нашёл NVM_DIR", "NVM_DIR" in names, str(names))
            check("list_env различает источники",
                  any(v["source"] == "file" for v in env["variables"]) and
                  any(v["source"] == "process" for v in env["variables"]))

            # секреты должны быть замаскированы: ищем любой токен в .zshenv
            # и проверяем что его значение не утекает в ответ
            raw = ""
            token_var = ""
            zshenv_path = os.path.join(os.path.expanduser("~"), ".zshenv")
            if os.path.exists(zshenv_path):
                with open(zshenv_path) as fh:
                    for ln in fh:
                        if "TOKEN=" in ln and not ln.strip().startswith("#"):
                            token_var = ln.split("=", 1)[0].strip()
                            raw = ln.split("=", 1)[1].strip().strip('"').strip("'")
                            break
            if token_var:
                secret = await call("grep_configs", {"query": token_var})
                joined = " ".join(r["text"] for r in secret["results"])
                check("grep нашёл токен-переменную", secret["matches"] > 0,
                      str(secret.get("matches")))
                check("grep замаскировал значение токена",
                      bool(raw) and raw not in joined,
                      "утечка значения" if raw else "токен не найден в .zshenv")
                check("grep показал маску", "••" in joined, joined[:120])
            else:
                print("  skip  маскировка токена — нет TOKEN= в ~/.zshenv")

            # чтение файла с секретом
            home = os.path.expanduser("~")
            zshenv = os.path.join(home, ".zshenv")
            if os.path.exists(zshenv):
                rc = await call("read_config", {"path": zshenv})
                check("read_config прочитал файл", "content" in rc)
                check("read_config замаскировал секреты",
                      rc.get("masked") is True and
                      "••" in rc.get("content", ""),
                      rc.get("content", "")[:120])

    print("\n" + "=" * 46)
    if FAILS:
        print("ПРОВАЛЕНО %d: %s" % (len(FAILS), ", ".join(FAILS)))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ MCP ПРОЙДЕНЫ")


asyncio.run(main())
