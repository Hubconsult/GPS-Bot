# SynteraGPT Bot

Telegram bot "SynteraGPT" for intelligent assistance with GPT-5 and media analysis.

## Setup

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set real values for:
   - `BOT_TOKEN` – Telegram bot token (required)
   - `OPENAI_API_KEY` – OpenAI API key (required)
   - Optional Redis and model overrides as needed
3. Run the bot:
   ```bash
   python3 bot.py
   ```
