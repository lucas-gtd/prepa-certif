# Prépa certif

A small CLI assistant that helps you prepare for a Microsoft certification exam.
It picks a certification, then uses an LLM (via [GitHub Models](https://models.github.ai))
to gather official Microsoft Learn learning paths, documentation, and relevant
YouTube tutorials, and prints them as a clean Markdown summary in your terminal.

## Requirements

- Python 3.10+
- A [GitHub personal access token](https://github.com/settings/tokens) with access to GitHub Models

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/lucas-gtd/prepa-certif.git
cd prepa-certif

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate

# 3. Install the dependencies
pip install -r requirements.txt
```

## Configuration

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
GITHUB_TOKEN=your_github_pat_here
MODEL_ID=openai/gpt-4o-mini
```

- `GITHUB_TOKEN` — a GitHub PAT with the `models:read` scope (see https://github.com/settings/tokens)
- `MODEL_ID` — any model ID available on GitHub Models (e.g. `openai/gpt-4o-mini`, `meta/Llama-3.3-70B-Instruct`)

## Run

```bash
python main.py
```

You will be prompted to fuzzy-search and select a certification. The assistant
will then fetch resources and display a Markdown report directly in the terminal.
