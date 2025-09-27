"""Background polling of YooKassa payments."""

import sqlite3
import threading
import time

from yookassa import Configuration, Payment

from settings import YOOKASSA_SHOP_ID, YOOKASSA_API_KEY, bot
from tariffs import activate_tariff

DB_PATH = "users.db"

# Настраиваем YooKassa SDK
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_API_KEY


def init_payments_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
    CREATE TABLE IF NOT EXISTS pending_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        tariff_key TEXT,
        payment_id TEXT,
        status TEXT
    )
    """
    )
    conn.commit()
    conn.close()


def add_payment(chat_id: int, tariff_key: str, payment_id: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO pending_payments(chat_id, tariff_key, payment_id, status) VALUES(?,?,?,?)",
        (chat_id, tariff_key, payment_id, "waiting"),
    )
    conn.commit()
    conn.close()


def check_payments_loop() -> None:
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "SELECT id, chat_id, tariff_key, payment_id FROM pending_payments WHERE status='waiting'"
            )
            rows = c.fetchall()
            conn.close()

            for row_id, chat_id, tariff_key, payment_id in rows:
                try:
                    payment = Payment.find_one(payment_id)
                    if payment.status == "succeeded":
                        # Активируем тариф
                        _reward, message = activate_tariff(chat_id, tariff_key)
                        bot.send_message(chat_id, message)

                        # Обновляем статус
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        c.execute(
                            "UPDATE pending_payments SET status='activated' WHERE id=?",
                            (row_id,),
                        )
                        conn.commit()
                        conn.close()
                except Exception as exc:  # noqa: BLE001
                    print("Ошибка при проверке платежа:", exc)
        except Exception as exc:  # noqa: BLE001
            print("Ошибка в цикле проверки платежей:", exc)

        time.sleep(60)  # Проверяем раз в минуту


def start_payments_checker() -> None:
    init_payments_db()
    threading.Thread(target=check_payments_loop, daemon=True).start()
