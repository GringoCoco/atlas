#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Config Atlas — карта конфигов на твоём Mac.

Показывает, где физически лежит каждый конфиг: opencode, git, GitHub CLI, SSH,
сеть/VPN, shell, npm/pnpm/yarn, python, docker, редакторы, launchd и прочее.

Только чтение — приложение ничего не меняет на диске.

Это модуль с данными и CLI. Интерактивный интерфейс — в atlas_tui.py.

    python3 config_atlas.py --list     # текстовый список в терминал
    python3 config_atlas.py --json     # выгрузка карты в JSON
    python3 config_atlas.py --chains   # приоритет конфигов
    python3 config_atlas.py --env      # переменные окружения
    python3 config_atlas.py --grep q   # поиск по содержимому
"""

from __future__ import annotations

import json
import locale
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict

# --------------------------------------------------------------------------- #
#  Категории
# --------------------------------------------------------------------------- #

CATEGORIES: list[tuple[str, str]] = [
    ("ai", "AI / Ассистенты"),
    ("git", "Git"),
    ("github", "GitHub / Токены"),
    ("ssh", "SSH"),
    ("net", "Сеть / VPN / Прокси"),
    ("shell", "Shell / Терминал"),
    ("node", "Node / JS / Пакеты"),
    ("py", "Python"),
    ("docker", "Docker / Контейнеры"),
    ("ide", "Редакторы / IDE"),
    ("macos", "macOS / Система"),
    ("apps", "Приложения (данные)"),
    ("misc", "Разное"),
]

CAT_TITLE = dict(CATEGORIES)

# --------------------------------------------------------------------------- #
#  Курируемый каталог: (категория, приложение, путь, что это)
# --------------------------------------------------------------------------- #

CATALOG: list[tuple[str, str, str, str]] = [
    # ---------------- AI / Ассистенты ----------------
    ("ai", "opencode", "~/.config/opencode/opencode.jsonc",
     "Главный конфиг opencode: тема, модель, плагины, MCP-серверы, агент. "
     "В проекте — ./opencode.json (перекрывает глобальный)"),
    ("ai", "opencode", "~/.config/opencode/cli.json", "Настройки CLI opencode (телеметрия, auth)"),
    ("ai", "opencode", "~/.config/opencode/tui.json", "Настройки TUI opencode"),
    ("ai", "opencode", "~/.config/opencode/service.json", "Фоновый сервис opencode"),
    ("ai", "opencode", "~/.config/opencode/plugins", "Установленные плагины opencode"),
    ("ai", "opencode", "~/.config/opencode/lsp-install-decisions.json",
     "Решения по автоустановке LSP-серверов"),
    ("ai", "opencode", "~/.config/opencode/opencode-cmux.json", "Интеграция opencode ↔ cmux"),
    ("ai", "opencode", "~/.opencode", "Старая (legacy) директория opencode — можно удалять"),
    ("ai", "Claude Code", "~/.claude/settings.json", "Глобальные настройки Claude Code"),
    ("ai", "Claude Code", "~/.claude", "Вся папка Claude Code: settings, agents, commands, skills"),
    ("ai", "Claude Code", "~/.claude.json", "Состояние Claude Code: история проектов, MCP, счётчики"),
    ("ai", "Claude Desktop", "~/Library/Application Support/Claude/config.json",
     "MCP-серверы и настройки Claude Desktop"),
    ("ai", "Claude Desktop", "~/Library/Preferences/com.anthropic.claudefordesktop.plist",
     "Prefs Claude Desktop (macOS)"),
    ("ai", "Codex CLI", "~/.codex/config.toml", "Конфиг OpenAI Codex CLI"),
    ("ai", "Codex CLI", "~/.codex/auth.json", "Токены авторизации Codex CLI"),
    ("ai", "Codex CLI", "~/.codex", "Вся папка Codex: сессии, логи, промпты"),
    ("ai", "CodexBar", "~/.config/codexbar", "Конфиг CodexBar"),
    ("ai", "Cursor", "~/.cursor/mcp.json", "MCP-серверы Cursor"),
    ("ai", "Cursor", "~/Library/Application Support/Cursor/User/settings.json",
     "Настройки Cursor (VS Code-формат)"),
    ("ai", "Cursor", "~/.cursor", "Расширения, правила и история Cursor"),
    ("ai", "Gemini CLI", "~/.gemini/settings.json", "Настройки Gemini CLI"),
    ("ai", "Gemini CLI", "~/.gemini/GEMINI.md", "Глобальный системный промпт Gemini"),
    ("ai", "Windsurf", "~/.codeium/windsurf/mcp_config.json", "MCP-серверы Windsurf"),
    ("ai", "Windsurf", "~/Library/Application Support/Windsurf/User/settings.json",
     "Настройки Windsurf"),
    ("ai", "Trae", "~/.trae/mcp.json", "MCP-серверы Trae"),
    ("ai", "Trae", "~/.trae", "Плагины и правила Trae"),
    ("ai", "Zed", "~/.config/zed/settings.json", "Настройки редактора Zed"),
    ("ai", "Zed", "~/.config/zed/keymap.json", "Раскладка клавиш Zed"),
    ("ai", "Antigravity", "~/.antigravity", "Конфиг Antigravity"),
    ("ai", "Devin", "~/.config/devin", "Конфиг Devin"),
    ("ai", "omo", "~/.omo", "Конфиг omo (codegraph, rules, telemetry)"),
    ("ai", "cmux", "~/.config/cmux", "Конфиг cmux"),
    ("ai", "cmux", "~/.cmuxterm", "Данные cmux-терминала"),
    ("ai", "cagent", "~/.config/cagent", "Конфиг cagent"),
    ("ai", "Codeium", "~/.codeium", "Настройки Codeium / language server"),
    ("ai", "GigaCode", "~/.gigacode", "Конфиг GigaCode"),
    ("ai", "GigaCode", "~/.gigacode-cron", "Cron-задачи GigaCode"),

    # ---------------- Git ----------------
    ("git", "Git", "~/.gitconfig", "Глобальный конфиг Git: user, alias, pull.rebase, core.editor"),
    ("git", "Git", "~/.config/git/config", "Git-конфиг по XDG (приоритетнее ~/.gitconfig)"),
    ("git", "Git", "~/.config/git/ignore", "Глобальный gitignore по XDG"),
    ("git", "Git", "~/.config/git/attributes", "Глобальные gitattributes по XDG"),
    ("git", "Git", "~/.gitignore_global", "Старый глобальный gitignore"),
    ("git", "Git", "~/.gitattributes_global", "Старые глобальные gitattributes"),
    ("git", "Git", "~/.config/configstore/git-config.json", "Кэш конфигов от npm-пакетов"),
    ("git", "Git", "~/.config/configstore/update-notifier-github.json",
     "Уведомления npm об обновлении пакета github"),
    ("git", "Git", "~/.git-credentials", "Файл с credentials (плохо хранить, но бывает)"),
    ("git", "Git", "~/.config/configstore/update-notifier-node-gyp.json",
     "Уведомления npm об обновлении node-gyp"),

    # ---------------- GitHub / токены ----------------
    ("github", "GitHub CLI", "~/.config/gh/hosts.yml",
     "Аккаунты GitHub CLI: токены, API-хосты (gh auth login пишет сюда)"),
    ("github", "GitHub CLI", "~/.config/gh/config.yml",
     "Настройки gh: git_protocol, editor, pager, промпты"),
    ("github", "GitHub CLI", "~/.config/gh/extensions.yml", "Установленные расширения gh"),
    ("github", "GitHub CLI", "~/.local/state/gh/state.yml", "Состояние gh (выбор репозитория)"),
    ("github", "GitHub", "~/.netrc", "Credentials для curl/git по http (логин-токен)"),
    ("github", "GitHub", "~/.config/gh", "Вся папка GitHub CLI"),
    ("github", "GitHub Desktop", "~/Library/Application Support/GitHub Desktop",
     "Данные GitHub Desktop"),
    ("github", "VS Code", "~/Library/Application Support/Code/User/settings.json",
     "Settings.json VS Code: токены, прокси, форматтеры"),

    # ---------------- SSH ----------------
    ("ssh", "OpenSSH", "~/.ssh/config", "Хосты, ключи, jump-hosts, прокси SSH"),
    ("ssh", "OpenSSH", "~/.ssh/known_hosts", "Известные хосты и их ключи"),
    ("ssh", "OpenSSH", "~/.ssh/authorized_keys", "Ключи, которым разрешён вход"),
    ("ssh", "OpenSSH", "~/.ssh/id_ed25519", "Ed25519-ключ (приватный!)"),
    ("ssh", "OpenSSH", "~/.ssh/id_ed25519.pub", "Ed25519-ключ (публичный)"),
    ("ssh", "OpenSSH", "~/.ssh/id_rsa", "RSA-ключ (приватный!)"),
    ("ssh", "OpenSSH", "~/.ssh/id_rsa.pub", "RSA-ключ (публичный)"),
    ("ssh", "OpenSSH", "~/.ssh/agent", "Состояние ssh-agent"),
    ("ssh", "OpenSSH", "~/.ssh/config.d", "Сниппеты ssh-конфига (если Include задан)"),
    ("ssh", "OpenSSH", "~/.ssh/id_ed25519", "Ed25519-ключ (приватный, современный стандарт)"),
    ("ssh", "OpenSSH", "~/.ssh/id_ed25519.pub", "Ed25519-ключ (публичный)"),

    # ---------------- Сеть / VPN / прокси ----------------
    ("net", "Cisco AnyConnect", "~/.anyconnect", "Профили и логи Cisco AnyConnect (VPN)"),
    ("net", "Cisco AnyConnect", "~/.cisco", "Кэш профилей Cisco"),
    ("net", "Система", "/etc/hosts", "Локальные DNS-override и блокировки"),
    ("net", "Система", "/etc/resolver", "Кастомные DNS-резолверы (split DNS)"),
    ("net", "Система", "/Library/Preferences/SystemConfiguration",
     "Системные настройки сети/Wi-Fi/прокси (read-only)"),
    ("net", "Система", "/etc/ppp", "PPP-конфигурация (VPN-протоколы)"),
    ("net", "npm", "~/.npmrc",
     "Реестр npm, токены (_authToken), прокси — часто лежит здесь"),
    ("net", "yarn", "~/.yarnrc.yml", "npmRegistryServer, токены, прокси"),
    ("net", "yarn", "~/.config/yarn/config.yml", "yarn-конфиг по XDG"),
    ("net", "pnpm", "~/.npmrc", "registry и токены pnpm (берёт из npmrc)"),
    ("net", "bun", "~/.bunfig.toml", "Реестр и токены bun"),
    ("net", "bun", "~/.bun", "Установка bun и его конфиги"),
    ("net", "pip", "~/.config/pip/pip.conf", "Индекс pip и прокси"),
    ("net", "pip", "~/.pip/pip.conf", "pip-конфиг в старом месте"),
    ("net", "uv", "~/.config/uv/uv.toml", "Зеркала и настройки uv"),
    ("net", "curl", "~/.curlrc", "Прокси, ретраи, TLS-опции curl"),
    ("net", "wget", "~/.wgetrc", "Прокси и настройки wget"),
    ("net", "Docker", "~/.docker/config.json", "Логины в docker registry, прокси"),
    ("net", "Docker", "~/.docker/contexts", "Docker contexts (удалённые кластеры)"),
    ("net", "Clash/Mihomo", "~/.config/clash", "Конфиг Clash / Mihomo (прокси)"),
    ("net", "Clash/Mihomo", "~/.config/mihomo", "Конфиг Mihomo"),
    ("net", "sing-box", "~/.config/sing-box", "Конфиг sing-box"),
    ("net", "Surge", "~/Library/Application Support/Surge", "Профили Surge"),
    ("net", "WireGuard", "~/Library/Application Support/wireguard", "Конфиги WireGuard"),
    ("net", "Tailscale", "~/Library/Preferences/com.tailscale.ipn.plist", "Состояние Tailscale"),
    ("net", "Cloudflare", "~/.cloudflared/config.yml", "Туннели cloudflared"),
    ("net", "ngrok", "~/.config/ngrok/ngrok.yml", "Туннели ngrok"),
    ("net", "env", "~/.zshenv", "Экспорт переменных окружения (PATH, прокси) — читается всеми шеллами"),
    ("net", "env", "~/.profile", "PATH и переменные окружения для login-shell"),
    ("net", "env", "~/.config/environment.d", "systemd-style env файлы (если есть)"),
    ("net", "macOS", "/Library/Preferences/com.apple.networkextension.plist",
     "Системные сетевые расширения macOS: VPN, DNS-прокси, фильтры"),
    ("net", "macOS", "~/Library/Preferences/com.apple.networkextension.plist",
     "Пользовательские сетевые расширения macOS (VPN-профили)"),
    ("net", "macOS", "/etc/auto_master", "Автомонтирование сетевых дисков (autofs)"),
    ("net", "macOS", "/etc/nfs.conf", "NFS: сетевые шары"),
    ("net", "macOS", "/etc/resolv.conf",
     "Системный DNS (на macOS генерируется автоматически)"),
    ("net", "ZeroTier", "~/Library/Application Support/ZeroTier", "Данные ZeroTier"),

    # ---------------- Shell / терминал ----------------
    ("shell", "zsh", "~/.zshrc", "Основной конфиг zsh: алиасы, PATH, промпт, плагины"),
    ("shell", "zsh", "~/.zshenv", "zshenv — читается всеми zsh-сессиями"),
    ("shell", "zsh", "~/.zprofile", "Логин-шелл zsh (PATH, PATH-экспорт)"),
    ("shell", "zsh", "~/.zlogin", "Логин-шелл zsh (после .zprofile)"),
    ("shell", "zsh", "~/.zlogout", "Выход из логин-шелла"),
    ("shell", "bash", "~/.bashrc", "Основной конфиг bash"),
    ("shell", "bash", "~/.bash_profile", "Логин-шелл bash"),
    ("shell", "bash", "~/.bash_logout", "Выход из логин-шелла"),
    ("shell", "Система", "/etc/zshenv", "Системный zshenv (macOS)"),
    ("shell", "Система", "/etc/zprofile", "Системный профиль zsh"),
    ("shell", "Система", "/etc/bashrc", "Системный bashrc"),
    ("shell", "Система", "/etc/paths", "Системные пути PATH"),
    ("shell", "Система", "/etc/paths.d", "Дополнительные PATH-фрагменты"),
    ("shell", "Fish", "~/.config/fish/config.fish", "Конфиг fish"),
    ("shell", "Fish", "~/.config/fish/conf.d", "Фрагменты конфига fish"),
    ("shell", "Oh My Zsh", "~/.oh-my-zsh", "Тема, плагины и кастомные плагины oh-my-zsh"),
    ("shell", "Starship", "~/.config/starship.toml", "Промпт-движок Starship"),
    ("shell", "Tmux", "~/.tmux.conf", "Конфиг tmux"),
    ("shell", "tmux", "~/.config/tmux/tmux.conf", "Конфиг tmux по XDG"),
    ("shell", "Kitty", "~/.config/kitty/kitty.conf", "Конфиг терминала Kitty"),
    ("shell", "Kitty", "~/.config/kitty", "Вся папка Kitty (темы, шрифты)"),
    ("shell", "Alacritty", "~/.config/alacritty/alacritty.toml", "Конфиг Alacritty"),
    ("shell", "WezTerm", "~/.config/wezterm/wezterm.lua", "Конфиг WezTerm"),
    ("shell", "Ghostty", "~/.config/ghostty/config", "Конфиг Ghostty"),
    ("shell", "iTerm2", "~/Library/Application Support/com.googlecode.iterm2",
     "Профили и настройки iTerm2"),
    ("shell", "iTerm2", "~/Library/Preferences/com.googlecode.iterm2.plist", "Prefs iTerm2"),
    ("shell", "direnv", "~/.config/direnv/direnv.toml", "Конфиг direnv"),
    ("shell", "Readline", "~/.inputrc", "Настройки Readline (bash/zsh)"),
    ("shell", "zsh", "~/.zcompdump", "Кэш автодополнения zsh (пересоздаётся)"),
    ("shell", "zsh", "~/.local/bin/env.fish", "Рыба-обёртка для PATH-менеджеров"),

    # ---------------- Node / JS ----------------
    ("node", "npm", "~/.npmrc", "Реестр, токены, прокси npm"),
    ("node", "npm", "~/.npm", "Глобальные пакеты npm и кэш (_cacache)"),
    ("node", "nvm", "~/.nvm", "Установленные версии Node и alias (default)"),
    ("node", "nvm", "~/.nvm/alias/default", "Alias версии Node по умолчанию"),
    ("node", "yarn", "~/.yarnrc.yml", "Yarn Berry: реестр, nodeLinker, токены"),
    ("node", "yarn", "~/.yarn", "Кэш и PnP Yarn"),
    ("node", "bun", "~/.bunfig.toml", "Конфиг bun"),
    ("node", "pnpm", "~/.pnpmrc", "pnpm-конфиг"),
    ("node", "pnpm", "~/.config/pnpm/rc", "pnpm-конфиг по XDG"),
    ("node", "Volta", "~/.volta", "Установленные toolchains Volta"),
    ("node", "node-gyp", "~/.node-gyp", "Кэш сборок node-gyp"),
    ("node", "corepack", "~/.cache/node/corepack", "Кэш corepack (Corepack-версии)"),

    # ---------------- Python ----------------
    ("py", "uv", "~/.config/uv/uv.toml", "Конфиг uv: зеркала, cache-dir"),
    ("py", "uv", "~/.config/uv/python-version", "Версия Python по умолчанию для uv"),
    ("py", "uv", "~/.cache/uv", "Кэш пакетов uv"),
    ("py", "pip", "~/.config/pip/pip.conf", "pip-конфиг по XDG"),
    ("py", "pip", "~/.pip/pip.conf", "pip-конфиг (legacy)"),
    ("py", "pydistutils", "~/.pydistutils.cfg", "pydistutils.cfg"),
    ("py", "Python", "~/.pythonrc", "Автозагрузка скриптов в интерактивном Python"),
    ("py", "pyenv", "~/.pyenv", "Установленные версии Python"),
    ("py", "conda", "~/.conda", "conda: окружения и конфиг"),
    ("py", "Poetry", "~/.config/pypoetry/config.toml", "Poetry: реестр, токены, настройки"),
    ("py", "Poetry", "~/.config/pypoetry/auth.toml", "Poetry: токены (registry)"),
    ("py", "Poetry", "~/.cache/pypoetry", "Кэш Poetry"),
    ("py", "HuggingFace", "~/.cache/huggingface/token", "Токен HuggingFace"),
    ("py", "Kaggle", "~/.kaggle/kaggle.json", "API-ключи Kaggle"),
    ("py", "Jupyter", "~/.jupyter/jupyter_config.py", "Конфиг Jupyter"),
    ("py", "Jupyter", "~/.ipython/profile_default", "Профиль IPython (алиасы, автозагрузка)"),
    ("py", "AWS", "~/.aws/credentials", "AWS-ключи (секретно!)"),
    ("py", "AWS", "~/.aws/config", "AWS-профили и регионы"),

    # ---------------- Docker ----------------
    ("docker", "Docker", "~/.docker/config.json", "Авторизация в registry + прокси"),
    ("docker", "Docker", "~/.docker/contexts", "Docker contexts"),
    ("docker", "Docker Desktop", "~/Library/Group Containers/group.com.docker/settings.json",
     "Настройки Docker Desktop"),
    ("docker", "Docker Desktop", "~/Library/Containers/com.docker.docker/Data",
     "Данные Docker Desktop (диски, образы)"),
    ("docker", "Colima", "~/.colima", "Конфиг Colima (VM для Docker)"),
    ("docker", "OrbStack", "~/.orbstack", "Конфиг OrbStack"),
    ("docker", "OrbStack", "~/Library/Group Containers/xyz.orbstack.OrbStack",
     "Данные OrbStack"),
    ("docker", "Podman", "~/.config/containers", "Конфиг podman (containers.conf)"),
    ("docker", "Rancher", "~/.rancher", "Конфиг Rancher Desktop"),
    ("docker", "Kubernetes", "~/.kube/config", "kubeconfig: кластеры, контексты, юзеры"),
    ("docker", "Minikube", "~/.minikube", "Локальные кластеры minikube"),

    # ---------------- IDE / редакторы ----------------
    ("ide", "VS Code", "~/Library/Application Support/Code/User/settings.json",
     "Settings.json VS Code"),
    ("ide", "VS Code", "~/Library/Application Support/Code/User/keybindings.json",
     "Горячие клавиши VS Code"),
    ("ide", "VS Code", "~/Library/Application Support/Code/User/snippets",
     "Пользовательские сниппеты VS Code"),
    ("ide", "VS Code", "~/Library/Application Support/Code/User/tasks.json",
     "Задачи VS Code"),
    ("ide", "VS Code", "~/Library/Application Support/Code/User/globalStorage",
     "Расширенные настройки расширений VS Code"),
    ("ide", "VS Code", "~/Library/Application Support/Code/User/profiles",
     "Профили VS Code"),
    ("ide", "VS Code", "~/Library/Application Support/Code/User/workspaceStorage",
     "Состояние рабочих областей"),
    ("ide", "VS Code", "~/.vscode", "Расширения и настройки CLI (code-server)"),
    ("ide", "Cursor", "~/Library/Application Support/Cursor/User/settings.json",
     "Settings.json Cursor"),
    ("ide", "Cursor", "~/Library/Application Support/Cursor/User/keybindings.json",
     "Горячие клавиши Cursor"),
    ("ide", "Windsurf", "~/Library/Application Support/Windsurf/User/settings.json",
     "Settings.json Windsurf"),
    ("ide", "JetBrains", "~/Library/Application Support/JetBrains",
     "Настройки всех IDE JetBrains (options/ внутри)"),
    ("ide", "Vim", "~/.vimrc", "Конфиг vim"),
    ("ide", "Vim", "~/.vim", "Плагины и темы vim"),
    ("ide", "Neovim", "~/.config/nvim", "Конфиг Neovim"),
    ("ide", "Neovim", "~/.vim", "Legacy-конфиг Neovim"),
    ("ide", "Arduino", "~/.arduinoIDE/arduino-cli.yaml", "Конфиг arduino-cli (board manager)"),
    ("ide", "Sublime", "~/Library/Application Support/Sublime Text/Packages/User/Preferences.sublime-settings",
     "Настройки Sublime Text"),
    ("ide", "Android", "~/.android", "Android SDK: ключи отладки, avd"),
    ("ide", "Expo", "~/.expo", "Конфиг Expo (EAS)"),

    # ---------------- macOS / система ----------------
    ("macos", "macOS", "~/Library/LaunchAgents", "Пользовательские launchd-агенты (автозапуск)"),
    ("macos", "macOS", "~/Library/Preferences", "plist-настройки всех приложений"),
    ("macos", "macOS", "~/Library/Application Support", "Данные и настройки приложений"),
    ("macos", "macOS", "~/Library/Containers", "Sandbox-контейнеры приложений"),
    ("macos", "macOS", "~/Library/Group Containers", "Общие контейнеры приложений"),
    ("macos", "macOS", "~/Library/Mobile Documents", "iCloud Drive"),
    ("macos", "macOS", "~/Library/Logs", "Логи приложений"),
    ("macos", "macOS", "~/Library/Caches", "Кэши (можно чистить)"),
    ("macos", "cron", "~/Library/LaunchAgents", "cron-подобные задачи macOS (launchd)"),
    ("macos", "AnyDesk", "~/.anydesk", "Настройки AnyDesk (удалённый доступ)"),
    ("macos", "macOS", "~/.Trash", "Корзина"),

    # ---------------- Приложения (данные) ----------------
    ("apps", "Brave", "~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Preferences",
     "Настройки Brave"),
    ("apps", "Chrome", "~/Library/Application Support/Google/Chrome/Default/Preferences",
     "Настройки Chrome"),
    ("apps", "Arc", "~/Library/Application Support/Arc/User Data/Default/Preferences",
     "Настройки Arc"),
    ("apps", "Docker Desktop", "~/Library/Application Support/Docker Desktop",
     "Данные Docker Desktop"),
    ("apps", "Spotify", "~/Library/Application Support/Spotify/Users",
     "Данные Spotify (prefs)"),
    ("apps", "Yandex", "~/.yandex", "Настройки Яндекс.Браузера / Диска"),
    ("apps", "Citrix", "~/Library/Application Support/Citrix", "Настройки Citrix"),
    ("apps", "1Password", "~/Library/Group Containers/2BUA8C4S2C.com.1password",
     "Данные 1Password"),
    ("apps", "Blizzard", "~/Library/Application Support/Blizzard", "Данные Battle.net"),
    ("apps", "Steam", "~/Library/Application Support/Steam", "Данные Steam"),
    ("apps", "Spotify", "~/Library/Preferences/com.spotify.client.plist", "Prefs Spotify"),
    ("apps", "JetBrains Toolbox", "~/Library/Application Support/JetBrains/Toolbox",
     "Toolbox JetBrains"),

    # ---------------- Разное ----------------
    ("misc", "Редактор", "~/.editorconfig", "Форматирование кода для всех редакторов"),
    ("misc", "Rust", "~/.cargo/config.toml", "cargo: зеркала, target-dir, linker"),
    ("misc", "Rust", "~/.rustup/settings.toml", "rustup: toolchain по умолчанию"),
    ("misc", "RubyGems", "~/.gem/credentials", "Токены RubyGems"),
    ("misc", "Maven", "~/.m2/settings.xml", "Maven: зеркала, серверы, токены"),
    ("misc", "Gradle", "~/.gradle/gradle.properties", "Gradle: прокси, токены"),
    ("misc", "Arduino", "~/.arduinoIDE", "Arduino IDE"),
    ("misc", "CodexBar", "~/.config/codexbar", "Конфиг CodexBar"),
    ("misc", "MCP", "~/.mcp-auth", "Авторизация MCP-серверов"),
    ("misc", "Zed", "~/.config/zed", "Вся папка Zed"),
    ("misc", "Antigravity", "~/Library/Application Support/Antigravity", "Данные Antigravity"),
    ("misc", "Obsidian", "~/Library/Application Support/obsidian", "Настройки Obsidian"),
    ("misc", "Spotify", "~/Library/Application Support/Spotify", "Данные Spotify"),
    ("misc", "bundle", "~/.bundle/config", "Bundler: зеркала и токены"),
    ("misc", "Flutter", "~/.flutter", "Flutter SDK и настройки"),
    ("misc", "Android Studio", "~/.AndroidStudio*", "Настройки Android Studio"),
    ("misc", "Keychain", "~/Library/Keychains", "Системные ключи (Keychain Access)"),
    ("misc", "Важное", "~/Library/Application Support/Code/User/settings.json",
     "Часто ищете здесь: GitHub-токен, прокси, форматтер"),
]

# --------------------------------------------------------------------------- #
#  Цепочки приоритета: какой конфиг реально применяется
#
#  Уровни идут от общего к частному. Внутри уровня работает правило
#  «первый существующий» (например, XDG-путь заменяет legacy-путь),
#  между уровнями — «последний существующий побеждает».
# --------------------------------------------------------------------------- #


@dataclass
class Chain:
    id: str
    title: str
    category: str
    levels: list[tuple[str, list[str]]]
    note: str = ""
    stack: tuple[str, ...] = ()   # уровни, где файлы читаются подряд


CHAIN_GROUPS: list[Chain] = [
    Chain("git", "Git", "git", [
        ("системный", ["/etc/gitconfig", "/opt/homebrew/etc/gitconfig"]),
        ("глобальный", ["~/.config/git/config", "~/.gitconfig"]),
        ("проектный", ["./.git/config"]),
    ], "Git читает системный → глобальный → локальный; значения перекрываются сверху вниз"),

    Chain("gitignore", "Git ignore", "git", [
        ("глобальный", ["~/.config/git/ignore", "~/.gitignore_global"]),
        ("проектный", ["./.gitignore"]),
    ], "gitignore читается сверху вниз, ближний к репозиторию побеждает"),

    Chain("opencode", "opencode", "ai", [
        ("глобальный", ["~/.config/opencode/opencode.jsonc"]),
        ("проектный", ["./opencode.json", "./opencode.jsonc"]),
    ], "Проектный opencode.json полностью перекрывает глобальный"),

    Chain("claude", "Claude Code", "ai", [
        ("глобальный", ["~/.claude/settings.json"]),
        ("проектный", ["./.claude/settings.json", "./.claude/settings.local.json"]),
    ], "Проектные настройки Claude Code дополняют глобальные"),

    Chain("npm", "npm", "node", [
        ("системный", ["/opt/homebrew/etc/npmrc", "/usr/local/etc/npmrc"]),
        ("глобальный", ["~/.npmrc"]),
        ("проектный", ["./.npmrc"]),
    ], "npmrc: системный → глобальный → проектный, каждый перекрывает предыдущий"),

    Chain("yarn", "Yarn", "node", [
        ("глобальный", ["~/.config/yarn/config.yml", "~/.yarnrc.yml"]),
        ("проектный", ["./.yarnrc.yml"]),
    ], "Yarn Berry: ~/.yarnrc.yml, в проекте — .yarnrc.yml"),

    Chain("pnpm", "pnpm", "node", [
        ("глобальный", ["~/.config/pnpm/rc", "~/.pnpmrc"]),
        ("проектный", ["./.npmrc"]),
    ], "pnpm берёт настройки из .npmrc"),

    Chain("pip", "pip", "py", [
        ("системный", ["/etc/pip.conf"]),
        ("глобальный", ["~/.config/pip/pip.conf", "~/.pip/pip.conf"]),
        ("проектный", ["./.pip/pip.conf"]),
    ], "pip: системный → пользовательский → проектный"),

    Chain("uv", "uv", "py", [
        ("глобальный", ["~/.config/uv/uv.toml"]),
        ("проектный", ["./uv.toml"]),
    ], "uv читает uv.toml из проекта поверх пользовательского"),

    Chain("zsh", "zsh", "shell", [
        ("системный", ["/etc/zshenv", "/etc/zprofile", "/etc/zshrc"]),
        ("пользователь", ["~/.zshenv", "~/.zprofile", "~/.zshrc", "~/.zlogin"]),
    ], "zsh читает файлы строго по порядку: zshenv → zprofile → zshrc → zlogin",
        stack=("системный", "пользователь")),

    Chain("bash", "bash", "shell", [
        ("системный", ["/etc/bashrc", "/etc/profile"]),
        ("пользователь", ["~/.bashrc", "~/.bash_profile"]),
    ], "bash: bashrc для интерактивных, bash_profile для login-shell"),

    Chain("ssh", "SSH", "ssh", [
        ("системный", ["/etc/ssh/ssh_config"]),
        ("пользователь", ["~/.ssh/config"]),
    ], "Пользовательский ~/.ssh/config читается первым и побеждает системный"),

    Chain("gh", "GitHub CLI", "github", [
        ("системный", ["/etc/gh/config.yml"]),
        ("глобальный", ["~/.config/gh/config.yml"]),
    ], "gh читает пользовательский config.yml"),

    Chain("docker", "Docker CLI", "docker", [
        ("системный", ["/etc/docker/config.json"]),
        ("глобальный", ["~/.docker/config.json"]),
        ("проектный", ["./.docker/config.json"]),
    ], "docker config.json — реестры, прокси, credential helpers"),

    Chain("compose", "Docker Compose", "docker", [
        ("проектный", ["./docker-compose.yml", "./docker-compose.yaml",
                       "./compose.yml", "./compose.yaml"]),
    ], "Compose читает compose.yaml в приоритете над docker-compose.yml"),

    Chain("vscode", "VS Code", "ide", [
        ("пользователь", ["~/Library/Application Support/Code/User/settings.json"]),
        ("рабочая папка", ["./.vscode/settings.json"]),
    ], "settings.json рабочей папки перекрывает пользовательский"),

    Chain("tmux", "tmux", "shell", [
        ("системный", ["/etc/tmux.conf"]),
        ("пользователь", ["~/.config/tmux/tmux.conf", "~/.tmux.conf"]),
    ], "tmux: пользовательский конфиг заменяет системный"),

    Chain("starship", "Starship", "shell", [
        ("глобальный", ["~/.config/starship.toml"]),
        ("проектный", ["./.starship.toml"]),
    ], "Starship: проектный .starship.toml поверх глобального"),

    Chain("kube", "Kubernetes", "docker", [
        ("глобальный", ["~/.kube/config"]),
    ], "kubeconfig; переопределяется переменной KUBECONFIG"),

    Chain("curl", "curl", "net", [
        ("глобальный", ["~/.curlrc"]),
    ], "curl читает .curlrc из домашней папки"),

    Chain("cargo", "Cargo", "misc", [
        ("глобальный", ["~/.cargo/config.toml"]),
        ("проектный", ["./.cargo/config.toml"]),
    ], "Cargo: проектный .cargo/config.toml поверх ~/.cargo/config.toml"),

    Chain("prettier", "Prettier", "node", [
        ("глобальный", ["~/.prettierrc"]),
        ("проектный", ["./.prettierrc", "./.prettierrc.json"]),
    ], "Prettier ищет конфиг от проекта вверх по дереву"),
]

CHAIN_ROLE_LABEL = {
    "winner": "ПРИМЕНЯЕТСЯ",
    "shadow": "перекрыт",
    "absent": "не найден",
}

# --------------------------------------------------------------------------- #
#  Модель
# --------------------------------------------------------------------------- #


@dataclass
class Entry:
    category: str
    app: str
    path: str
    note: str
    source: str = "curated"   # curated | auto
    exists: bool = False
    is_dir: bool = False
    size: int = 0
    mtime: float = 0.0
    real_path: str = ""
    alias: bool = False       # True — тот же путь, что и выше по списку
    is_link: bool = False
    link_target: str = ""
    relative: bool = False    # путь относительно текущей папки
    chain: str = ""           # id цепочки приоритета
    chain_title: str = ""     # короткое имя цепочки
    chain_level: str = ""     # уровень внутри цепочки
    chain_role: str = ""      # winner | shadow | absent

    def mtime_str(self) -> str:
        if not self.mtime:
            return "-"
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.mtime))


# --------------------------------------------------------------------------- #
#  Сканирование
# --------------------------------------------------------------------------- #

SKIP_TOP = {
    ".git", "node_modules", ".cache", ".Trash", "Applications", "Pictures",
    "Movies", "Music", "Documents", "Downloads", "Desktop", "Public",
    "Library", ".npm", ".nvm", ".oh-my-zsh", ".cargo", ".rustup", ".bun",
    ".vscode", ".docker", ".local", ".codeium", ".arduinoIDE", ".expo",
    ".kaggle", ".nvm", "site-packages", "__pycache__", ".gradle", ".m2",
    ".pub-cache", ".swiftpm", ".zcompdump*", ".DS_Store", ".ssh",
}

# Что внутри ~/.config считаем конфигом
CONF_EXT = {
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".plist", ".xml", ".properties", ".env", ".editorconfig", ".gitconfig",
}
CONF_NAMES = {
    "config", "settings", "credentials", "hosts", "rc", "config.toml",
    "settings.json", "config.json", "config.yaml", "config.yml",
    ".npmrc", ".gitconfig", ".netrc", "auth.json", "hosts.yml",
}

# Приложения, шум из которых пропускаем в Application Support
NOISY_APP_SUPPORT = {
    "com.apple.", "Code Helper", "Crashpad", "Caches", "Caches_",
}


def expand(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


def is_configish(name: str) -> bool:
    low = name.lower()
    if low in CONF_NAMES:
        return True
    ext = os.path.splitext(low)[1]
    if ext in CONF_EXT:
        return True
    if low.startswith(".env"):
        return True
    if low.endswith(".rc") and not low.endswith(".drc"):
        return True
    if low.startswith(".") and len(low) > 1 and ext == "":
        return True  # dotfile без расширения
    return False


def stat_entry(e: Entry) -> Entry:
    try:
        st = os.lstat(e.path)
        e.exists = True
        e.is_dir = os.path.isdir(e.path)
        e.size = st.st_size
        e.mtime = st.st_mtime
        e.real_path = os.path.realpath(e.path)
        if os.path.islink(e.path):
            e.is_link = True
            try:
                e.link_target = os.readlink(e.path)
            except OSError:
                e.link_target = ""
    except OSError:
        e.exists = False
    return e


# --- эвристика категории ---------------------------------------------------- #
# Проверяется по короткому «предмету» (имя папки/файла), а не по полному пути,
# чтобы ~/Library/Application Support/Code не улетал в macOS.

HINTS: list[tuple[tuple[str, ...], str]] = [
    (("github", "gh", "netrc"), "github"),
    (("opencode", "claude", "anthropic", "codex", "openai", "cursor", "gemini",
      "windsurf", "trae", "zed", "antigravity", "devin", "codeium", "gigacode",
      "cmux", "cagent", "omo", "atlas"), "ai"),
    (("git",), "git"),
    (("ssh", "id_rsa", "id_ed25519", "id_ecdsa", "known_hosts",
      "authorized_keys"), "ssh"),
    (("clash", "mihomo", "sing-box", "ngrok", "cloudflared", "anyconnect",
      "cisco", "wireguard", "tailscale", "surge", "hosts", "resolver",
      "npmrc", "pip.conf", "uv.toml", "curlrc", "wgetrc", "proxy", "registry",
      "configstore", "ngrok", "dns"), "net"),
    (("zsh", "bash", "fish", "tmux", "kitty", "alacritty", "wezterm",
      "ghostty", "iterm", "starship", "oh-my-zsh", "direnv", "inputrc",
      "zcompdump", "profile", "env.fish", "terminal"), "shell"),
    (("npm", "yarn", "pnpm", "bun", "node", "volta", "nvm", "corepack",
      "node-gyp"), "node"),
    (("pip", "uv", "poetry", "conda", "pyenv", "jupyter", "ipython",
      "huggingface", "python", "pydistutils"), "py"),
    (("docker", "colima", "orbstack", "podman", "rancher", "lima"), "docker"),
    (("code", "jetbrains", "intellij", "pycharm", "webstorm", "goland",
      "rubymine", "phpstorm", "clion", "rider", "datagrip", "vscode",
      "sublime", "nvim", "neovim", "vim", "arduino", "android", "expo",
      "flutter", "zed"), "ide"),
    (("launchagent", "launchdaemon"), "macos"),
    (("arc", "figma", "notion", "brave", "chrome", "spotify", "yandex",
      "citrix", "1password", "blizzard", "steam", "obsidian", "battle",
      "slack", "telegram", "discord", "postman", "raycast", "docker desktop"),
     "apps"),
    (("cargo", "rustup", "gem", "maven", "gradle", "bundle", "aws",
      "keychain", "mcp", "anydesk", "battlenet"), "misc"),
]


def guess_category(subject: str) -> str:
    low = subject.lower()
    for keys, cat in HINTS:
        for k in keys:
            if k in low:
                return cat
    return "misc"


def app_guess(path: str) -> str:
    parts = [p for p in path.split(os.sep) if p]
    interesting = [p for p in parts if not p.startswith(".")]
    if not interesting:
        interesting = parts
    return interesting[-1] if interesting else path


# --- курируемый слой -------------------------------------------------------- #


def curated_entries() -> list[Entry]:
    out: list[Entry] = []
    for cat, app, path, note in CATALOG:
        e = Entry(category=cat, app=app, path=expand(path), note=note,
                  source="curated")
        out.append(stat_entry(e))
    return out


# --- автопоиск -------------------------------------------------------------- #

# Мусор, который не является конфигом
NOISE_TOKENS = (
    "storablearchive", "statsig", "remotefeatureflags", "splunk-log",
    "font_cache", "window-state", "languagepack", "feedback-history",
    "crash_helper_state", "crash_markers", "browser_history",
    "closed-item-history", "extensions-blocklist", "ant-device-registry",
    "right_button_move", "rotatecfg", "smicfg", "btfs_client_config",
    "viewerlogging", "package-lock", "first_run", "managed-codex-accounts",
    "cursor-session", "codex-account-snapshots", "openai-dashboard",
    "cowork-", "git-worktrees", "install-state", "persisted-state",
    "desktop_state", "harmonia-", "notifications.json", "versions.json",
    "session-com", "usage-history", "state.json", "updaterid",
    "vm-support-probe", "dotnet", "diagnostics", "telemetry",
    "deviceinfocache", "autoupdate", "epicwebhelper", "epicgamesmodsdk",
    "avatar", "cacheindex",
)


def is_noise(name: str) -> bool:
    low = name.lower()
    return any(tok in low for tok in NOISE_TOKENS)

NOISE_DIRS = {"CrashReporter", ".system-cache", "Caches", "Code Cache",
              "GPUCache", "Crashpad", "DiagnosticReports"}


def scan_home(home: str) -> list[Entry]:
    found: list[Entry] = []
    seen: set[str] = set()

    def add(p: str, subject: str, note: str = "", force_cat: str | None = None,
            app: str | None = None) -> None:
        if p in seen:
            return
        try:
            st = os.lstat(p)
        except OSError:
            return
        if os.path.isfile(p) and st.st_size > 4 * 1024 * 1024:
            return
        seen.add(p)
        cat = force_cat or guess_category(subject)
        if cat == "misc" and force_cat is None:
            cat = "apps"       # непонятное — это данные приложения
        e = Entry(category=cat, app=app or app_guess(p), path=p, note=note,
                  source="auto")
        found.append(stat_entry(e))

    # 1. Дот-файлы в корне HOME
    try:
        for name in sorted(os.listdir(home)):
            if not name.startswith(".") or name in SKIP_TOP:
                continue
            p = os.path.join(home, name)
            if os.path.isdir(p) and not os.path.islink(p):
                continue
            if name in (".DS_Store", ".zcompdump", ".viminfo", ".lesshst",
                        ".CFUserTextEncoding", ".bash_history", ".zsh_history",
                        ".npmrc.lock", ".python_history", ".node_repl_history"):
                continue
            if not is_configish(name):
                continue
            add(p, name.lstrip("."), "Дот-файл в корне HOME")
    except OSError:
        pass

    # 2. ~/.config/<app>/** (глубина до 4)
    cfg_root = os.path.join(home, ".config")
    if os.path.isdir(cfg_root):
        for dirpath, dirnames, filenames in os.walk(cfg_root):
            rel = os.path.relpath(dirpath, cfg_root)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > 3:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if d not in ("node_modules", ".git", ".cache", "bin")]
            top = os.path.basename(dirpath) if rel != "." else ""
            for fn in filenames:
                if fn == ".DS_Store" or fn.startswith("."):
                    continue
                if is_noise(fn):
                    continue
                if not is_configish(fn):
                    continue
                add(os.path.join(dirpath, fn), top or fn,
                    "Найдено в ~/.config%s" % ("/" + top if top else ""),
                    app=top or None)

    # 3. ~/Library/Application Support/<App> — только верхний уровень
    as_root = os.path.join(home, "Library", "Application Support")
    if os.path.isdir(as_root):
        try:
            apps = sorted(os.listdir(as_root))
        except OSError:
            apps = []
        for app in apps:
            if app.startswith("com.apple.") or app in NOISE_DIRS or app.startswith("."):
                continue
            d = os.path.join(as_root, app)
            if not os.path.isdir(d):
                continue
            try:
                entries = sorted(os.listdir(d))
            except OSError:
                continue
            hits = 0
            for fn in entries:
                p = os.path.join(d, fn)
                if os.path.isdir(p) or fn.startswith(".") or fn == ".DS_Store":
                    continue
                if is_noise(fn):
                    continue
                if not (is_configish(fn) or fn.endswith(".plist")):
                    continue
                add(p, app, "Данные приложения %s" % app, app=app)
                hits += 1
                if hits >= 5:
                    break

    # 4. ~/Library/Preferences — plist'ы нормальных приложений
    BUNDLE_PREFIXES = ("com.", "am.", "net.", "org.", "io.", "dev.", "ru.",
                        "cn.", "co.", "me.", "xyz.", "app.", "com_", "group.")
    pref_root = os.path.join(home, "Library", "Preferences")
    if os.path.isdir(pref_root):
        try:
            names = sorted(os.listdir(pref_root))
        except OSError:
            names = []
        n = 0
        for fn in names:
            if not fn.endswith(".plist") or fn.startswith("."):
                continue
            bundle = fn[:-6]
            if not bundle.lower().startswith(BUNDLE_PREFIXES):
                continue          # системные агенты и служебные файлы
            if is_noise(fn):
                continue
            add(os.path.join(pref_root, fn), bundle,
                "Prefs приложения (macOS)", app=bundle)
            n += 1
            if n >= 45:
                break

    # 5. LaunchAgents
    for sub in ("LaunchAgents", "LaunchDaemons"):
        d = os.path.join(home, "Library", sub)
        if os.path.isdir(d):
            try:
                for fn in sorted(os.listdir(d)):
                    if fn.endswith(".plist"):
                        add(os.path.join(d, fn), sub, "launchd-%s" % sub,
                            force_cat="macos")
            except OSError:
                pass

    # 6. /etc — системные конфиги (точечно)
    for p, subj in (("/etc/hosts", "hosts"), ("/etc/resolver", "resolver"),
                    ("/etc/ssh/ssh_config", "ssh"), ("/etc/zshenv", "zshenv"),
                    ("/etc/zprofile", "zprofile"), ("/etc/bashrc", "bashrc"),
                    ("/etc/paths", "paths"), ("/etc/paths.d", "paths"),
                    ("/etc/ppp", "ppp"), ("/etc/sudoers", "sudoers"),
                    ("/etc/launchd.conf", "launchd"), ("/etc/apache2", "apache"),
                    ("/etc/nginx", "nginx"), ("/etc/ssh/sshd_config", "ssh")):
        if os.path.exists(p):
            add(p, subj, "Системный конфиг (/etc)")

    return found


# Путь, у которого «главная» категория задаётся явно (остальные — алиасы)
PRIMARY_OVERRIDE = {
    "~/.npmrc": "node",
    "~/.config/pip/pip.conf": "py",
    "~/.config/uv/uv.toml": "py",
    "~/.config/yarn/config.yml": "node",
    "~/.bun": "node",
    "~/.codeium": "ai",
}


def build_map(home: str | None = None) -> list[Entry]:
    home = home or os.path.expanduser("~")
    groups: dict[str, list[Entry]] = {}
    order: list[str] = []
    for e in curated_entries():
        if e.path not in groups:
            groups[e.path] = []
            order.append(e.path)
        groups[e.path].append(e)

    entries: list[Entry] = []
    primary_paths: set[str] = set()
    for path in order:
        group = groups[path]
        override = PRIMARY_OVERRIDE.get(path)
        primary = group[0]
        if override:
            for cand in group:
                if cand.category == override:
                    primary = cand
                    break
        # склеиваем описания, убирая дубли
        notes: list[str] = []
        for g in group:
            if g.note and g.note not in notes:
                notes.append(g.note)
        primary.note = " · ".join(notes)
        primary.alias = False
        entries.append(primary)
        primary_paths.add(path)
        for g in group:
            if g is primary:
                continue
            g.alias = True
            entries.append(g)

    for e in scan_home(home):
        if e.path in primary_paths:
            continue
        if e.real_path and e.real_path in primary_paths:
            continue
        entries.append(e)

    apply_chains(entries)
    return entries


# --------------------------------------------------------------------------- #
#  Цепочки приоритета
# --------------------------------------------------------------------------- #


def apply_chains(entries: list[Entry]) -> None:
    """Размечает записи ролью в цепочке приоритета (winner/shadow/absent)."""
    by_path: dict[str, Entry] = {}
    for e in entries:
        by_path.setdefault(e.path, e)

    for chain in CHAIN_GROUPS:
        winner: Entry | None = None
        # сверху вниз: последний уровень с существующим файлом побеждает
        for level_name, paths in chain.levels:
            level_hits: list[Entry] = []
            for p in paths:
                full = expand(p)
                ent = by_path.get(full)
                if ent is None:
                    ent = Entry(category=chain.category, app=chain.title,
                                path=full, note=chain.note, source="curated")
                    ent.relative = p.startswith("./")
                    ent = stat_entry(ent)
                    by_path[full] = ent
                    entries.append(ent)
                if ent.exists:
                    level_hits.append(ent)
                    if level_name not in chain.stack:
                        break       # альтернативы: подходит только первый
            if level_hits:
                winner = level_hits[-1]
        # размечаем все кандидаты цепочки
        for level_name, paths in chain.levels:
            for p in paths:
                full = expand(p)
                ent = by_path.get(full)
                if ent is None:
                    continue
                ent.chain = chain.id
                ent.chain_title = chain.title
                ent.chain_level = level_name
                if not ent.exists:
                    ent.chain_role = "absent"
                elif winner is not None and ent is winner:
                    ent.chain_role = "winner"
                else:
                    ent.chain_role = "shadow"


def chain_rows(entries: list[Entry]) -> list[tuple[Entry, str]]:
    """Строки для вида «Приоритет конфигов»: (запись, подпись роли)."""
    rows: list[tuple[Entry, str]] = []
    for chain in CHAIN_GROUPS:
        for level_name, paths in chain.levels:
            for p in paths:
                full = expand(p)
                for e in entries:
                    if e.path == full and e.chain == chain.id:
                        rows.append((e, CHAIN_ROLE_LABEL.get(e.chain_role, "")))
                        break
    return rows


# --------------------------------------------------------------------------- #
#  Индекс переменных окружения
# --------------------------------------------------------------------------- #

ENV_PATTERNS = [
    re.compile(r"^\s*export\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$"),
    re.compile(r"^\s*(?:set\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$"),
    re.compile(r"<key>([A-Z_][A-Z0-9_]*)</key>\s*<string>(.*?)</string>"),
    re.compile(r"<key>([A-Z_][A-Z0-9_]*)</key>\s*<string></string>"),
]

ENV_FILE_NAMES = {
    ".zshenv", ".zshrc", ".zprofile", ".zlogin", ".bashrc", ".bash_profile",
    ".profile", ".envrc", ".env", ".env.local", ".env.development",
    ".env.production", ".envrc.local",
}


def is_env_candidate(path: str) -> bool:
    base = os.path.basename(path)
    if base in ENV_FILE_NAMES:
        return True
    if base.startswith(".env"):
        return True
    if base.endswith(".env"):
        return True
    return False


@dataclass
class EnvVar:
    name: str
    entry: Entry | None      # None — переменная из живого окружения
    lineno: int
    value: str
    origin: str = "file"     # file | process
    note: str = ""           # «из окружения процесса» и т.п.


# Переменные, которые задаёт не конфиг, а сама система (launchd, Finder,
# Терминал, IDE). Их полезно видеть, но они не интересны как «где настроено».
SYSTEM_ENV_PREFIXES = (
    "LS_", "DISPLAY", "CFNETWORK", "COMMAND_MODE", "SECURITYSESSIONID",
    "SSH_AUTH_SOCK", "SSH_CONNECTION", "SSH_TTY", "SSH_CLIENT", "TERM_PROGRAM",
    "TERM_SESSION_ID", "XPC_", "__CF", "GPG_", "GNOME_", "DBUS_", "GTK_",
    "QT_", "LC_", "LANG", "TZ", "USER_", "SHLVL", "ZSH_", "PWD", "OLDPWD",
    "TMPDIR", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "HOSTNAME",
    "PS1", "PS2", "COLUMNS", "LINES", "EDITOR", "VISUAL", "PAGER",
)

# Переменные, которые почти всегда полезны иметь под рукой
INTERESTING_ENV = {
    "PATH", "HOME", "SHELL", "EDITOR", "JAVA_HOME", "GOROOT", "GOPATH",
    "NODE_PATH", "NVM_DIR", "NVM_BIN", "NPM_CONFIG_PREFIX", "PNPM_HOME",
    "BUN_INSTALL", "YARN_CACHE_FOLDER", "PYENV_ROOT", "PYENV_VERSION",
    "VIRTUAL_ENV", "CONDA_PREFIX", "RUBY_VERSION", "GEM_HOME", "ANDROID_HOME",
    "ANDROID_SDK_ROOT", "JAVA_TOOL_OPTIONS", "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH", "PKG_CONFIG_PATH", "MANPATH",
    "GOPROXY", "GOSUMDB", "CGO_ENABLED", "CC", "CXX", "MAKEFLAGS",
    "KUBECONFIG", "DOCKER_HOST", "DOCKER_CONFIG", "COMPOSE_FILE",
    "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "GITHUB_TOKEN",
    "GH_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
    "ANTHROPIC_BASE_URL", "OLLAMA_HOST", "HUGGINGFACE_HUB_CACHE",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
    "NPM_TOKEN", "NPM_CONFIG_REGISTRY", "NPM_CONFIG_USERCONFIG",
    "PYTHONPATH", "PYTHONSTARTUP", "PIP_INDEX_URL", "PIP_TRUSTED_HOST",
    "SSH_AUTH_SOCK", "GPG_TTY", "GIT_EDITOR", "GIT_PAGER", "GIT_SSH_COMMAND",
    "BROWSER", "CLICOLOR", "LANG", "LC_ALL",
}


def is_system_env(name: str) -> bool:
    """Задано ли переменное окружением процесса, а не конфигом."""
    if name in INTERESTING_ENV:
        return False
    return name.startswith(SYSTEM_ENV_PREFIXES) or name.startswith("_")


def live_env(env: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Живое окружение: имя → значение, только «интересные» переменные."""
    src = os.environ if env is None else env
    out = []
    for name, value in src.items():
        if not name or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            continue
        if is_system_env(name):
            continue
        out.append((name, value))
    out.sort()
    return out


