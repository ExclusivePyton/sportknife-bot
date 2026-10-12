"""Живое обновление экранов турниров.

Бот запоминает, у каких пользователей сейчас открыт экран «Турниры» / карточка турнира / выбор стороны,
и при любом изменении (регистрация, выход, смена стороны, кик, старт, завершение) сам редактирует
эти сообщения. Поэтому счётчик 1/2 → 2/2 меняется на всех устройствах без повторного входа.

Реестр хранится в памяти: после перезапуска бота уже открытые старые сообщения обновляться
перестанут, пока игрок снова не откроет «🏆 Турниры».
"""
import asyncio
import logging
import time
from collections import OrderedDict

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

log = logging.getLogger("live")

MAX_VIEWS = 5000
TTL_SECONDS = 6 * 3600
EDIT_DELAY = 0.05  # пауза между правками, чтобы не упереться в лимиты Telegram

# (chat_id, message_id) -> {"kind": "list" | "detail" | "pick_reg" | "pick_sw", "tid": int | None, "user_id": int | None}
_views: "OrderedDict[tuple[int, int], dict]" = OrderedDict()
_pending: set = set()
_tasks: set = set()


def track(chat_id: int, message_id: int, kind: str, tid: int | None = None, user_id: int | None = None, media: bool = False) -> None:
    key = (chat_id, message_id)
    _views[key] = {"kind": kind, "tid": tid, "user_id": user_id, "ts": time.time(), "media": media}
    _views.move_to_end(key)
    while len(_views) > MAX_VIEWS:
        _views.popitem(last=False)


def untrack(chat_id: int, message_id: int) -> None:
    _views.pop((chat_id, message_id), None)


async def _edit(bot, chat_id: int, message_id: int, text: str, kb, media: bool = False) -> bool:
    """True — сообщение живо (или не изменилось); False — его больше нельзя редактировать."""
    for attempt in range(2):
        try:
            if media:
                await bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=text, reply_markup=kb)
            else:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=kb)
            return True
        except TelegramRetryAfter as e:
            if attempt == 0:
                await asyncio.sleep(e.retry_after + 0.1)
                continue
            return True
        except TelegramBadRequest as e:
            return "not modified" in str(e).lower()
        except TelegramForbiddenError:
            return False
        except Exception:
            log.exception("live edit failed")
            return True
    return True


async def _refresh(bot, tid: int | None) -> None:
    # импорт здесь, чтобы не было циклической зависимости с handlers.tournaments
    from app.handlers.tournaments import render_list, render_tour, render_pick

    now = time.time()
    items = list(_views.items())
    list_cache = None
    for (chat_id, message_id), v in items:
        if now - v["ts"] > TTL_SECONDS:
            _views.pop((chat_id, message_id), None)
            continue
        try:
            if v["kind"] == "list":
                if list_cache is None:
                    list_cache = await render_list()
                text, kb = list_cache
            elif tid is not None and v["tid"] == tid:
                if v["kind"] == "detail":
                    text, kb, _photo = await render_tour(tid, v["user_id"])
                elif v["kind"] == "pick_reg":
                    text, kb, _photo = await render_pick(tid, v["user_id"], "reg")
                elif v["kind"] == "pick_sw":
                    text, kb, _photo = await render_pick(tid, v["user_id"], "sw")
                else:
                    continue
            else:
                continue
        except Exception:
            log.exception("live render failed")
            continue
        alive = await _edit(bot, chat_id, message_id, text, kb, media=bool(v.get("media")))
        if not alive:
            _views.pop((chat_id, message_id), None)
        await asyncio.sleep(EDIT_DELAY)


async def _run(bot, tid: int | None) -> None:
    try:
        await asyncio.sleep(0.3)  # собираем несколько быстрых изменений в одно обновление
        _pending.discard(tid)
        await _refresh(bot, tid)
    except Exception:
        _pending.discard(tid)
        log.exception("live refresh failed")


def schedule_refresh(bot, tid: int | None = None) -> None:
    """Обновить у всех открытые экраны турнира tid (и общий список турниров).
    tid=None — обновить только списки (например, после создания нового турнира)."""
    if tid in _pending:
        return
    _pending.add(tid)
    task = asyncio.create_task(_run(bot, tid))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
