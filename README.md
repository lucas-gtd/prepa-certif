# Prépa Certif

A friendly **desktop app** that helps you prepare for any Microsoft certification.
Pick an exam, and an AI agent gathers the official Microsoft Learn learning paths
and documentation plus curated YouTube tutorials, all in one place.

## Features

- 🖥️ **Desktop GUI** (Tkinter — works on Windows, macOS, Linux, no browser needed)
- 🔎 **Searchable** list of every Microsoft certification (just start typing)
- 🤖 AI-powered: combines official Microsoft Learn results with hand-picked
  YouTube videos
- 🔗 Clickable links open straight in your browser
- ♿ **Accessible by design**: keyboard navigation, large readable fonts,
  screen-reader-friendly controls, in-app Settings dialog (no need to edit
  config files), clear status messages
- 🧑‍💻 Still works as a CLI for power users (`python main.py --cli`)

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Launch the desktop app
python main.py
```

The first time you launch the app, open **File → Settings** (or press `Ctrl+,`)
and paste your free [OpenRouter API key](https://openrouter.ai/keys). That's it.

## Keyboard shortcuts

| Shortcut  | Action                  |
|-----------|-------------------------|
| `Ctrl+,`  | Open Settings           |
| `Enter`   | Run search              |
| `F5`      | Re-run search           |
| `Tab`     | Move between controls   |

## Power-user CLI

```bash
python main.py --cli
```

## Project layout

```
agent.py    # Reusable AI agent (used by both GUI and CLI)
gui.py      # Tkinter desktop interface
main.py     # Entry point (GUI by default, --cli for terminal)
tools.py    # Microsoft Learn & YouTube tool implementations
```