_SHELL_ENV_CACHE: dict[str, str] | None = None

# Disk-cache для login_shell_env — избегает запуска login-shell при каждом
# старте MCP-сервера или повторном открытии TUI.
_SHELL_ENV_DISK_CACHE = os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "atlas_shell_env.json")
_SHELL_ENV_CACHE_TTL = 120   # секунд


def _load_shell_env_disk() -> dict[str, str] | None:
    """Загрузить кеш с диска, если он свежий."""
    try:
        st = os.stat(_SHELL_ENV_DISK_CACHE)
        if time.time() - st.st_mtime > _SHELL_ENV_CACHE_TTL:
            return None
        with open(_SHELL_ENV_DISK_CACHE) as fh:
            return json.load(fh)
    except Exception:
        return None


def _save_shell_env_disk(env: dict[str, str]) -> None:
    try:
        with open(_SHELL_ENV_DISK_CACHE, "w") as fh:
            json.dump(env, fh)
    except Exception:
        pass


def login_shell_env(shell: str | None = None,
                    timeout: float = 6.0,
                    use_cache: bool = True) -> dict[str, str]:
    """Окружение, которое получит НОВЫЙ терминал.

    Читается запуском login-shell — то есть ровно то, что получит
    пользователь, открыв новую вкладку. Результат кешируется в памяти
    и на диске (TTL=120 с) чтобы не тормозить повторные запуски.

    Возвращает пустой словарь, если shell недоступен или не отвечает.
    """
    global _SHELL_ENV_CACHE
    if use_cache and _SHELL_ENV_CACHE is not None:
        return _SHELL_ENV_CACHE
    if use_cache:
        disk = _load_shell_env_disk()
        if disk is not None:
            _SHELL_ENV_CACHE = disk
            return disk
    sh = shell or os.environ.get("SHELL") or "/bin/zsh"
    if not os.path.exists(sh):
        sh = "/bin/zsh"
    try:
        proc = subprocess.run(
            [sh, "-lc", "source ~/.zshrc 2>/dev/null; env"],
            capture_output=True, stdin=subprocess.DEVNULL,
            timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return {}
    out: dict[str, str] = {}
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            out[name] = value
    if use_cache:
        _SHELL_ENV_CACHE = out
        _save_shell_env_disk(out)
    return out


def build_env_index(entries: list[Entry],
                    include_process: bool = True) -> list[EnvVar]:
    """Индекс переменных окружения.

    Сначала — определения из файлов конфигурации, затем — живые переменные
    процесса, которых нет ни в одном конфиге (заданы системой, launchd,
    профилем IDE и т.п.).
    """
    out: list[EnvVar] = []
    seen: set[tuple[str, int, str]] = set()
    from_files: set[str] = set()
    for e in entries:
        if not e.exists or e.is_dir:
            continue
        if not (is_env_candidate(e.path) or
                "/LaunchAgents/" in e.path or e.path.endswith(".plist")):
            continue
        if e.size > 2 * 1024 * 1024:
            continue
        lines, is_bin = read_preview(e.path, limit=400_000)
        if is_bin:
            continue
        for i, ln in enumerate(lines, 1):
            for pat in ENV_PATTERNS:
                m = pat.match(ln)
                if not m:
                    continue
                name, value = m.group(1), (m.group(2) or "").strip()
                if len(name) < 2:
                    continue
                key = (name, i, e.path)
                if key in seen:
                    continue
                seen.add(key)
                from_files.add(name)
                out.append(EnvVar(name=name, entry=e, lineno=i, value=value,
                                  origin="file"))
                break
    if include_process:
        for name, value in live_env():
            if name in from_files:
                continue
            out.append(EnvVar(name=name, entry=None, lineno=0, value=value,
                              origin="process",
                              note="только в окружении процесса"))
    return out


def build_env_index_with_shell(entries: list[Entry],
                               include_process: bool = True) -> list[EnvVar]:
    """То же, но живые переменные берутся из login-shell."""
    if not include_process:
        return build_env_index(entries, include_process=False)
    out = build_env_index(entries, include_process=False)
    from_files = {v.name for v in out}
    shell_env = login_shell_env()
    source = shell_env if shell_env else dict(os.environ)
    for name, value in live_env(source):
        if name in from_files:
            continue
        out.append(EnvVar(name=name, entry=None, lineno=0, value=value,
                          origin="process",
                          note="только в окружении"))
    return out


# --------------------------------------------------------------------------- #
#  Поиск по содержимому (grep)
# --------------------------------------------------------------------------- #

GREP_MAX_FILE = 2 * 1024 * 1024
GREP_MAX_HITS = 800


def grep_entries(entries: list[Entry], query: str,
                 limit: int = GREP_MAX_HITS) -> list[tuple[Entry, int, str]]:
    if not query:
        return []
    needle = query.lower()
    hits: list[tuple[Entry, int, str]] = []
    for e in entries:
        if not e.exists or e.is_dir or e.size > GREP_MAX_FILE:
            continue
        if not is_configish(os.path.basename(e.path)) and \
                not e.path.endswith((".json", ".jsonc", ".yaml", ".yml",
                                     ".toml", ".plist", ".conf", ".ini",
                                     ".cfg", ".sh", ".bash", ".zsh", ".env")):
            continue
        try:
            with open(e.path, "rb") as fh:
                data = fh.read(GREP_MAX_FILE)
        except OSError:
            continue
        if b"\x00" in data[:2048]:
            continue
        text = data.decode("utf-8", errors="replace")
        for i, ln in enumerate(text.splitlines(), 1):
            if needle in ln.lower():
                hits.append((e, i, ln.strip()))
                if len(hits) >= limit:
                    return hits
    return hits


# --------------------------------------------------------------------------- #
#  Поиск — многоуровневое ранжирование
# --------------------------------------------------------------------------- #
#
#  Уровни (убывающий приоритет):
#    5000  exact match имени файла или app
#    4000  prefix имени файла
#    3000  подстрока в имени файла или app (exact)
#    2000  подстрока в пути (~/. часть)
#    1000  подстрока в теге / категории / note
#     500  fuzzy по всем полям
#    -1    не подходит
#
# --------------------------------------------------------------------------- #

SYNONYMS = {
    "proxy": "прокси", "proxies": "прокси",
    "network": "сеть", "net": "сеть",
    "token": "токен", "tokens": "токены",
    "secret": "секрет", "secrets": "секреты",
    "password": "пароль",
    "credentials": "креды",
    "settings": "настройки",
    "config": "конфиг", "conf": "конфиг", "configuration": "конфиг",
    "keychain": "кейчейн",
    "registry": "реестр",
    "mcp": "mcp",
    "zsh": "zsh", "bash": "bash", "fish": "fish", "shell": "shell",
    "git": "git", "github": "github",
    "ssh": "ssh", "ssl": "ssl", "tls": "tls",
    "npm": "npm", "node": "node", "yarn": "yarn", "pnpm": "pnpm",
    "pip": "pip", "python": "python", "pyenv": "pyenv",
    "docker": "docker", "k8s": "kubernetes", "kubectl": "kubernetes",
    "aws": "aws", "gcp": "gcloud", "azure": "azure",
}

# Обратные синонимы (ru → en) — для поиска по-русски
_RU_SYNONYMS = {v: k for k, v in SYNONYMS.items() if v != k}


def normalize(text: str) -> str:
    low = text.lower()
    for src, dst in SYNONYMS.items():
        if src in low:
            low = low.replace(src, dst)
    return low


def _path_tokens(path: str) -> list[str]:
    """Значимые части пути: имя файла, директории без ~/ и точек."""
    home = os.path.expanduser("~")
    p = path
    if p.startswith(home):
        p = p[len(home):]
    # разбиваем по /, ., -, _
    tokens = re.split(r"[/.\-_]", p.lower())
    return [t for t in tokens if len(t) > 1]


def search_score(query: str, entry: "Entry") -> float:
    """Вернуть числовой рейтинг релевантности (< 0 = не показывать)."""
    if not query:
        return 0.0

    q = normalize(query).lower()
    fname = os.path.basename(entry.path).lower()
    app   = (entry.app or "").lower()
    path  = entry.path.lower()
    note  = (entry.note or "").lower()
    cat   = CAT_TITLE.get(entry.category, "").lower()

    # 1. exact match имени файла или приложения
    if q == fname or q == app:
        return 5000.0

    # 2. prefix имени файла (без лидирующей точки)
    fname_base = fname.lstrip(".")
    if fname_base.startswith(q) or app.startswith(q):
        return 4000.0 - len(fname_base)

    # 3. подстрока в имени файла или app
    if q in fname or q in app:
        pos = min(fname.find(q) if q in fname else 9999,
                  app.find(q)   if q in app   else 9999)
        return 3000.0 - pos

    # 4. подстрока в path-токенах (~/. часть пути)
    tokens = _path_tokens(entry.path)
    for tok in tokens:
        if q == tok:
            return 2500.0
        if tok.startswith(q):
            return 2000.0
        if q in tok:
            return 1800.0 - len(tok)

    # 5. подстрока в категории / note
    if q in cat or q in note:
        return 1000.0

    # 6. fuzzy по всем полям
    haystack = " ".join([fname, app, path, note, cat] + tokens)
    return _fuzzy(q, haystack)


def _fuzzy(q: str, text: str) -> float:
    """Классический fuzzy: символы q должны встречаться в text по порядку."""
    if q in text:
        return 400.0 - text.index(q) * 0.5
    qi = 0
    score = 0.0
    last = -2
    for i, ch in enumerate(text):
        if qi < len(q) and ch == q[qi]:
            score += 12.0 if last == i - 1 else max(0.5, 4.0 - (i - last - 1) * 0.25)
            last = i
            qi += 1
    if qi < len(q) or score < 2.0:
        return -1.0
    return score


# Устаревший псевдоним — оставляем для совместимости
def fuzzy_score(query: str, text: str) -> float:
    return _fuzzy(query.lower(), text.lower())


def search(entries: list[Entry], query: str) -> list[Entry]:
    """Многоуровневый поиск: exact → prefix → substring → path-tokens → fuzzy."""
    if not query:
        return entries

    q = normalize(query)
    # Попробуем также оригинальный запрос (без нормализации) — для коротких
    q_raw = query.strip().lower()

    scored: list[tuple[float, Entry]] = []
    for e in entries:
        s = search_score(q, e)
        # если нормализация не помогла, пробуем raw
        if s < 0 and q_raw != q:
            s = search_score(q_raw, e)
        if s >= 0:
            scored.append((s, e))

    scored.sort(key=lambda x: (-x[0], x[1].alias, x[1].path))

    # один путь — одна строка (приоритет у основной записи, не у алиаса)
    out: list[Entry] = []
    used: set[str] = set()
    for _, e in scored:
        if e.path in used:
            continue
        used.add(e.path)
        out.append(e)
    return out


# --------------------------------------------------------------------------- #
#  Чтение файлов
# --------------------------------------------------------------------------- #

# ── Секреты в «key = value» ──────────────────────────────────────────────────
SECRET_RE = re.compile(
    r"(?i)([\"']?[a-z0-9_.\-]*(?:token|secret|password|passwd|api[_-]?key"
    r"|apikey|access[_-]?key|private[_-]?key|credential|auth)[\"']?"
    r"\s*[:=]\s*)"
    r"(?P<val>\"[^\"]*\"|'[^']*'|\$\{[^}]*\}|[^\s\"',;}]+)"
)

# ── Пароль в connection-string ─────────────────────────────────────────────
#   postgres://user:PASSWORD@host  redis://:PASSWORD@host  mysql://u:P@h/db
_CONNSTR_RE = re.compile(
    r"(?P<proto>[a-z][a-z0-9+\-.]*://)(?P<user>[^:@/\s]*):(?P<pass>[^@\s]{3,})@"
)

# ── Slack/webhook токен в URL ──────────────────────────────────────────────
#   https://hooks.slack.com/services/T.../B.../SECRET
#   https://discord.com/api/webhooks/ID/SECRET
_WEBHOOK_RE = re.compile(
    r"(?i)(?:hooks\.slack\.com/services/[A-Z0-9]{3,}/[A-Z0-9]{3,}/|"
    r"discord\.com/api/webhooks/\d+/|"
    r"hooks\.zapier\.com/hooks/catch/[^/]+/)(?P<tok>[A-Za-z0-9_\-]{8,})"
)

# ── Строки, которые выглядят как секреты, но ими не являются ──────────────
_COMMENT_LINE_RE = re.compile(r"^\s*(?:#|//|--|\*)")         # комментарий
_ENV_REF_RE      = re.compile(r"process\.env\.|os\.environ|getenv|\$\{?\w+\}?")
_EMPTY_VAL_RE    = re.compile(r"""[\"']?\s*[\"']?$""")       # пустое значение
_PLACEHOLDER_RE  = re.compile(                                # <placeholder> или YOUR_TOKEN
    r"(?i)(?:^|\b)(?:<[^>]{1,40}>|YOUR_[A-Z_]+|REPLACE_ME|CHANGEME|PLACEHOLDER"
    r"|XXXXXXXX+|INSERT_HERE|TODO|FIXME)(?:\b|$)"
)

BINARY_HINT = set(b"\x00\x01\x02")


def read_preview(path: str, limit: int = 400_000) -> tuple[list[str], bool]:
    """Возвращает (строки, is_binary)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(limit)
    except OSError as exc:
        return ["[не удалось прочитать: %s]" % exc], False
    if not data:
        return ["[пустой файл]"], False
    if any(b in data[:2048] for b in BINARY_HINT):
        return ["[двоичный файл]"], True
    text = data.decode("utf-8", errors="replace")
    return text.splitlines(), False


def _mask_match(m: re.Match) -> str:
    val = m.group("val")
    if val[:1] in ('"', "'"):
        return m.group(1) + val[0] + "••••••" + val[0]
    return m.group(1) + "••••••"


def _mask_connstr(m: re.Match) -> str:
    """postgres://user:••••••@host"""
    return m.group("proto") + m.group("user") + ":••••••@"


def _mask_webhook(m: re.Match) -> str:
    full = m.group(0)
    tok = m.group("tok")
    return full[: -len(tok)] + "••••••"


def _is_benign_secret_line(line: str, val_group: str) -> bool:
    """True если совпадение — не настоящий секрет."""
    stripped = val_group.strip().strip("\"'")
    if not stripped:
        return True
    if _PLACEHOLDER_RE.search(stripped):
        return True
    if _ENV_REF_RE.search(line):
        return True
    if len(stripped) < 4:
        return True
    return False


ASSIGN_RE = re.compile(
    r"^(\s*(?:export\s+|set\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*)(.*)$")


def mask_secrets(lines: list[str]) -> list[str]:
    """Маскирует секреты во всех строках файла.

    Покрывает:
    - key = value / key: value / export KEY=value
    - connection strings: postgres://user:pass@host
    - webhook URLs: hooks.slack.com/.../SECRET
    Пропускает комментарии, ссылки на env-переменные, плейсхолдеры.
    """
    out: list[str] = []
    for ln in lines:
        # пропускаем строки-комментарии целиком
        if _COMMENT_LINE_RE.match(ln):
            out.append(ln)
            continue

        masked = ln

        # connection strings (postgres://, mysql://, redis://, mongodb+srv://)
        masked = _CONNSTR_RE.sub(_mask_connstr, masked)

        # webhook URLs
        masked = _WEBHOOK_RE.sub(_mask_webhook, masked)

        # key = value / key: value — с проверкой на benign
        def _safe_mask(m: re.Match) -> str:
            if _is_benign_secret_line(ln, m.group("val")):
                return m.group(0)
            return _mask_match(m)

        masked = SECRET_RE.sub(_safe_mask, masked)

        # export FOO=... если значение похоже на секрет
        am = ASSIGN_RE.match(masked)
        if am:
            name = am.group(1).strip().rstrip("=").strip()
            val = am.group(2)
            new_val = mask_value(name, val)
            if new_val != val:
                masked = am.group(1) + new_val

        out.append(masked)
    return out


# --- маскирование отдельных значений (env-переменные) ---------------------- #

SECRET_NAME_RE = re.compile(
    r"(?i)(token|secret|passw|pass|cred|auth|key|licen|private|signature)")
# Длинная случайная строка без слов — почти наверняка токен/ключ
# Снижаем порог до 16 (GitHub PAT = 40, Slack = 24, OpenAI sk- = ~50)
OPAQUE_RE = re.compile(r"^[A-Za-z0-9+=/_\-]{16,}$")
# user:pass внутри строки
USERPASS_RE = re.compile(r"[\"'][^\"'\s:/@$]+:[^\"'\s@/]{4,}[\"']")
# Переменные, чьи значения — пути/URL/имена, а не секреты
# WEBHOOK_URL и DATABASE_URL намеренно НЕ в whitelist — они содержат секреты
BENIGN_NAME_RE = re.compile(
    r"(?i)^(PATH|HOME|SHELL|PWD|OLDPWD|USER|LOGNAME|TERM|LANG|LOCALE|EDITOR"
    r"|PAGER|TMPDIR|HOSTNAME|SHLVL|ZSH|BASH|PS1|PS2|DISPLAY|XDG_.*"
    r"|.*_DIR|.*_HOME|.*_PORT|.*_VERSION|.*_NAME|.*_THEME"
    r"|.*_MIRROR|.*_REGISTRY|.*_REPO|.*_PROXY|.*_CACHE|.*_PREFIX"
    r"|.*_INSTALL|.*_BIN|.*_LOG|.*_LEVEL|.*_TIMEOUT|.*_LIMIT|.*_SOCK"
    r"|.*_TTY|.*_CMD|.*_SHELL|.*_PROFILE|.*_STATE|.*_FILE|.*_DIRS"
    r"|NODE_PATH|PYTHONPATH|GOPATH|GOROOT|MANPATH|PKG_CONFIG_PATH"
    r"|NVM_DIR|NVM_BIN|PYENV_ROOT|GEM_HOME|RBENV_ROOT|CARGO_HOME"
    r"|NPM_CONFIG_PREFIX|PNPM_HOME|BUN_INSTALL|YARN_CACHE_FOLDER)$")
# URL без credentials — не секрет (но не webhook/service-токен URL)
_PLAIN_URL_RE = re.compile(r"^https?://(?!hooks\.slack\.com|discord\.com/api/webhooks)[^\s:@]{3,}$")


def value_is_secret(name: str, value: str) -> bool:
    """Похоже ли значение на секрет (по имени переменной и виду значения)."""
    if not value:
        return False
    raw = value.strip().strip("\"'")
    if not raw or _PLACEHOLDER_RE.search(raw) or len(raw) < 6:
        return False
    # путь к файлу/директории — никогда не секрет
    if raw.startswith("/") or raw.startswith("~/") or raw.startswith("./"):
        return False
    if os.path.sep in raw and os.path.sep == "/" and raw.count("/") >= 2:
        return False
    # connection string → всегда содержит секрет
    if _CONNSTR_RE.search(value):
        return True
    # webhook URL
    if _WEBHOOK_RE.search(value):
        return True
    # обычный URL без credentials → не секрет
    if _PLAIN_URL_RE.match(raw):
        return False
    # имя переменной явно секретное
    if SECRET_NAME_RE.search(name) and not BENIGN_NAME_RE.match(name):
        return True
    # длинная непрозрачная строка (без слешей — иначе это путь)
    if OPAQUE_RE.match(raw) and "/" not in raw and "\\" not in raw:
        return True
    if USERPASS_RE.search(value):
        return True
    return False


def mask_value(name: str, value: str) -> str:
    """Вернуть замаскированное значение или исходное если оно не секрет."""
    if not value:
        return value
    # connection strings в значении
    if _CONNSTR_RE.search(value):
        return _CONNSTR_RE.sub(_mask_connstr, value)
    if _WEBHOOK_RE.search(value):
        return _WEBHOOK_RE.sub(_mask_webhook, value)
    # key=value внутри самого значения
    synthetic = "%s=%s" % (name, value)
    if SECRET_RE.search(synthetic):
        def _safe(m: re.Match) -> str:
            if _is_benign_secret_line(synthetic, m.group("val")):
                return m.group(0)
            return _mask_match(m)
        masked = SECRET_RE.sub(_safe, synthetic)
        return masked.split("=", 1)[1] if "=" in masked else "••••••"
    if value_is_secret(name, value):
        return "••••••"
    return value


def human_size(n: int) -> str:
    if n < 1024:
        return "%d B" % n
    if n < 1024 ** 2:
        return "%.1f KB" % (n / 1024)
    if n < 1024 ** 3:
        return "%.1f MB" % (n / 1024 ** 2)
    return "%.1f GB" % (n / 1024 ** 3)


# --------------------------------------------------------------------------- #
#  Пакеты и версии инструментов
# --------------------------------------------------------------------------- #

from dataclasses import dataclass as _dc


@_dc
class Package:
    manager: str    # brew, npm, pip, cargo, uv, nvm, go
    name: str
    version: str
    extra: str = ""  # e.g. "global", "tap"


@_dc
class DevContext:
    """Компактное описание среды разработчика — для агентов."""
    git_user: str = ""
    git_email: str = ""
    git_signing: str = ""       # "ssh" / "gpg" / ""
    git_signing_key: str = ""
    shell: str = ""
    editor: str = ""
    node_version: str = ""
    node_manager: str = ""      # nvm / system
    python_version: str = ""
    python_path: str = ""
    go_version: str = ""
    ruby_version: str = ""
    rust_version: str = ""
    ssh_keys: list[str] = field(default_factory=list)
    path_issues: list[str] = field(default_factory=list)
    env_conflicts: list[str] = field(default_factory=list)


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    """Запустить команду, вернуть stdout или '' при ошибке."""
    try:
        r = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL,
                           timeout=timeout, check=False)
        return r.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def _run_sh(script: str, timeout: float = 8.0) -> str:
    try:
        r = subprocess.run(["sh", "-c", script], capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, check=False)
        return r.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return ""


