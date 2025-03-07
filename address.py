import logging
import asyncio
import aiosqlite
import os
import psutil
from datetime import datetime
from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
from enum import Enum
from functools import lru_cache
import random

# ✅ טעינת משתני סביבה
load_dotenv()
TOKEN = os.getenv("TOKEN")

# ✅ הגדרת הבוט
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ✅ ניהול תהליכים ישנים
def kill_old_processes():
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if "python" in proc.info['name'] and proc.info['cmdline']:
                if any("address.py" in cmd for cmd in proc.info['cmdline']) and proc.info['pid'] != current_pid:
                    logging.info(f"🔴 סגירת תהליך ישן: {proc.info['pid']}")
                    proc.terminate()
                    proc.wait(timeout=3)
                    if proc.is_running():
                        proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

kill_old_processes()

# ✅ הגדרת Enum לקטגוריות
class Category(Enum):
    APARTMENT = "דירה"
    HOUSE = "בית"
    LAND = "קרקע"

# ✅ הודעות ברוכים הבא דינמיות
welcome_messages = [
    "☀️ בוקר טוב! מוכנים למצוא את דירת החלומות שלכם? 🏡",
    "🌤️ צהריים טובים! אולי זה הזמן לרכוש דירה חדשה? 🏠",
    "🌙 ערב טוב! דירות חמות מחכות לכם 🔥"
]

@lru_cache(maxsize=100)
def get_welcome_message():
    return random.choice(welcome_messages)

# ✅ מקלדת כפתורים עם קטגוריות
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 מחשבון משכנתא", callback_data="calc")],
        [InlineKeyboardButton(text="🏡 הוספת דירה", callback_data="add_listing")],
        [InlineKeyboardButton(text="🔍 חיפוש דירות", callback_data="search")],
        [InlineKeyboardButton(text="📈 סטטיסטיקות", callback_data="stats")],
        [InlineKeyboardButton(text="📝 דירוג דירות", callback_data="rate_listing")],
        [InlineKeyboardButton(text="ℹ️ עזרה", callback_data="help")]
    ])

# ✅ חיבור למסד נתונים SQLite
@asynccontextmanager
async def get_db():
    async with aiosqlite.connect("real_estate.db") as db:
        db.row_factory = aiosqlite.Row
        yield db

# ✅ יצירת טבלאות
async def init_db():
    async with get_db() as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            description TEXT,
            price INTEGER,
            photo_id TEXT,
            category TEXT,
            rating INTEGER DEFAULT NULL
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            last_active TIMESTAMP
        )
        """)
        await db.commit()

# ✅ פקודת /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name or ""

    full_name = f"{first_name} {last_name}".strip() if first_name else (username if username else f"משתמש {user_id}")

    async with get_db() as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, last_active) VALUES (?, ?, ?, ?, ?)",
                         (user_id, username, first_name, last_name, datetime.now()))
        await db.commit()

    await message.answer(f"{get_welcome_message()} {full_name}! 🎉\nבחר פעולה מהתפריט למטה:",
                         reply_markup=get_main_keyboard())

# ✅ מחשבון משכנתא
@dp.callback_query(F.data == "calc")
async def calc_callback(callback: types.CallbackQuery):
    await callback.message.answer("📊 **מחשבון משכנתא**\nשלח פקודה בפורמט:\n\n`/calc סכום ריבית(%) שנים`")

@dp.message(Command("calc"))
async def calc_mortgage(message: types.Message):
    try:
        parts = message.text.split()
        if len(parts) != 4:
            await message.answer("📊 **שימוש נכון:** /calc סכום ריבית(%) שנים")
            return

        loan = float(parts[1])
        interest = float(parts[2]) / 100 / 12
        years = int(parts[3])
        months = years * 12

        if loan <= 0 or interest <= 0 or years <= 0:
            await message.answer("⚠️ הערכים חייבים להיות חיוביים!")
            return

        payment = (loan * interest) / (1 - (1 + interest) ** -months)

        await message.answer(f"💰 **ההחזר החודשי:** `{payment:,.2f} ש״ח`", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in calc_mortgage: {e}")
        await message.answer("❌ אירעה שגיאה בחישוב. נסה שוב.")

# ✅ חיפוש דירות
@dp.callback_query(F.data == "search")
async def search_callback(callback: types.CallbackQuery):
    await callback.message.answer("🔍 **חיפוש דירות**\nשלח פקודה בפורמט:\n\n`/search מינימום מחיר מקסימום מחיר`")

@dp.message(Command("search"))
async def search_listing(message: types.Message):
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("🔍 **שימוש נכון:** /search מינימום מקסימום")
            return

        min_price = int(parts[1])
        max_price = int(parts[2])

        async with get_db() as db:
            cursor = await db.execute("SELECT description, price, photo_id FROM listings WHERE price BETWEEN ? AND ?", (min_price, max_price))
            rows = await cursor.fetchall()

        if not rows:
            await message.answer("❌ לא נמצאו דירות בטווח המחירים הזה.")
            return

        for desc, price, photo_id in rows:
            if photo_id:
                await message.answer_photo(photo_id, caption=f"🏡 {desc} - {price} ש״ח")
            else:
                await message.answer(f"🏡 {desc} - {price} ש״ח")

    except Exception as e:
        logging.error(f"Error in search_listing: {e}")
        await message.answer("❌ שגיאה בחיפוש. נסה שוב.")

# ✅ מטפל להודעות רגילות
@dp.message(F.text)
async def handle_message(message: types.Message):
    await message.answer(f"היי! קיבלתי את ההודעה שלך: {message.text}")

# ✅ מטפל להודעות לא ידועות
@dp.message()
async def unknown_message(message: types.Message):
    await message.answer("לא הבנתי את ההודעה שלך. נסה להשתמש בפקודות כמו /start או /help.")

# ✅ הפעלת הבוט
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
