import logging
import asyncio
import aiosqlite
import os
import psutil
from datetime import datetime
from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import random

# ✅ טעינת משתני סביבה
load_dotenv()
TOKEN = os.getenv("TOKEN")

# ✅ בדיקת תקינות ה-TOKEN
if not TOKEN:
    raise ValueError("❌ שגיאה: TOKEN לא מוגדר! בדוק את קובץ ה-.env שלך.")

# ✅ הגדרת הבוט וה-Dispatcher
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ✅ ניהול תהליכים ישנים (מונע התנגשויות של הבוט)
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

# ✅ חיבור למסד נתונים SQLite
@asynccontextmanager
async def get_db():
    async with aiosqlite.connect("real_estate.db") as db:
        db.row_factory = aiosqlite.Row
        yield db

# ✅ יצירת טבלאות במסד הנתונים
async def init_db():
    async with get_db() as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            last_active TIMESTAMP
        )
        """)
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
        await db.commit()

# ✅ הודעות ברוכים הבאים דינמיות
welcome_messages = [
    "☀️ בוקר טוב! מוכנים למצוא את דירת החלומות שלכם? 🏡",
    "🌤️ צהריים טובים! אולי זה הזמן לרכוש דירה חדשה? 🏠",
    "🌙 ערב טוב! דירות חמות מחכות לכם 🔥"
]

def get_welcome_message():
    return random.choice(welcome_messages)

# ✅ כפתורי קטגוריות ראשיים
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏡 דירות ונכסים", callback_data="category_real_estate")],
        [InlineKeyboardButton(text="📊 מחשבון משכנתא", callback_data="category_mortgage")],
        [InlineKeyboardButton(text="📈 סטטיסטיקות", callback_data="category_stats")],
        [InlineKeyboardButton(text="ℹ️ עזרה", callback_data="help")]
    ])

# ✅ כפתורי תפריט משנה – דירות ונכסים
def get_real_estate_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 חיפוש דירות", callback_data="search")],
        [InlineKeyboardButton(text="➕ הוספת דירה", callback_data="add_listing")],
        [InlineKeyboardButton(text="📜 רשימת הדירות שלי", callback_data="my_listings")],
        [InlineKeyboardButton(text="🔙 חזור לתפריט ראשי", callback_data="main_menu")]
    ])

# ✅ כפתורי תפריט משנה – מחשבוני משכנתא
def get_mortgage_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 חישוב משכנתא", callback_data="calc")],
        [InlineKeyboardButton(text="💰 חישוב החזר כולל", callback_data="total_payment")],
        [InlineKeyboardButton(text="🔙 חזור לתפריט ראשי", callback_data="main_menu")]
    ])

# ✅ כפתורי תפריט משנה – סטטיסטיקות
def get_stats_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 סטטיסטיקות דירות", callback_data="stats")],
        [InlineKeyboardButton(text="🏆 הדירות המדורגות ביותר", callback_data="top_rated")],
        [InlineKeyboardButton(text="🔙 חזור לתפריט ראשי", callback_data="main_menu")]
    ])

# ✅ ניווט בין קטגוריות
@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text("🔝 חזרת לתפריט הראשי. בחר פעולה:", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "category_real_estate")
async def real_estate_menu(callback: CallbackQuery):
    await callback.message.edit_text("🏡 **תפריט דירות ונכסים**\nבחר פעולה:", reply_markup=get_real_estate_keyboard())

@dp.callback_query(F.data == "category_mortgage")
async def mortgage_menu(callback: CallbackQuery):
    await callback.message.edit_text("📊 **תפריט מחשבוני משכנתא**\nבחר פעולה:", reply_markup=get_mortgage_keyboard())

@dp.callback_query(F.data == "category_stats")
async def stats_menu(callback: CallbackQuery):
    await callback.message.edit_text("📈 **תפריט סטטיסטיקות**\nבחר פעולה:", reply_markup=get_stats_keyboard())

# ✅ פקודת /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "משתמש"
    last_name = message.from_user.last_name or ""

    full_name = f"{first_name} {last_name}".strip()

    async with get_db() as db:
        await db.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, last_active) 
        VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, first_name, last_name, datetime.now()))
        await db.commit()

    await message.answer(f"{get_welcome_message()} {full_name}! 🎉\nבחר פעולה מהתפריט למטה:",
                         reply_markup=get_main_keyboard())

# ✅ פקודת עזרה
@dp.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    await callback.message.edit_text("ℹ️ **עזרה**\nבחר קטגוריה למידע נוסף:", reply_markup=get_main_keyboard())

# ✅ הפעלת הבוט
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()  # יצירת טבלאות במסד הנתונים
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
