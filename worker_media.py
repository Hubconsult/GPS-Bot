"""Background worker for generating media files without blocking the bot."""

from __future__ import annotations

import io
import multiprocessing as mp
from multiprocessing.process import BaseProcess
from typing import Any, Optional

from settings import bot
import media_utils

_MEDIA_QUEUE: Optional[mp.Queue] = None
_MEDIA_PROCESS: Optional[BaseProcess] = None


def media_worker(task_queue: "mp.Queue") -> None:
    """Worker loop that processes media generation tasks."""
    while True:
        chat_id, task_type, payload = task_queue.get()
        try:
            if task_type == "pdf":
                pdf_bytes = media_utils.make_pdf(str(payload or ""))
                bot.send_document(
                    chat_id,
                    io.BytesIO(pdf_bytes),
                    visible_file_name="document.pdf",
                    caption="PDF готов ✅",
                )
            elif task_type == "excel":
                xlsx_bytes = media_utils.make_excel(str(payload or ""))
                bot.send_document(
                    chat_id,
                    io.BytesIO(xlsx_bytes),
                    visible_file_name="data.xlsx",
                    caption="Excel готов ✅",
                )
            elif task_type == "pptx":
                pptx_bytes = media_utils.make_pptx(str(payload or ""))
                bot.send_document(
                    chat_id,
                    io.BytesIO(pptx_bytes),
                    visible_file_name="slides.pptx",
                    caption="Презентация готова ✅",
                )
            else:
                bot.send_message(chat_id, f"⚠️ Неизвестная задача: {task_type}")
        except Exception as exc:  # noqa: BLE001 - хотим поймать любые сбои
            bot.send_message(chat_id, f"⚠️ Ошибка обработки медиа: {exc}")


def _ensure_queue() -> "mp.Queue":
    global _MEDIA_QUEUE
    if _MEDIA_QUEUE is None:
        _MEDIA_QUEUE = mp.Queue()
    return _MEDIA_QUEUE


def start_media_worker() -> "mp.Queue":
    """Ensure that the media worker process is running and return its queue."""
    global _MEDIA_PROCESS
    queue = _ensure_queue()
    if _MEDIA_PROCESS is None or not _MEDIA_PROCESS.is_alive():
        _MEDIA_PROCESS = mp.Process(target=media_worker, args=(queue,), daemon=True)
        _MEDIA_PROCESS.start()
    return queue


def enqueue_media_task(chat_id: int, task_type: str, payload: Any) -> None:
    """Schedule a media generation task for asynchronous processing."""
    queue = start_media_worker()
    queue.put((chat_id, task_type, payload))


__all__ = ["enqueue_media_task", "start_media_worker", "media_worker"]


if __name__ == "__main__":
    queue = mp.Queue()
    media_worker(queue)