_PKG_CACHE: dict[str, list[Package]] | None = None
_PKG_DISK_CACHE = os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "atlas_pkg_cache.json")
_PKG_CACHE_TTL = 300   # секунд (5 минут)


def _load_pkg_disk() -> dict[str, list[Package]] | None:
    try:
        st = os.stat(_PKG_DISK_CACHE)
        if time.time() - st.st_mtime > _PKG_CACHE_TTL:
            return None
        with open(_PKG_DISK_CACHE) as fh:
            raw = json.load(fh)
        return {mgr: [Package(**p) for p in pkgs]
                for mgr, pkgs in raw.items()}
    except Exception:
        return None


def _save_pkg_disk(data: dict[str, list[Package]]) -> None:
    try:
        from dataclasses import asdict
        serializable = {mgr: [asdict(p) for p in pkgs]
                        for mgr, pkgs in data.items()}
        with open(_PKG_DISK_CACHE, "w") as fh:
            json.dump(serializable, fh)
    except Exception:
        pass


def _scan_brew() -> list[Package]:
    raw = _run(["brew", "list", "--versions"])
    pkgs = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            pkgs.append(Package("brew", parts[0], parts[-1]))
    return pkgs


def _scan_npm() -> list[Package]:
    raw = _run(["npm", "list", "-g", "--depth=0"])
    pkgs = []
    for line in raw.splitlines():
        line = line.strip()
        m = re.match(r"[├└─\s]+(@?[^@\s]+)@(.+)", line)
        if m:
            pkgs.append(Package("npm", m.group(1), m.group(2), "global"))
    return pkgs


