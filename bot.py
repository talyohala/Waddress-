import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

TOKEN = "הכנס_את_הטוקן_שלך"
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# חיבור למסד נתונים SQLite
conn = sqlite3.connect("real_estate.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    description TEXT,
    price INTEGER
)
""")
conn.commit()

# מחשבון משכנתא
@dp.message_handler(commands=['calc'])
async def calc_mortgage(message: types.Message):
    try:
        parts = message.text.split()
        loan = float(parts[1])  # סכום ההלוואה
        interest = float(parts[2]) / 100 / 12  # ריבית חודשית
        years = int(parts[3])  # משך שנים
        months = years * 12
        payment = (loan * interest) / (1 - (1 + interest) ** -months)
        await message.reply(f"ההחזר החודשי שלך: {payment:,.2f} ש״ח")
    except:
        await message.reply("שימוש: /calc סכום ריבית(%) שנים")

# הוספת דירה למאגר
@dp.message_handler(commands=['add_listing'])
async def add_listing(message: types.Message):
    user_id = message.from_user.id
    text = message.text.replace("/add_listing ", "")
    price = int(text.split()[-1])
    description = text.replace(str(price), "").strip()

    cursor.execute("INSERT INTO listings (user_id, description, price) VALUES (?, ?, ?)", (user_id, description, price))
    conn.commit()
    
    await message.reply("הדירה נוספה בהצלחה!")

# הצגת דירות
@dp.message_handler(commands=['listings'])
async def list_listings(message: types.Message):
    cursor.execute("SELECT description, price FROM listings")
    rows = cursor.fetchall()
    if rows:
        response = "\n".join([f"{desc} - {price} ש״ח" for desc, price in rows])
    else:
        response = "אין כרגע דירות."
    await message.reply(response)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    executor.start_polling(dp, skip_updates=True)
