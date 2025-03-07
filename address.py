import logging
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from config import TOKEN
import pandas as pd  # להדפסת טבלאות

# הגדרת הבוט
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

# ✅ יצירת כפתורים ראשיים
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 מחשבון משכנתא", callback_data="calc")],
        [InlineKeyboardButton(text="🏡 הוספת דירה", callback_data="add_listing")],
        [InlineKeyboardButton(text="🔍 חיפוש דירות", callback_data="search")],
        [InlineKeyboardButton(text="📈 סטטיסטיקות", callback_data="stats")],
        [InlineKeyboardButton(text="ℹ️ עזרה", callback_data="help")]
    ])
    return keyboard

# ✅ תגובה ל-/start עם כפתורים
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "ברוך הבא! אני כאן כדי לעזור לך עם דירות 🏡\nבחר פעולה מהתפריט למטה:",
        reply_markup=get_main_keyboard()
    )

# ✅ תגובה ללחיצה על כפתור עזרה
@dp.callback_query(lambda c: c.data == "help")
async def help_callback(callback: types.CallbackQuery):
    help_text = """
    ℹ️ **הסבר על הפקודות** ℹ️
    📊 **מחשבון משכנתא** - מאפשר לחשב החזר חודשי לפי סכום, ריבית ושנים.
    🏡 **הוספת דירה** - ניתן להוסיף דירות למאגר.
    🔍 **חיפוש דירות** - חיפוש לפי מחיר.
    📈 **סטטיסטיקות** - הצגת נתוני הדירות הקיימות.
    """
    await callback.message.edit_text(help_text, reply_markup=get_main_keyboard())

# ✅ מחשבון משכנתא עם טבלה
@dp.callback_query(lambda c: c.data == "calc")
async def calc_mortgage_callback(callback: types.CallbackQuery):
    await callback.message.answer("📊 **מחשבון משכנתא**\nשלח פקודה בפורמט הבא:\n\n`/calc סכום ריבית(%) שנים`")

@dp.message(Command("calc"))
async def calc_mortgage(message: types.Message):
    try:
        parts = message.text.split()
        if len(parts) != 4:
            await message.answer("📊 **שימוש:** /calc סכום ריבית(%) שנים")
            return

        loan = float(parts[1])
        interest = float(parts[2]) / 100 / 12
        years = int(parts[3])
        months = years * 12

        if loan <= 0 or interest <= 0 or years <= 0:
            await message.answer("⚠️ הערכים חייבים להיות חיוביים!")
            return

        payment = (loan * interest) / (1 - (1 + interest) ** -months)

        # יצירת טבלת תשלומים
        data = {
            "🔢 שנים": [i for i in range(1, years + 1)],
            "📉 החזר שנתי": [round(payment * 12 * i, 2) for i in range(1, years + 1)]
        }
        df = pd.DataFrame(data)

        # המרת הטבלה לטקסט
        table_text = df.to_string(index=False)

        await message.answer(f"💰 **ההחזר החודשי:** `{payment:,.2f} ש״ח`\n\n📊 **טבלת תשלומים:**\n```{table_text}```", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in calc_mortgage: {e}")
        await message.answer("❌ אירעה שגיאה בחישוב. נסה שוב.")

# ✅ תגובה ללחיצה על "הוספת דירה"
@dp.callback_query(lambda c: c.data == "add_listing")
async def add_listing_callback(callback: types.CallbackQuery):
    await callback.message.answer("🏡 **הוספת דירה**\nשלח את פרטי הדירה בפורמט הבא:\n\n`/add_listing תיאור מחיר`\n\nניתן להוסיף תמונה לאחר מכן.")

# ✅ חיפוש דירות
@dp.callback_query(lambda c: c.data == "search")
async def search_listing_callback(callback: types.CallbackQuery):
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

        cursor.execute("SELECT description, price FROM listings WHERE price BETWEEN ? AND ?", (min_price, max_price))
        rows = cursor.fetchall()

        if not rows:
            await message.answer("❌ לא נמצאו דירות בטווח המחירים הזה.")
            return

        results = "\n".join([f"🏡 {desc} - {price} ש״ח" for desc, price in rows])
        await message.answer(f"🔎 **תוצאות חיפוש:**\n{results}")

    except Exception as e:
        logging.error(f"Error in search_listing: {e}")
        await message.answer("❌ שגיאה בחיפוש. נסה שוב.")

# ✅ הצגת סטטיסטיקות
@dp.callback_query(lambda c: c.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*), MIN(price), MAX(price), AVG(price) FROM listings")
    count, min_price, max_price, avg_price = cursor.fetchone()
    if count == 0:
        await callback.message.answer("📊 אין דירות במאגר.")
    else:
        await callback.message.answer(f"📊 **סטטיסטיקות:**\n"
                                      f"🏠 סה״כ דירות: {count}\n"
                                      f"💰 מחיר מינימלי: {min_price} ש״ח\n"
                                      f"💰 מחיר מקסימלי: {max_price} ש״ח\n"
                                      f"💰 מחיר ממוצע: {int(avg_price)} ש״ח")

# ✅ הפעלת הבוט
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
