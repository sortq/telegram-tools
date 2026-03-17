import asyncio

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config import TELEGRAM_ADMIN_ID, TELEGRAM_BOT_TOKEN
from database import get_connection


if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


def update_request_status(request_id: int, status: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE requests SET status = ? WHERE id = ?", (status, request_id))
        conn.commit()


def get_requests_by_status(status: str) -> list[tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, bot, comment, status, developer FROM requests WHERE status = ? ORDER BY id DESC",
            (status,),
        )
        return cursor.fetchall()


def build_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Заявки")]],
        resize_keyboard=True,
    )


def build_requests_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟡 Новые", callback_data="list:new")],
            [InlineKeyboardButton(text="🔵 В работе", callback_data="list:in_progress")],
            [InlineKeyboardButton(text="✅ Выполненные", callback_data="list:done")],
        ]
    )


def build_request_keyboard(request_id: int, username: str) -> InlineKeyboardMarkup:
    rows = []
    if username not in {"", "-"}:
        rows.append([InlineKeyboardButton(text="Связаться", url=f"https://t.me/{username.replace('@', '')}")])

    rows.append(
        [
            InlineKeyboardButton(text="Принять", callback_data=f"accept:{request_id}"),
            InlineKeyboardButton(text="Выполнено", callback_data=f"done:{request_id}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_done_button(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Выполнено", callback_data=f"done:{request_id}")]]
    )


def build_status_keyboard(status: str, request_id: int) -> InlineKeyboardMarkup:
    labels = {
        "in_progress": "🔵 Заявка в работе",
        "done": "✅ Заявка выполнена",
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=labels[status], callback_data=f"status:{request_id}")]]
    )


def format_request_text(request_id: int, username: str, bot_name: str, comment: str, developer: str) -> str:
    return f"""📩 Заявка #{request_id}

👤 Telegram
{username}

🤖 Бот
{bot_name}

💬 Комментарий
{comment}

🧑‍💻 Разработчик
{developer or "-"}
"""


@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Бот заявок запущен", reply_markup=build_main_keyboard())


@dp.message(Command("requests"))
@dp.message(F.text == "Заявки")
async def show_requests(message: types.Message):
    await message.answer("📚 Выберите категорию заявок:", reply_markup=build_requests_menu())


async def send_request(request_id: int, username: str, bot_name: str, comment: str):
    safe_username = username if username and username != "-" else "-"
    safe_comment = comment if comment and comment != "-" else "-"
    text = format_request_text(request_id, safe_username, bot_name, safe_comment, "")
    await bot.send_message(
        TELEGRAM_ADMIN_ID,
        text,
        reply_markup=build_request_keyboard(request_id, safe_username),
    )


@dp.callback_query(F.data.startswith("accept:"))
async def accept_request(callback: types.CallbackQuery):
    request_id = int(callback.data.split(":", 1)[1])
    update_request_status(request_id, "in_progress")
    await callback.message.edit_reply_markup(reply_markup=build_status_keyboard("in_progress", request_id))
    await callback.answer("Заявка принята")


@dp.callback_query(F.data.startswith("done:"))
async def complete_request(callback: types.CallbackQuery):
    request_id = int(callback.data.split(":", 1)[1])
    update_request_status(request_id, "done")
    await callback.message.edit_reply_markup(reply_markup=build_status_keyboard("done", request_id))
    await callback.answer("Заявка выполнена")


@dp.callback_query(F.data.startswith("status:"))
async def noop_status(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("list:"))
async def show_requests_by_status(callback: types.CallbackQuery):
    status = callback.data.split(":", 1)[1]
    requests = get_requests_by_status(status)

    titles = {
        "new": "🟡 Новые заявки",
        "in_progress": "🔵 Заявки в работе",
        "done": "✅ Выполненные заявки",
    }
    title = titles.get(status, "Заявки")

    if not requests:
        await callback.message.answer(f"{title}\n\nПока пусто.")
        await callback.answer()
        return

    await callback.message.answer(title)

    for request_id, username, bot_name, comment, _, developer in requests:
        reply_markup = build_done_button(request_id) if status == "in_progress" else None
        await callback.message.answer(
            format_request_text(
                request_id,
                username or "-",
                bot_name or "-",
                comment or "-",
                developer or "",
            ),
            reply_markup=reply_markup,
        )

    await callback.answer()


async def main():
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
