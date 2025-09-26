"""Dedicated process for polling and processing payments."""

from __future__ import annotations

import multiprocessing as mp
import time

from settings import bot
import payments_polling

_PAYMENTS_PROCESS: mp.Process | None = None


def payments_worker() -> None:
    """Background loop that periodically checks payment status."""
    payments_polling.init_payments_db()
    while True:
        try:
            payments_polling.check_payments(bot)
        except Exception as exc:  # noqa: BLE001
            print(f"[payments_worker] Ошибка: {exc}")
        time.sleep(10)


def start_payments_worker() -> None:
    """Запускает отдельный процесс для проверки платежей (idempotent)."""
    global _PAYMENTS_PROCESS
    if _PAYMENTS_PROCESS is not None and _PAYMENTS_PROCESS.is_alive():
        return
    process = mp.Process(target=payments_worker, daemon=True)
    process.start()
    _PAYMENTS_PROCESS = process


__all__ = ["payments_worker", "start_payments_worker"]
