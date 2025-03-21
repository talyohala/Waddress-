import os
import sys
import json
import logging
import random
import sqlite3
import asyncio
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from contextlib import closing
from datetime import datetime, timedelta

# הגדרת logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# טעינת משתנים מהסביבה
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8034267278:AAGUWCyTEAK_ub3Sk9AOtz9mQ1Ihl6Ukxh8").strip()
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
ADMIN_ID = 7663483746  # המספר שלך קבוע ישירות

if not TOKEN or ":" not in TOKEN:
    logger.error("❌ שגיאה: TOKEN אינו תקין! ודא שהוא מוגדר כראוי.")
    sys.exit(1)

if not TMDB_API_KEY:
    logger.error("❌ שגיאה: TMDB_API_KEY לא מוגדר! ודא שהכנסת API Key תקין.")
    sys.exit(1)

# יצירת אובייקטים של הבוט עם תמיכה ב-Aiogram 3.7
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

MOVIES_JSON_PATH = "/data/data/com.termux/files/home/movies_links.json"
VLC_LINK = "http://troya.info/pl/13/grdgiekhp3dla/playlist.m3u8"

# מילון לשמירת תוצאות חיפוש עבור כל משתמש
user_data = {}

# פונקציה לטעינת רשימת הסרטים
def load_movies_links():
    if os.path.exists(MOVIES_JSON_PATH):  
        with open(MOVIES_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {}  

movies_links = load_movies_links()

# פונקציה לקבלת חיבור למסד נתונים
def get_db_connection():
    return sqlite3.connect("bot_users.db", check_same_thread=False)

# יצירת מסד הנתונים אם לא קיים
def init_db():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_blocked INTEGER DEFAULT 0
        );
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            movie_id INTEGER,
            PRIMARY KEY (user_id, movie_id)
        );
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS views (
            user_id INTEGER,
            movie_id INTEGER,
            views INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, movie_id)
        );
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_history (
            user_id INTEGER,
            query TEXT,
            search_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS live_access (
            user_id INTEGER PRIMARY KEY,
            approved INTEGER DEFAULT 0,
            approval_expiry TIMESTAMP,
            is_blocked INTEGER DEFAULT 0
        );
        ''')
        conn.commit()

init_db()

# ✅ **תיקון המקלדת בצורה הנכונה**
def set_custom_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔥 המלצות חמות"), KeyboardButton(text="🏆 הנצפים ביותר")],
            [KeyboardButton(text="⭐ מועדפים"), KeyboardButton(text="🎲 סרט אקראי")],
            [KeyboardButton(text="📺 צפייה בלייב")]
        ],
        resize_keyboard=True
    )

# 📌 **פקודה /start**
@dp.message(Command("start"))
async def start_command(message: Message):
    user_id = message.chat.id
    username = message.from_user.username

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()

    # ברכות משתנות
    greetings = [
        "🎬 ברוך הבא לבוט הסרטים של TBOX!",
        "🍿 היי! מוכנים לצפייה בסרטים מדהימים?",
        "🌟 ברוכים הבאים ל-TBOX, המקום הכי טוב לסרטים!",
        "🎥 שלום! בואו נתחיל את החוויה הקולנועית שלכם."
    ]
    greeting = random.choice(greetings)

    await message.answer(greeting, reply_markup=set_custom_keyboard())

# 📌 **טיפול בכפתורים בתפריט הראשי**
@dp.message(lambda message: message.text in ["🔥 המלצות חמות", "🏆 הנצפים ביותר", "⭐ מועדפים", "🎲 סרט אקראי"])
async def handle_main_menu(message: Message):
    user_id = message.chat.id
    if message.text == "🔥 המלצות חמות":
        await get_hot_recommendations(user_id)
    elif message.text == "🏆 הנצפים ביותר":
        await get_top_rated(user_id)
    elif message.text == "⭐ מועדפים":
        await show_favorites(user_id)
    elif message.text == "🎲 סרט אקראי":
        await get_random_movie(user_id)

# 📌 **חיפוש סרטים לפי שם**
@dp.message(lambda message: message.text and not message.text.startswith("/"))
async def search_movie_by_name(message: Message):
    user_id = message.chat.id
    query = message.text.strip()

    # שמירת החיפוש בהיסטוריה
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO search_history (user_id, query) VALUES (?, ?)", (user_id, query))
        conn.commit()

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&language=he-IL&query={query}"
    response = requests.get(url)
    response.raise_for_status()
    movies = response.json().get("results", [])

    if not movies:
        await message.answer("❌ לא נמצאו תוצאות לחיפוש.")
        return

    user_data[user_id] = {
        "movies": movies,
        "current_index": 0
    }

    await send_movie_details(user_id, movies[0])

# 📌 **המלצות חמות**
async def get_hot_recommendations(user_id):
    url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=he-IL"
    response = requests.get(url)
    response.raise_for_status()
    movies = response.json().get("results", [])

    if not movies:
        await bot.send_message(user_id, "❌ לא נמצאו המלצות חמות.")
        return

    user_data[user_id] = {
        "movies": movies,
        "current_index": 0
    }

    await send_movie_details(user_id, movies[0])

# 📌 **הנצפים ביותר**
async def get_top_rated(user_id):
    url = f"https://api.themoviedb.org/3/movie/top_rated?api_key={TMDB_API_KEY}&language=he-IL"
    response = requests.get(url)
    response.raise_for_status()
    movies = response.json().get("results", [])

    if not movies:
        await bot.send_message(user_id, "❌ לא נמצאו סרטים נצפים ביותר.")
        return

    user_data[user_id] = {
        "movies": movies,
        "current_index": 0
    }

    await send_movie_details(user_id, movies[0])

# 📌 **מועדפים**
async def show_favorites(user_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT movie_id FROM favorites WHERE user_id = ?", (user_id,))
        favorites = cursor.fetchall()

    if not favorites:
        await bot.send_message(user_id, "❌ אין לך סרטים מועדפים.")
        return

    movies = []
    for fav in favorites:
        movie_id = fav[0]
        url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=he-IL"
        response = requests.get(url)
        if response.status_code == 200:
            movies.append(response.json())

    if not movies:
        await bot.send_message(user_id, "❌ לא נמצאו סרטים מועדפים.")
        return

    user_data[user_id] = {
        "movies": movies,
        "current_index": 0
    }

    await send_movie_details(user_id, movies[0])

# 📌 **סרט אקראי**
async def get_random_movie(user_id):
    url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=he-IL"
    response = requests.get(url)
    response.raise_for_status()
    movies = response.json().get("results", [])

    if not movies:
        await bot.send_message(user_id, "❌ לא נמצאו סרטים אקראיים.")
        return

    random_movies = random.sample(movies, min(5, len(movies)))
    user_data[user_id] = {
        "movies": random_movies,
        "current_index": 0
    }

    await send_movie_details(user_id, random_movies[0])

# 📌 **שליחת פרטי סרט**
async def send_movie_details(user_id, movie, edit_message_id=None):
    title = movie["title"]
    movie_id = movie["id"]
    
    watch_url = movies_links.get(title)
    trailer_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}&language=he-IL"
    trailer_response = requests.get(trailer_url)
    trailer_data = trailer_response.json().get("results", [])
    trailer_link = f"https://www.youtube.com/watch?v={trailer_data[0]['key']}" if trailer_data else None
    
    buttons = []
    if watch_url:
        buttons.append([InlineKeyboardButton(text="🍿 צפייה מהנה", url=watch_url)])
    if trailer_link:
        buttons.append([InlineKeyboardButton(text="🎥 צפייה בטריילר", url=trailer_link)])
    
    # בדיקה אם הסרט כבר במועדפים
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM favorites WHERE user_id = ? AND movie_id = ?", (user_id, movie_id))
        is_favorite = cursor.fetchone()

    if is_favorite:
        buttons.append([InlineKeyboardButton(text="❌ הסר ממועדפים", callback_data=f"unfavorite_{movie_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="⭐ הוסף למועדפים", callback_data=f"favorite_{movie_id}")])
    
    buttons.append([InlineKeyboardButton(text="⬅️ הקודם", callback_data=f"prev_{movie_id}"),
                    InlineKeyboardButton(text="➡️ הבא", callback_data=f"next_{movie_id}")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = f"🎬 <b>{title}</b>\n⭐ דירוג TMDB: {movie.get('vote_average', 0)}\n"
    
    poster_url = f"https://image.tmdb.org/t/p/w300{movie.get('poster_path', '')}"
    
    # בדיקה אם הקישור לתמונה תקין
    try:
        logger.info(f"🖼️ בדיקת קישור לתמונה: {poster_url}")
        response = requests.head(poster_url)
        if response.status_code != 200:
            logger.error(f"❌ קישור לתמונה לא תקין: {poster_url}")
            poster_url = None  # אם הקישור לא תקין, נבטל את שליחת התמונה
    except Exception as e:
        logger.error(f"❌ שגיאה בבדיקת הקישור לתמונה: {e}")
        poster_url = None

    if edit_message_id:
        if poster_url:
            await bot.edit_message_media(chat_id=user_id, message_id=edit_message_id, media=types.InputMediaPhoto(media=poster_url, caption=text, parse_mode=ParseMode.HTML), reply_markup=markup)
        else:
            await bot.edit_message_text(chat_id=user_id, message_id=edit_message_id, text=text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        if poster_url:
            await bot.send_photo(user_id, poster_url, caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await bot.send_message(user_id, text, reply_markup=markup, parse_mode=ParseMode.HTML)

# 📌 **הוספה למועדפים**
@dp.callback_query(lambda call: call.data.startswith("favorite_"))
async def add_to_favorites(call: types.CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    user_id = call.from_user.id

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO favorites (user_id, movie_id) VALUES (?, ?)", (user_id, movie_id))
        conn.commit()

    await call.answer("✅ הסרט נוסף למועדפים!")

# 📌 **הסרה ממועדפים**
@dp.callback_query(lambda call: call.data.startswith("unfavorite_"))
async def remove_from_favorites(call: types.CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    user_id = call.from_user.id

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE user_id = ? AND movie_id = ?", (user_id, movie_id))
        conn.commit()

    await call.answer("✅ הסרט הוסר מהמועדפים!")

# 📌 **ניווט בין סרטים**
@dp.callback_query(lambda call: call.data.startswith("prev_") or call.data.startswith("next_"))
async def navigate_movies(call: types.CallbackQuery):
    user_id = call.from_user.id
    if user_id not in user_data:
        await call.answer("❌ אין תוצאות חיפוש זמינות.")
        return

    current_index = user_data[user_id]["current_index"]
    movies = user_data[user_id]["movies"]

    if call.data.startswith("prev_"):
        new_index = max(0, current_index - 1)
    else:
        new_index = min(len(movies) - 1, current_index + 1)

    user_data[user_id]["current_index"] = new_index
    await send_movie_details(user_id, movies[new_index], call.message.message_id)

# 📌 **צפייה בלייב**
@dp.message(lambda message: message.text == "📺 צפייה בלייב")
async def live_stream(message: Message):
    user_id = message.chat.id
    username = message.from_user.username or "אורח"

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT approved, approval_expiry, is_blocked FROM live_access WHERE user_id = ?", (user_id,))
        access_data = cursor.fetchone()

    if not access_data:
        await message.answer("❌ אין לך גישה לצפייה בלייב. אנא בקש אישור ממנהל המערכת.")
        # שלח למנהל הודעה עם שם המשתמש
        await bot.send_message(ADMIN_ID, f"👤 משתמש חדש מבקש גישה לצפייה בלייב:\n🆔 ID: {user_id}\n👤 שם משתמש: @{username}")
        return

    approved, expiry_date, is_blocked = access_data

    if is_blocked:
        await message.answer("⛔ אתה חסום מצפייה בלייב. אנא פנה למנהל המערכת.")
        return

    if not approved or datetime.now() > datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S"):
        await message.answer("❌ האישור שלך לצפייה בלייב פג תוקף. אנא בקש אישור חדש ממנהל המערכת.")
        # שלח למנהל הודעה עם שם המשתמש
        await bot.send_message(ADMIN_ID, f"👤 משתמש מבקש אישור מחדש לצפייה בלייב:\n🆔 ID: {user_id}\n👤 שם משתמש: @{username}")
        return

    await message.answer(f"📺 צפייה בלייב: [לחץ כאן לצפייה]({VLC_LINK})", parse_mode=ParseMode.MARKDOWN)

# 📌 **פקודת /approve (למנהל בלבד)**
@dp.message(Command("approve"))
async def approve_user(message: Message):
    if message.chat.id != ADMIN_ID:
        await message.answer("⛔ אין לך הרשאה לבצע פעולה זו!")
        return

    try:
        user_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("❌ שימוש: /approve <user_id>")
        return

    expiry_date = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO live_access (user_id, approved, approval_expiry, is_blocked)
            VALUES (?, 1, ?, 0)
        """, (user_id, expiry_date))
        conn.commit()

    await message.answer(f"✅ המשתמש {user_id} אושר לצפייה בלייב למשך שנה.")

# 📌 **פקודת /block_live (למנהל בלבד)**
@dp.message(Command("block_live"))
async def block_user_live(message: Message):
    if message.chat.id != ADMIN_ID:
        await message.answer("⛔ אין לך הרשאה לבצע פעולה זו!")
        return

    try:
        user_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("❌ שימוש: /block_live <user_id>")
        return

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE live_access SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()

    await message.answer(f"✅ המשתמש {user_id} נחסם מצפייה בלייב.")

# 📌 **פקודת /unblock_live (למנהל בלבד)**
@dp.message(Command("unblock_live"))
async def unblock_user_live(message: Message):
    if message.chat.id != ADMIN_ID:
        await message.answer("⛔ אין לך הרשאה לבצע פעולה זו!")
        return

    try:
        user_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("❌ שימוש: /unblock_live <user_id>")
        return

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE live_access SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        conn.commit()

    await message.answer(f"✅ המשתמש {user_id} שוחרר מחסימה לצפייה בלייב.")

# 📌 **הפעלת הבוט**
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())