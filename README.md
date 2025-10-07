# SynteraGPT Bot

Telegram bot "SynteraGPT" for intelligent assistance with GPT-5, media analysis, and tariff management.

## Setup

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set real values for:
   - `BOT_TOKEN` – Telegram bot token (required)
   - `OPENAI_API_KEY` – OpenAI API key (required)
   - `PAY_URL_HARMONY` – payment link for the "Basic" tariff (required)
   - `PAY_URL_REFLECTION` – payment link for the "Pro" tariff (required)
   - `PAY_URL_TRAVEL` – payment link for the "Ultra" tariff (required)
   - `PAY_URL_PACK_*` – ссылки на оплату дополнительных пакетов (если продаёте пакеты)
   - `YOOKASSA_SHOP_ID` – YooKassa shop identifier used by the SDK (required)
   - `YOOKASSA_API_KEY` – YooKassa secret key used by the SDK (required)
3. Run the bot:
   ```bash
   python3 bot.py
   ```
