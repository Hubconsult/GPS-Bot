# GPS-Bot

Telegram bot "Vnutrenniy GPS" (Internal GPS) for mood tracking and quick mental help.

## Setup

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set real values for:
   - `BOT_TOKEN` – Telegram bot token
   - `OPENAI_API_KEY` – OpenAI API key
   - `FREE_LIMIT` – number of free interactions (default 10)
   - `PAY_BUTTON_URL` – link to payment page
3. Run the bot:
   ```bash
   python3 bot.py
   ```
