# ATLAS

You open a new terminal and have no idea where `PATH` comes from, why git is
signing commits with the wrong email, or which of your five `.npmrc` files has
the proxy configured.

ATLAS answers those questions. It scans macOS, builds a map of every config
file it can find, and shows it in a terminal UI with search and file preview.
Read-only — it never changes anything.

```
358 paths · 223 on disk · 22 priority chains · env vars: 47

  ● ~/.gitconfig                    Git (global)
  ● ~/.config/gh/config.yml         GitHub CLI
  ● ~/.ssh/config                   SSH
  ● ~/.zshrc                        zsh — main profile
  ● ~/.npmrc                        npm / proxy
  ...

  ╭──────────────────────────────────────────────────╮
  │ ❯                                                │
  ╰──────────────────────────────────────────────────╯
```

## Requirements

- macOS
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)

Install `uv` if you don't have it:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Installation

Clone the repo anywhere you like:

```sh
git clone https://github.com/GringoCoco/atlas ~/atlas
```

Add an alias to your `~/.zshrc` (or `~/.bashrc`):

```sh
alias atlas='uv run --quiet --script ~/atlas/atlas_tui.py'
```

Reload your shell:

```sh
source ~/.zshrc
```

That's it:

```sh
atlas
```

## Usage

```sh
atlas                   # interactive TUI
atlas --list            # plain text list — pipe to grep/less
atlas --chains          # priority chains: which file actually wins
atlas --env             # env vars and where each one is defined
atlas --grep proxy      # search file contents
atlas --json            # dump the full map as JSON
```

### Navigation

| Key | Action |
|---|---|
| `↑` `↓` / `PgUp` `PgDn` | move |
| `Enter` | open file preview |
| `Tab` / `Shift-Tab` | switch mode |
| `Esc` | clear query / filters |
| `Ctrl+Y` | copy path to clipboard |
| `Ctrl+O` | open in `$EDITOR` |
| `Ctrl+F` | reveal in Finder |
| `Ctrl+R` | rescan |
| `/` | command palette |
| `F1` | help |
| `Ctrl+C` | quit |

In the preview panel: `c` — copy path, `o` — open in editor, `f` — Finder,
`m` — toggle secrets, `Esc` — close.

### Modes (Tab)

| Mode | Shows |
|---|---|
| **All configs** | full list with search |
| **Priority** | which file wins, which is shadowed |
| **Environment** | where each env var is defined — file and line number |
| **Packages** | installed packages per manager (brew, npm, pip…) |
| **Grep** | full-text search inside config files |

### Diagnostics (`/`)

Type `/` to open the command palette:

| Command | What it does |
|---|---|
| `/trace PATH` | shows every file that sets a variable, with line numbers and values |
| `/diff` | compares IDE environment vs a fresh terminal — finds discrepancies |
| `/gitaudit` | shows which email each git repo will use for the next commit |
| `/sshcheck` | audits SSH keys: exist on disk, loaded into agent, config issues |
| `/stale` | finds hardcoded version paths like `python@3.11/3.11.2/` |
| `/orphan` | config files for apps that are no longer installed |
| `/scan` | files containing tokens or passwords that are tracked by git |
| `/export` | generates a `setup.sh` to reproduce your environment on a new Mac |

### Categories

`/ai` `/git` `/github` `/ssh` `/net` `/shell` `/node` `/py` `/docker` `/ide` `/macos` `/apps`

### Environment variables

The **Environment** mode shows each variable and **where** it is defined:

```
PATH   defined 9 times — last one wins
  ~/.profile:2     "$PATH:~/.docker/bin"
  ~/.zshrc:115     ~/.opencode/bin:$PATH
NVM_BIN
  ⚙ process only   ~/.nvm/versions/node/v22.0.0/bin
```

`⚙ process only` means the variable exists in the current environment but
isn't set in any config file — likely injected by your IDE, launchd, or a
parent process.

## MCP server

ATLAS ships an MCP server that connects to any AI assistant supporting the
[Model Context Protocol](https://modelcontextprotocol.io/). Once connected,
the assistant knows your full config map and can answer questions like
"where is the proxy configured?" or "why isn't `.nvmrc` being picked up?"

### Tools

| Tool | What it does |
|---|---|
| `find_configs` | find configs by name, path, or description |
| `read_config` | read a file (secrets masked by default) |
| `explain_config` | which file in a priority chain actually applies and why |
| `grep_configs` | full-text search with line numbers |
| `list_env` | env vars and where they are defined |
| `list_chains` | all priority chains |
| `map_overview` | summary: total paths, chains, variables |
| `trace_env_var` | full trace of an env var across all config files |
| `diff_env` | diff between IDE environment and a fresh terminal |
| `git_audit` | email and name that each git repo will use |
| `ssh_audit` | SSH key audit |
| `find_stale_refs` | hardcoded version paths in configs |
| `find_orphans` | config files for removed apps |
| `scan_secret_leaks` | secrets in git-tracked files |
| `generate_export` | script to reproduce your dev environment |

### Connecting

The MCP server runs as a separate process and communicates over stdin/stdout —
the standard transport for local MCP servers.

**Claude (via CLI):**

```sh
claude mcp add atlas -- uv run --quiet --script ~/atlas/atlas_mcp.py
```

**opencode** — add to `~/.config/opencode/opencode.jsonc`:

```jsonc
"mcp": {
  "servers": {
    "atlas": {
      "type": "local",
      "command": ["uv", "run", "--quiet", "--script",
                  "~/atlas/atlas_mcp.py"],
      "enabled": true
    }
  }
}
```

**Other clients** (Cursor, Zed, any MCP-compatible tool) — set the command to:

```
uv run --quiet --script ~/atlas/atlas_mcp.py
```

### Why env vars are read from a login shell

When an AI assistant runs the MCP server, the process starts with a stripped
environment — many variables are missing. ATLAS explicitly runs
`zsh -l -i -c env` to get the same environment a new terminal would have.
The result is cached for 2 minutes.

## Symbols

| Symbol | Meaning |
|---|---|
| `●` | file exists |
| `○` | file does not exist |
| `▸` | directory |
| `→` | symlink |
| `✓` | file is active (wins the priority chain) |
| `✗` | file is shadowed by another |
| `↩` | same file already shown above |

## Security

Secrets in the preview are hidden by default. Masked: values under keys like
`token`, `secret`, `password`, `api_key`; long base64/hex strings; `user:password`
pairs in URLs. Use `/secrets` or press `m` in the preview to reveal them.

The MCP server masks secrets too — real values are never sent to the assistant
unless you explicitly pass `reveal_secrets=true`.

## Structure

```
atlas_tui.py       TUI (Textual)
atlas_mcp.py       MCP server
config_atlas.py    data layer, search, diagnostics (stdlib only — no deps)
examples/          usage examples as a library
tools/             tests and dev utilities
```

The data layer `config_atlas.py` has no third-party dependencies and can be
imported directly:

```python
import config_atlas as ca

entries = ca.build_map()
hits = ca.search(entries, "proxy")
```

## License

MIT
