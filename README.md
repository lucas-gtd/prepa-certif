# Prépa certif

A small CLI assistant that helps you prepare for a Microsoft certification exam.
It picks a certification, then uses an LLM (via [OpenRouter](https://openrouter.ai))
to gather official Microsoft Learn learning paths, documentation, and relevant
YouTube tutorials, and prints them as a clean Markdown summary in your terminal.

## Requirements

- Python 3.10+
- An [OpenRouter](https://openrouter.ai) API key

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
OPENROUTER_API_KEY=your_openrouter_api_key_here
MODEL_ID=google/gemma-4-31b-it
```

- `OPENROUTER_API_KEY` — your API key from https://openrouter.ai/keys
- `MODEL_ID` — any model ID available on OpenRouter

## Run

```bash
python main.py
```

You will be prompted to fuzzy-search and select a certification. The assistant
will then fetch resources and display a Markdown report directly in the terminal.