def _scan_pip() -> list[Package]:
    raw = _run([sys.executable, "-m", "pip", "list", "--format=json"])
    if not raw:
        raw = _run(["pip3", "list", "--format=json"])
    try:
        return [Package("pip", p["name"], p["version"])
                for p in json.loads(raw)] if raw else []
    except (json.JSONDecodeError, KeyError):
        return []


def _scan_uv() -> list[Package]:
    raw = _run(["uv", "tool", "list"])
    pkgs = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("-"):
            continue
        m = re.match(r"(\S+)\s+v?(\S+)", line)
        if m:
            pkgs.append(Package("uv", m.group(1), m.group(2)))
    return pkgs


def _scan_cargo() -> list[Package]:
    cargo_toml = os.path.expanduser("~/.cargo/.crates.toml")
    if os.path.exists(cargo_toml):
        try:
            with open(cargo_toml) as fh:
                content = fh.read()
            pkgs = []
            for m in re.finditer(r'"([^"]+)\s+([^\s"]+)\s+\(', content):
                pkgs.append(Package("cargo", m.group(1), m.group(2)))
            return pkgs
        except OSError:
            pass
    cargo_bin = os.path.expanduser("~/.cargo/bin")
    if os.path.isdir(cargo_bin):
        return [Package("cargo", b, "?")
                for b in sorted(os.listdir(cargo_bin))]
    return []


