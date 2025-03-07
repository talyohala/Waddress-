import logging
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from config import TOKEN  # ייבוא ה-TOKEN מהקובץ config.py

# הגדרת הבוט וה-Dispatcher
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# חיבור למסד נתונים SQLite
conn = sqlite3.connect("real_estate.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    description TEXT,
    price INTEGER,
    photo_id TEXT
)
""")
conn.commit()

# מחלקות למצבים
class AddListingStates(StatesGroup):
    DESCRIPTION = State()
    PRICE = State()
    PHOTO = State()

class SearchListingStates(StatesGroup):
    MIN_PRICE = State()
    MAX_PRICE = State()

# מחשבון משכנתא
@dp.message(Command("calc"))
async def calc_mortgage(message: types.Message):
    try:
        parts = message.text.split()
        if len(parts) != 4:
            await message.answer("שימוש: /calc סכום ריבית(%) שנים")
            return

        loan = float(parts[1])
        interest = float(parts[2]) / 100 / 12
        years = int(parts[3])
        months = years * 12

        if loan <= 0 or interest <= 0 or years <= 0:
            await message.answer("הערכים חייבים להיות גדולים מ-0.")
            return

        payment = (loan * interest) / (1 - (1 + interest) ** -months)
        await message.answer(f"ההחזר החודשי שלך: {payment:,.2f} ש״ח")
    except Exception as e:
        logging.error(f"Error in calc_mortgage: {e}")
        await message.answer("אירעה שגיאה בחישוב המשכנתא. אנא נסה שוב.")

# פקודת /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("ברוך הבא! אני כאן כדי לעזור לך עם דירות 🏡\nשלח /help כדי לראות את כל הפקודות.")

# פקודת עזרה
@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = """
    פקודות זמינות:
    /calc סכום ריבית(%) שנים - חישוב משכנתא
    /add_listing - הוספת דירה למאגר
    /listings - הצגת כל הדירות
    /search - חיפוש דירות לפי טווח מחירים
    /delete_listing id - מחיקת דירה
    /stats - הצגת סטטיסטיקות
    """
    await message.answer(help_text)

# הפעלת הבוט עם aiogram 3.x
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
