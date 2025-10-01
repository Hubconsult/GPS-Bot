# SynteraGPT Bot

Telegram bot "SynteraGPT" for intelligent assistance with GPT-5, media analysis, and tariff management.

## Setup

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set real values for:
   - `BOT_TOKEN` – Telegram bot token
   - `OPENAI_API_KEY` – OpenAI API key
   - `FREE_LIMIT` – number of free interactions (default 10)
   - `PAY_URL_HARMONY` – payment link for the "Basic" tariff
   - `PAY_URL_REFLECTION` – payment link for the "Pro" tariff
   - `PAY_URL_TRAVEL` – payment link for the "Ultra" tariff
3. Run the bot:
   ```bash
   python3 bot.py
   ```
