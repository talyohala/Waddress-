import logging
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.filters.state import StateFilter
from config import TOKEN
import pandas as pd

# הגדרת הבוט
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# חיבור למסד נתונים SQLite
conn = sqlite3.connect("real_estate.db", check_same_thread=False)
cursor = conn.cursor()

# ✅ יצירת טבלאות
cursor.execute("""
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    description TEXT,
    price INTEGER,
    photo_id TEXT,
    rating INTEGER DEFAULT NULL
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    last_active TIMESTAMP
)
""")
conn.commit()

# ✅ מקלדת ראשית
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 מחשבון משכנתא", callback_data="calc")],
        [InlineKeyboardButton(text="🏡 הוספת דירה", callback_data="add_listing")],
        [InlineKeyboardButton(text="🔍 חיפוש דירות", callback_data="search")],
        [InlineKeyboardButton(text="📈 סטטיסטיקות", callback_data="stats")],
        [InlineKeyboardButton(text="📝 דירוג דירות", callback_data="rate_listing")],
        [InlineKeyboardButton(text="ℹ️ עזרה", callback_data="help")]
    ])
    return keyboard

# ✅ הודעת ברוכים הבאים דינמית
def get_welcome_message():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "☀️ בוקר טוב!"
    elif 12 <= hour < 18:
        return "🌤️ צהריים טובים!"
    else:
        return "🌙 ערב טוב!"

# ✅ פקודת /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, last_active) VALUES (?, ?, ?)", 
                   (user_id, username, datetime.now()))
    conn.commit()
    await message.answer(f"{get_welcome_message()} {username}! אני כאן כדי לעזור לך עם דירות 🏡\nבחר פעולה מהתפריט למטה:",
                         reply_markup=get_main_keyboard())

# ✅ ניהול מצבים (FSM) - הוספת דירה
class AddListingStates(StatesGroup):
    DESCRIPTION = State()
    PRICE = State()
    PHOTO = State()

@dp.callback_query(lambda c: c.data == "add_listing")
async def add_listing_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🏡 **הוספת דירה**\nשלח את תיאור הדירה:")
    await state.set_state(AddListingStates.DESCRIPTION)

@dp.message(StateFilter(AddListingStates.DESCRIPTION))
async def add_listing_description(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['description'] = message.text
    await message.answer("💰 שלח את המחיר:")
    await state.set_state(AddListingStates.PRICE)

@dp.message(StateFilter(AddListingStates.PRICE))
async def add_listing_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
        async with state.proxy() as data:
            data['price'] = price
        await message.answer("📸 שלח תמונה של הדירה (או הקלד /skip כדי לדלג).")
        await state.set_state(AddListingStates.PHOTO)
    except ValueError:
        await message.answer("⚠️ יש להזין מחיר חוקי.")

@dp.message(StateFilter(AddListingStates.PHOTO), F.content_type == ContentType.PHOTO)
async def add_listing_photo(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['photo_id'] = message.photo[-1].file_id
    await save_listing(message, state)

@dp.message(Command("skip"), StateFilter(AddListingStates.PHOTO))
async def skip_listing_photo(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['photo_id'] = None
    await save_listing(message, state)

async def save_listing(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        cursor.execute("INSERT INTO listings (user_id, description, price, photo_id) VALUES (?, ?, ?, ?)",
                       (message.from_user.id, data['description'], data['price'], data.get('photo_id')))
        conn.commit()
    await message.answer("✅ הדירה נוספה בהצלחה!", reply_markup=get_main_keyboard())
    await state.clear()

# ✅ הפעלת הבוט
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