def _scan_nvm() -> list[Package]:
    nvm_dir = os.path.expanduser("~/.nvm/versions/node")
    if not os.path.isdir(nvm_dir):
        return []
    active = _run_sh("node --version").lstrip("v")
    pkgs = []
    for v in sorted(os.listdir(nvm_dir)):
        ver = v.lstrip("v")
        pkgs.append(Package("nvm", "node", ver,
                             "active" if ver == active else ""))
    return pkgs


def _scan_go_tools() -> list[Package]:
    gopath = _run(["go", "env", "GOPATH"]) or os.path.expanduser("~/go")
    gobin = os.path.join(gopath, "bin")
    if os.path.isdir(gobin):
        return [Package("go", b, "?") for b in sorted(os.listdir(gobin))]
    return []


def scan_packages(managers: list[str] | None = None) -> dict[str, list[Package]]:
    """Установленные пакеты по менеджерам — запускает сканеры параллельно.

    managers=None → все доступные (brew, npm, pip, uv, cargo, nvm, go).
    """
    global _PKG_CACHE
    if _PKG_CACHE is not None:
        want = set(managers) if managers else None
        if want is None:
            return _PKG_CACHE
        return {k: v for k, v in _PKG_CACHE.items() if k in want}

    # disk cache (TTL=5 мин)
    if managers is None:
        disk = _load_pkg_disk()
        if disk is not None:
            _PKG_CACHE = disk
            return disk

    import concurrent.futures

    scanners: dict[str, object] = {
        "brew":  _scan_brew,
        "npm":   _scan_npm,
        "pip":   _scan_pip,
        "uv":    _scan_uv,
        "cargo": _scan_cargo,
        "nvm":   _scan_nvm,
        "go":    _scan_go_tools,
    }
    want_set = set(managers) if managers else set(scanners)

    result: dict[str, list[Package]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
        futs = {mgr: ex.submit(fn)   # type: ignore[operator]
                for mgr, fn in scanners.items() if mgr in want_set}
        for mgr, fut in futs.items():
            try:
                pkgs = fut.result(timeout=12)
                if pkgs:
                    result[mgr] = pkgs
            except Exception:
                pass   # таймаут или ошибка — пропускаем менеджер

    _PKG_CACHE = result
    if managers is None:
        _save_pkg_disk(result)
    return result


def invalidate_pkg_cache() -> None:
    global _PKG_CACHE
    _PKG_CACHE = None
    try:
        os.unlink(_PKG_DISK_CACHE)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  Контекст разработчика
# --------------------------------------------------------------------------- #

_CTX_CACHE: DevContext | None = None


def _ctx_git() -> tuple[str, str, str, str]:
    user  = _run(["git", "config", "--global", "user.name"])
    email = _run(["git", "config", "--global", "user.email"])
    sign  = _run(["git", "config", "--global", "commit.gpgsign"])
    fmt   = ""
    key   = ""
    if sign.lower() == "true":
        fmt = _run(["git", "config", "--global", "gpg.format"]) or "gpg"
        key = _run(["git", "config", "--global", "user.signingkey"])
    return user, email, fmt, key


def _ctx_runtimes() -> tuple[str, str, str, str, str]:
    node = _run(["node", "--version"]).lstrip("v")
    go_r = _run(["go", "version"])
    go_m = re.search(r"go(\d+\.\d+(?:\.\d+)?)", go_r)
    go   = go_m.group(1) if go_m else ""
    ruby_r = _run(["ruby", "--version"])
    ruby_m = re.search(r"ruby (\d+\.\d+\.\d+)", ruby_r)
    ruby = ruby_m.group(1) if ruby_m else ""
    rust_r = _run(["rustc", "--version"])
    rust_m = re.search(r"rustc (\d+\.\d+\.\d+)", rust_r)
    rust = rust_m.group(1) if rust_m else ""
    return node, go, ruby, rust, _run([sys.executable, "--version"]).replace("Python ", "")


def _ctx_env_conflicts(entries_: list[Entry]) -> list[str]:
    conflicts: list[str] = []
    try:
        idx = build_env_index(entries_, include_process=False)
        by_name: dict[str, list[EnvVar]] = {}
        for v in idx:
            by_name.setdefault(v.name, []).append(v)
        home = os.path.expanduser("~")
        for name, vars_ in by_name.items():
            vals = [v.value for v in vars_]
            if len(set(vals)) > 1:
                def _sh(p: str) -> str:
                    return "~" + p[len(home):] if p.startswith(home) else p
                conflicts.append(
                    "%s: %s" % (name, " vs ".join(
                        "%s(%s)" % (_sh(v.entry.path) if v.entry else "?", v.value[:30])
                        for v in vars_))
                )
    except Exception:
        pass
    return conflicts


def get_dev_context(use_cache: bool = True) -> DevContext:
    """Компактный снимок среды разработчика.

    Агент вызывает один раз вместо 10+ read_config / list_env.
    Тяжёлые вызовы запускаются параллельно — ~0.3 с вместо ~1 с.
    """
    import concurrent.futures

    global _CTX_CACHE
    if use_cache and _CTX_CACHE is not None:
        return _CTX_CACHE

    ctx = DevContext()
    ctx.shell  = os.environ.get("SHELL") or "/bin/zsh"
    ctx.editor = (os.environ.get("VISUAL") or os.environ.get("EDITOR") or "")
    ctx.python_path = sys.executable

    # nvm / ssh keys — быстро, без subprocess
    nvm_dir = os.path.expanduser("~/.nvm/versions/node")
    ctx.node_manager = "nvm" if os.path.isdir(nvm_dir) else "system"
    ssh_dir = os.path.expanduser("~/.ssh")
    if os.path.isdir(ssh_dir):
        ctx.ssh_keys = sorted(
            f.replace(".pub", "")
            for f in os.listdir(ssh_dir) if f.endswith(".pub"))

    # PATH issues — быстро, без subprocess
    path_dirs = os.environ.get("PATH", "").split(":")
    seen_dirs: set[str] = set()
    for d in path_dirs:
        if not d:
            continue
        if d in seen_dirs:
            ctx.path_issues.append("дубль: %s" % d)
        elif not os.path.isdir(d):
            ctx.path_issues.append("не существует: %s" % d)
        seen_dirs.add(d)

    # Тяжёлые задачи — параллельно
    entries_ = build_map()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        f_git      = ex.submit(_ctx_git)
        f_runtimes = ex.submit(_ctx_runtimes)
        f_conflicts = ex.submit(_ctx_env_conflicts, entries_)

        git_user, git_email, git_fmt, git_key = f_git.result(timeout=8)
        node, go, ruby, rust, python_v        = f_runtimes.result(timeout=8)
        conflicts                              = f_conflicts.result(timeout=10)

    ctx.git_user    = git_user
    ctx.git_email   = git_email
    ctx.git_signing = git_fmt
    ctx.git_signing_key = git_key
    ctx.node_version    = node
    ctx.go_version      = go
    ctx.ruby_version    = ruby
    ctx.rust_version    = rust
    ctx.python_version  = python_v
    ctx.env_conflicts   = conflicts

    if use_cache:
        _CTX_CACHE = ctx
    return ctx


def dev_context_text(ctx: DevContext | None = None) -> str:
    """Компактный текст контекста — для агентов и /context команды."""
    if ctx is None:
        ctx = get_dev_context()
    lines = []

    def row(label: str, value: str) -> None:
        if value:
            lines.append("%-14s %s" % (label, value))

    row("git user:", "%s <%s>" % (ctx.git_user, ctx.git_email)
        if ctx.git_user else "")
    if ctx.git_signing:
        row("git signing:", "%s  key: %s" % (ctx.git_signing, ctx.git_signing_key))
    row("shell:", ctx.shell)
    row("editor:", ctx.editor or "(не задан)")
    row("node:", "%s (%s)" % (ctx.node_version, ctx.node_manager)
        if ctx.node_version else "")
    row("python:", "%s  %s" % (ctx.python_version, ctx.python_path)
        if ctx.python_version else "")
    row("go:", ctx.go_version)
    row("ruby:", ctx.ruby_version)
    row("rust:", ctx.rust_version)
    if ctx.ssh_keys:
        row("ssh keys:", "  ".join(ctx.ssh_keys))
    if ctx.path_issues:
        lines.append("")
        lines.append("PATH проблемы:")
        for issue in ctx.path_issues[:10]:
            lines.append("  " + issue)
    if ctx.env_conflicts:
        lines.append("")
        lines.append("Конфликты переменных:")
        for c in ctx.env_conflicts[:10]:
            lines.append("  " + c)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  /trace — откуда взялась переменная окружения
# --------------------------------------------------------------------------- #

@dataclass
class EnvTrace:
    name: str
    value: str
    sources: list[dict]   # [{file, line, raw_line, is_winner}]
    process_value: str = ""   # текущее значение в os.environ


def trace_env_var(name: str,
                  entries_: list[Entry] | None = None) -> EnvTrace:
    """Найти все места, где задана переменная name, и вернуть цепочку."""
    if entries_ is None:
        entries_ = build_map()
    idx = build_env_index(entries_, include_process=False)
    sources = []
    for v in idx:
        if v.name.upper() != name.upper():
            continue
        sources.append({
            "file": v.entry.path if v.entry else "(process)",
            "line": v.lineno,
            "raw": v.value,
            "origin": v.origin,
        })
    # текущее значение — из login shell или os.environ
    shell_env = login_shell_env()
    process_val = shell_env.get(name) or os.environ.get(name, "")
    # добавляем из PATH-подобных случаев
    if not sources and process_val:
        sources.append({"file": "(shell)", "line": 0,
                        "raw": process_val, "origin": "process"})
    return EnvTrace(name=name, value=process_val,
                    sources=sources, process_value=process_val)


# --------------------------------------------------------------------------- #
#  /diff env — расхождение os.environ vs login shell
# --------------------------------------------------------------------------- #

@dataclass
class EnvDiff:
    name: str
    process_val: str    # в текущем процессе (IDE/агент)
    shell_val: str      # в новом терминале (login shell)
    status: str         # "conflict" | "only_process" | "only_shell"


def diff_env(entries_: list[Entry] | None = None) -> list[EnvDiff]:
    """Сравнить os.environ (текущий процесс) с login-shell окружением.

    Возвращает только расхождения — переменные, которые IDE/агент видит
    иначе чем терминал.
    """
    shell_env = login_shell_env()
    proc_env = dict(os.environ)
    all_keys = set(proc_env) | set(shell_env)
    diffs: list[EnvDiff] = []
    for key in sorted(all_keys):
        if is_system_env(key):
            continue
        pv = proc_env.get(key, "")
        sv = shell_env.get(key, "")
        if pv == sv:
            continue
        if pv and sv:
            status = "conflict"
        elif pv:
            status = "only_process"
        else:
            status = "only_shell"
        diffs.append(EnvDiff(name=key, process_val=pv,
                             shell_val=sv, status=status))
    return diffs


# --------------------------------------------------------------------------- #
#  /git-audit — какой email будет у коммита в каждом репо
# --------------------------------------------------------------------------- #

@dataclass
class GitRepoAudit:
    path: str
    local_email: str    # "" если не задан локально
    local_name: str
    effective_email: str
    effective_name: str
    global_email: str
    global_name: str
    has_local_config: bool
    unsigned: bool      # gpg/ssh signing не настроен локально


def _git_config_in(repo: str, key: str) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", repo, "config", "--local", key],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=4)
        return r.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def _git_config_effective(repo: str, key: str) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", repo, "config", key],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=4)
        return r.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def _find_git_repos(root: str, max_depth: int = 3) -> list[str]:
    """Рекурсивно найти git-репозитории до max_depth уровней."""
    repos: list[str] = []
    try:
        for entry in os.scandir(root):
            if entry.name.startswith("."):
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            git_dir = os.path.join(entry.path, ".git")
            if os.path.exists(git_dir):
                repos.append(entry.path)
            elif max_depth > 1:
                repos.extend(_find_git_repos(entry.path, max_depth - 1))
    except PermissionError:
        pass
    return repos


def git_audit(search_dirs: list[str] | None = None,
              max_depth: int = 3) -> list[GitRepoAudit]:
    """Аудит git-репозиториев: какой email/name будет у следующего коммита."""
    if search_dirs is None:
        home = os.path.expanduser("~")
        search_dirs = [home, os.path.expanduser("~/Projects"),
                       os.path.expanduser("~/work"),
                       os.path.expanduser("~/dev")]
    global_email = _run(["git", "config", "--global", "user.email"])
    global_name  = _run(["git", "config", "--global", "user.name"])
    global_sign  = _run(["git", "config", "--global", "commit.gpgsign"])

    seen: set[str] = set()
    repos: list[str] = []
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        # сам dir может быть репо
        if os.path.exists(os.path.join(d, ".git")):
            if d not in seen:
                repos.append(d)
                seen.add(d)
        for r in _find_git_repos(d, max_depth):
            if r not in seen:
                repos.append(r)
                seen.add(r)

    result: list[GitRepoAudit] = []
    for repo in repos[:50]:   # ограничение: не сканируем бесконечно
        local_email = _git_config_in(repo, "user.email")
        local_name  = _git_config_in(repo, "user.name")
        eff_email   = _git_config_effective(repo, "user.email")
        eff_name    = _git_config_effective(repo, "user.name")
        local_sign  = _git_config_in(repo, "commit.gpgsign")
        has_local   = os.path.exists(os.path.join(repo, ".git", "config"))
        unsigned    = (global_sign.lower() == "true" and
                       local_sign.lower() not in ("true", "false"))
        result.append(GitRepoAudit(
            path=repo,
            local_email=local_email, local_name=local_name,
            effective_email=eff_email, effective_name=eff_name,
            global_email=global_email, global_name=global_name,
            has_local_config=bool(local_email or local_name),
            unsigned=unsigned,
        ))
    return result


# --------------------------------------------------------------------------- #
#  /ssh — аудит SSH-конфигурации
# --------------------------------------------------------------------------- #

@dataclass
class SshHost:
    name: str           # паттерн из Host
    hostname: str
    user: str
    identity_file: str
    key_exists: bool
    key_in_agent: bool
    port: str
    forward_agent: bool
    extra: dict         # прочие ключи


@dataclass
class SshAudit:
    hosts: list[SshHost]
    agent_keys: list[str]       # fingerprints из ssh-add -l
    known_issues: list[str]


def _parse_ssh_config(path: str) -> list[SshHost]:
    hosts: list[SshHost] = []
    if not os.path.exists(path):
        return hosts
    current: dict[str, str] = {}
    host_name = ""
    try:
        with open(path) as fh:
            lines = fh.readlines()
    except OSError:
        return hosts
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        key, val = parts[0].lower(), parts[1].strip()
        if key == "host":
            if host_name:
                hosts.append(_ssh_host_from(host_name, current))
            host_name = val
            current = {}
        else:
            current[key] = val
    if host_name:
        hosts.append(_ssh_host_from(host_name, current))
    return hosts


def _ssh_host_from(name: str, cfg: dict) -> SshHost:
    idf = cfg.get("identityfile", "").strip("\"'")
    if idf:
        idf = os.path.expanduser(idf)
    key_exists = bool(idf and os.path.exists(idf))
    return SshHost(
        name=name,
        hostname=cfg.get("hostname", ""),
        user=cfg.get("user", ""),
        identity_file=idf,
        key_exists=key_exists,
        key_in_agent=False,   # заполним позже
        port=cfg.get("port", "22"),
        forward_agent=cfg.get("forwardagent", "no").lower() == "yes",
        extra={k: v for k, v in cfg.items()
               if k not in ("hostname", "user", "identityfile",
                            "port", "forwardagent")},
    )


def ssh_audit() -> SshAudit:
    """Полный аудит SSH: хосты, ключи, агент, проблемы."""
    config_path = os.path.expanduser("~/.ssh/config")
    hosts = _parse_ssh_config(config_path)

    # ключи в агенте
    agent_out = _run(["ssh-add", "-l"])
    agent_keys: list[str] = []
    agent_fps: set[str] = set()
    for line in agent_out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            agent_keys.append(line.strip())
            agent_fps.add(parts[1])   # fingerprint

    # проверяем ключ каждого хоста в агенте
    for h in hosts:
        if not h.identity_file or not h.key_exists:
            continue
        fp_out = _run(["ssh-keygen", "-lf", h.identity_file])
        if fp_out:
            fp = fp_out.split()[1] if len(fp_out.split()) > 1 else ""
            h.key_in_agent = fp in agent_fps

    # проблемы
    issues: list[str] = []
    for h in hosts:
        if h.name in ("*", "* "):
            continue
        if h.identity_file and not h.key_exists:
            issues.append("Host %s: ключ не найден: %s" % (h.name, h.identity_file))
        if h.identity_file and h.key_exists and not h.key_in_agent:
            issues.append("Host %s: ключ есть, но не в ssh-agent" % h.name)
        if h.forward_agent and not h.key_in_agent:
            issues.append("Host %s: ForwardAgent=yes, но ключ не в агенте" % h.name)
    # ключи в ~/.ssh без записи в config
    ssh_dir = os.path.expanduser("~/.ssh")
    if os.path.isdir(ssh_dir):
        all_keys = {f.replace(".pub", "")
                    for f in os.listdir(ssh_dir) if f.endswith(".pub")
                    and f not in ("authorized_keys",)}
        used_keys = {os.path.basename(h.identity_file)
                     for h in hosts if h.identity_file}
        for k in sorted(all_keys - used_keys):
            issues.append("Ключ %s есть, но не используется ни одним Host" % k)

    return SshAudit(hosts=hosts, agent_keys=agent_keys, known_issues=issues)


# --------------------------------------------------------------------------- #
#  /stale — конфиги с захардкоженными путями к Cellar/версиям
# --------------------------------------------------------------------------- #

@dataclass
class StaleRef:
    entry: Entry
    line: int
    raw_line: str
    reason: str     # тип проблемы


STALE_PATTERNS = [
    (re.compile(r"/opt/homebrew/Cellar/[a-z0-9@._-]+/[\d.]+/"),
     "путь к конкретной версии Cellar"),
    (re.compile(r"/usr/local/Cellar/[a-z0-9@._-]+/[\d.]+/"),
     "путь к конкретной версии Cellar (Intel)"),
    (re.compile(r"python3?\.\d+(?:\.\d+)?(?:/bin)?"),
     "захардкоженная версия Python"),
    (re.compile(r"node/v[\d.]+/"),
     "захардкоженная версия Node"),
    (re.compile(r"jdk[\d._]+"),
     "захардкоженная версия JDK"),
    (re.compile(r"ruby[\d.]+"),
     "захардкоженная версия Ruby"),
    (re.compile(r"go[\d.]+/bin"),
     "захардкоженная версия Go"),
]


def find_stale_refs(entries_: list[Entry] | None = None,
                    limit: int = 200) -> list[StaleRef]:
    """Конфиги, ссылающиеся на конкретные версии пакетов."""
    if entries_ is None:
        entries_ = build_map()
    results: list[StaleRef] = []
    for e in entries_:
        if not e.exists or e.is_dir or e.size > 512 * 1024:
            continue
        lines, is_bin = read_preview(e.path, limit=50_000)
        if is_bin:
            continue
        for i, line in enumerate(lines, 1):
            for pat, reason in STALE_PATTERNS:
                if pat.search(line):
                    results.append(StaleRef(
                        entry=e, line=i,
                        raw_line=line.strip()[:120],
                        reason=reason))
                    break
            if len(results) >= limit:
                return results
    return results


# --------------------------------------------------------------------------- #
#  /orphan — конфиги для удалённых приложений
# --------------------------------------------------------------------------- #

@dataclass
class OrphanEntry:
    entry: Entry
    app_name: str
    reason: str


def _installed_apps() -> set[str]:
    """Имена установленных приложений (нижний регистр)."""
    apps: set[str] = set()
    for d in ("/Applications", os.path.expanduser("~/Applications")):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name.endswith(".app"):
                apps.add(name[:-4].lower())
    # brew
    brew_out = _run(["brew", "list", "--cask", "--versions"])
    for line in brew_out.splitlines():
        apps.add(line.split()[0].lower() if line.split() else "")
    # npm global
    npm_out = _run(["npm", "list", "-g", "--depth=0"])
    for line in npm_out.splitlines():
        m = re.match(r"[├└─\s]+@?([^@\s]+)@", line.strip())
        if m:
            apps.add(m.group(1).lower())
    return apps


# Приложения, которые существуют как CLI/сервис, не как .app → не orphan
_CLI_BINARIES: dict[str, str] = {
    # app_name (lower) → бинарь для проверки через `which`
    "gemini cli": "gemini", "gemini": "gemini",
    "windsurf": "windsurf",
    "trae": "trae",
    "antigravity": "antigravity",
    "devin": "devin",
    "claude code": "claude", "claude": "claude",
    "codex cli": "codex", "codex": "codex",
    "codexbar": "codexbar",
    "opencode": "opencode",
    "git": "git", "gh": "gh",
    "docker": "docker", "docker desktop": "docker",
    "kubectl": "kubectl", "k9s": "k9s", "helm": "helm",
    "terraform": "terraform", "ansible": "ansible",
    "vim": "vim", "neovim": "nvim", "nano": "nano",
    "zed": "zed",
    "node": "node", "npm": "npm", "yarn": "yarn", "pnpm": "pnpm", "bun": "bun",
    "python": "python3", "pip": "pip3", "uv": "uv",
    "rust": "rustc", "cargo": "cargo", "go": "go",
    "ruby": "ruby", "gem": "gem",
    "java": "java", "gradle": "gradle", "maven": "mvn",
    "aws cli": "aws", "aws": "aws",
    "gcloud": "gcloud", "gsutil": "gsutil",
    "az": "az",
    "ssh": "ssh", "gpg": "gpg",
    "brew": "brew", "homebrew": "brew",
    "nvm": "nvm",
    "pyenv": "pyenv",
    "rbenv": "rbenv",
    "mise": "mise", "asdf": "asdf",
    "starship": "starship",
    "oh my zsh": "zsh",
    "tmux": "tmux", "screen": "screen",
    "ripgrep": "rg", "fd": "fd", "bat": "bat", "fzf": "fzf",
    "mole": "mole",
    "kaggle": "kaggle",
    "leshy": "leshy",
}


def find_orphans(entries_: list[Entry] | None = None) -> list[OrphanEntry]:
    """Конфиги приложений, которые уже не установлены."""
    if entries_ is None:
        entries_ = build_map()
    installed = _installed_apps()
    results: list[OrphanEntry] = []
    for e in entries_:
        if not e.exists:
            continue
        if not e.app:
            continue
        app_lower = e.app.lower()

        # 1. Есть в установленных GUI-приложениях
        if (app_lower in installed or
                any(app_lower in a or a in app_lower for a in installed)):
            continue

        # 2. Есть CLI-бинарь (из таблицы или первое слово имени)
        binary_hint = _CLI_BINARIES.get(app_lower)
        if binary_hint and _run(["which", binary_hint]):
            continue
        fallback_bin = app_lower.split()[0]
        if _run(["which", fallback_bin]):
            continue

        # 3. Есть каталог конфига (~/Library/Application Support/AppName)
        app_support = os.path.expanduser(
            "~/Library/Application Support/" + e.app)
        if os.path.isdir(app_support):
            continue

        results.append(OrphanEntry(
            entry=e, app_name=e.app,
            reason="«%s» не найдено в системе" % e.app))

    # дедупликация по приложению
    seen: set[str] = set()
    deduped: list[OrphanEntry] = []
    for o in results:
        if o.app_name not in seen:
            deduped.append(o)
            seen.add(o.app_name)
    return deduped


# --------------------------------------------------------------------------- #
#  /secrets-scan — конфиги с секретами в git-репо
# --------------------------------------------------------------------------- #

@dataclass
class SecretLeak:
    entry: Entry
    line: int
    raw_line: str       # с маскировкой
    in_git: bool
    git_repo: str


def _file_in_git(path: str) -> tuple[bool, str]:
    """Проверить, отслеживается ли файл git'ом. Вернуть (tracked, repo_root)."""
    try:
        r = subprocess.run(
            ["git", "-C", os.path.dirname(path),
             "ls-files", "--error-unmatch", os.path.basename(path)],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=4)
        if r.returncode == 0:
            repo = subprocess.run(
                ["git", "-C", os.path.dirname(path),
                 "rev-parse", "--show-toplevel"],
                capture_output=True, stdin=subprocess.DEVNULL, timeout=4)
            return True, repo.stdout.decode().strip()
    except Exception:
        pass
    return False, ""


def scan_secret_leaks(entries_: list[Entry] | None = None,
                      limit: int = 100) -> list[SecretLeak]:
    """Файлы, содержащие секреты И отслеживаемые git'ом."""
    if entries_ is None:
        entries_ = build_map()
    results: list[SecretLeak] = []
    for e in entries_:
        if not e.exists or e.is_dir or e.size > 256 * 1024:
            continue
        lines, is_bin = read_preview(e.path, limit=20_000)
        if is_bin:
            continue
        found_secrets = []
        for i, line in enumerate(lines, 1):
            if SECRET_RE.search(line):
                masked = SECRET_RE.sub(_mask_match, line).strip()[:120]
                found_secrets.append((i, masked))
        if not found_secrets:
            continue
        in_git, repo = _file_in_git(e.path)
        for ln, raw in found_secrets[:5]:
            results.append(SecretLeak(
                entry=e, line=ln, raw_line=raw,
                in_git=in_git, git_repo=repo))
        if len(results) >= limit:
            break
    return results


# --------------------------------------------------------------------------- #
#  /export — генерация setup.sh / Brewfile
# --------------------------------------------------------------------------- #

def generate_export(format: str = "sh") -> str:
    """Сгенерировать скрипт воспроизведения среды.

    format: "sh" | "brew" | "all"
    """
    ctx = get_dev_context()
    pkgs = scan_packages()
    parts: list[str] = []

    if format in ("sh", "all"):
        parts.append("#!/usr/bin/env bash")
        parts.append("# Generated by ATLAS — dev environment setup")
        parts.append("# %s" % __import__("datetime").date.today())
        parts.append("")

        # git
        if ctx.git_user:
            parts.append("git config --global user.name  '%s'" % ctx.git_user)
        if ctx.git_email:
            parts.append("git config --global user.email '%s'" % ctx.git_email)
        if ctx.git_signing:
            parts.append("git config --global commit.gpgsign true")
            parts.append("git config --global gpg.format %s" % ctx.git_signing)
        parts.append("")

        # brew packages
        if "brew" in pkgs:
            parts.append("# Homebrew packages")
            parts.append("brew install \\")
            for p in pkgs["brew"]:
                parts.append("  %s \\" % p.name)
            parts[-1] = parts[-1].rstrip(" \\")
            parts.append("")

        # npm global
        if "npm" in pkgs:
            parts.append("# npm global packages")
            npm_names = [p.name for p in pkgs["npm"]
                         if p.name not in ("npm", "corepack")]
            if npm_names:
                parts.append("npm install -g %s" % " ".join(npm_names))
                parts.append("")

        # uv tools
        if "uv" in pkgs:
            parts.append("# uv tools")
            for p in pkgs["uv"]:
                parts.append("uv tool install %s" % p.name)
            parts.append("")

        # cargo
        if "cargo" in pkgs:
            parts.append("# Cargo packages")
            for p in pkgs["cargo"]:
                if p.version != "?":
                    parts.append("cargo install %s" % p.name)
            parts.append("")

        # node version
        if ctx.node_manager == "nvm" and ctx.node_version:
            parts.append("# Node version (nvm)")
            parts.append("nvm install %s" % ctx.node_version)
            parts.append("nvm use %s" % ctx.node_version)
            parts.append("")

        # ssh keys hint
        if ctx.ssh_keys:
            parts.append("# SSH keys to copy: %s" % ", ".join(ctx.ssh_keys))
            parts.append("")

    if format in ("brew", "all"):
        if format == "all":
            parts.append("")
            parts.append("# ── Brewfile ──────────────────────────────────")
        if "brew" in pkgs:
            for p in pkgs["brew"]:
                parts.append("brew '%s'" % p.name)

    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #


def cmd_json() -> None:
    entries = build_map()
    data = [asdict(e) for e in entries]
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_list() -> None:
    entries = build_map()
    cats = dict(CATEGORIES)
    by_cat: dict[str, list[Entry]] = {}
    for e in entries:
        by_cat.setdefault(e.category, []).append(e)
    for key, title in CATEGORIES:
        items = by_cat.get(key, [])
        if not items:
            continue
        print("\n\033[1m%s\033[0m  (%d)" % (title, len(items)))
        for e in sorted(items, key=lambda x: x.path):
            if e.source == "curated":
                mark = "★"
            else:
                mark = "○"
            if e.alias:
                mark = "↩"
            state = " " if e.exists else "✗"
            print("  %s%s %-58s %s" % (mark, state, e.path.replace(
                os.path.expanduser("~"), "~"), e.note))


def cmd_chains() -> None:
    entries = build_map()
    home = os.path.expanduser("~")
    print("\n\033[1mПриоритет конфигов\033[0m — какой файл реально применяется\n")
    for chain in CHAIN_GROUPS:
        pairs = [(e, r) for e, r in chain_rows(entries) if e.chain == chain.id]
        if not pairs:
            continue
        print("\033[1m%s\033[0m  — %s" % (chain.title, chain.note))
        for e, role in pairs:
            sym = {"winner": "✓", "shadow": "✗", "absent": "·"}.get(
                e.chain_role, " ")
            disp = e.path.replace(home, "~")
            if e.relative:
                disp = "(проект) " + disp
            print("   %s %-48s %s" % (sym, disp, role))
        print()


def cmd_env() -> None:
    entries = build_map()
    env = build_env_index(entries)
    home = os.path.expanduser("~")
    from_files = sum(1 for v in env if v.origin == "file")
    print("\n\033[1mПеременные окружения\033[0m — %d из файлов, "
          "%d из окружения\n" % (from_files, len(env) - from_files))
    last = ""
    for v in sorted(env, key=lambda x: (x.name, x.origin != "file",
                                        x.entry.path if x.entry else "",
                                        x.lineno)):
        if v.name != last:
            print("\n\033[1m%s\033[0m" % v.name)
            last = v.name
        val = mask_value(v.name, v.value)
        if v.entry:
            print("   %-44s %-4d %s" % (
                v.entry.path.replace(home, "~"), v.lineno, val[:50]))
        else:
            print("   %-44s %-4s %s" % (
                "⚙ только в окружении", "—", val[:50]))


def cmd_grep(query: str) -> None:
    entries = build_map()
    home = os.path.expanduser("~")
    hits = grep_entries(entries, query)
    print("\n\033[1mСовпадения по содержимому: «%s»\033[0m — %d\n"
          % (query, len(hits)))
    for e, lineno, text in hits:
        print("   %s:%-5d %s" % (e.path.replace(home, "~"), lineno, text[:90]))


def main() -> None:
    locale.setlocale(locale.LC_ALL, "")
    args = sys.argv[1:]
    if "--json" in args:
        cmd_json()
        return
    if "--list" in args:
        cmd_list()
        return
    if "--chains" in args:
        cmd_chains()
        return
    if "--env" in args:
        cmd_env()
        return
    if "--grep" in args:
        rest = [a for a in args if a != "--grep"]
        if not rest:
            print("Укажите запрос: config-atlas --grep proxy", file=sys.stderr)
            return
        cmd_grep(rest[0])
        return
    if "--help" in args or "-h" in args:
        print(__doc__)
        return
    print(__doc__)
    print("\nИнтерактивный интерфейс: uv run --script atlas_tui.py",
          file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:      # например, `config-atlas --json | head`
        try:
            sys.stdout.close()
        except Exception:
            pass
        os._exit(0)
    except KeyboardInterrupt:
        os._exit(130)
