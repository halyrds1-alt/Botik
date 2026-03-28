import telebot
from telebot import types
import sqlite3
import json
import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = "8784923511:AAEd4LsRjYdGuO3eEsYLthdMRrMIATiBsfw"
bot = telebot.TeleBot(TOKEN)

ADMIN_IDS = [6747528307, 26852106]
NEWS_CHANNEL = "https://t.me/withdrawsbotf"
BOT_NAME = "AERY"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aery_bot.db')

# ============= БАЗА ДАННЫХ (полная, без изменений) =============
class Database:
    def __init__(self):
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # users
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            stars INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            tasks_done INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # tasks
        c.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            text_to_send TEXT,
            target_group TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # completions
        c.execute('''CREATE TABLE IF NOT EXISTS completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id INTEGER,
            message_link TEXT,
            status TEXT DEFAULT 'pending',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # withdrawals (gifts)
        c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            gift_name TEXT,
            stars_cost INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # channel_withdrawals
        c.execute('''CREATE TABLE IF NOT EXISTS channel_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            channel_link TEXT,
            stars_cost INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # support
        c.execute('''CREATE TABLE IF NOT EXISTS support (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            message TEXT,
            status TEXT DEFAULT 'unread',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # sessions
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            user_id INTEGER PRIMARY KEY,
            step TEXT,
            data TEXT
        )''')
        # settings
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', '🐻 ДОБРО ПОЖАЛОВАТЬ В AERY!\\n\\nПривет, {name}!\\n\\n👇 Выбери действие:')")
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")

    def _execute(self, query, params=(), fetchone=False, fetchall=False):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(query, params)
        result = None
        if fetchone:
            result = c.fetchone()
        elif fetchall:
            result = c.fetchall()
        conn.commit()
        conn.close()
        return result

    # users
    def get_user(self, user_id):
        return self._execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)

    def add_user(self, user_id, username, first_name):
        self._execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (user_id, username, first_name))

    def update_stars(self, user_id, amount):
        self._execute("UPDATE users SET stars = stars + ?, total_earned = total_earned + ? WHERE user_id = ?", 
                      (amount, amount if amount > 0 else 0, user_id))

    def get_top_users(self, category):
        sql = {
            'stars': "SELECT first_name, stars, user_id FROM users ORDER BY stars DESC LIMIT 10",
            'earned': "SELECT first_name, total_earned, user_id FROM users ORDER BY total_earned DESC LIMIT 10",
            'tasks': "SELECT first_name, tasks_done, user_id FROM users ORDER BY tasks_done DESC LIMIT 10"
        }.get(category)
        return self._execute(sql, fetchall=True) or []

    # tasks
    def get_tasks(self):
        return self._execute("SELECT id, title, description, text_to_send, target_group FROM tasks ORDER BY id DESC", fetchall=True) or []

    def add_task(self, title, description, text_to_send, target_group, admin_id):
        self._execute("INSERT INTO tasks (title, description, text_to_send, target_group, created_by) VALUES (?, ?, ?, ?, ?)",
                      (title, description, text_to_send, target_group, admin_id))

    def delete_task(self, task_id):
        self._execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def get_task_by_id(self, task_id):
        return self._execute("SELECT id, title, description, text_to_send, target_group, created_at FROM tasks WHERE id = ?", (task_id,), fetchone=True)

    def get_all_tasks_paginated(self, page, per_page=5):
        offset = page * per_page
        tasks = self._execute("SELECT id, title, description, text_to_send, target_group, created_at FROM tasks ORDER BY id DESC LIMIT ? OFFSET ?",
                              (per_page, offset), fetchall=True) or []
        total = self._execute("SELECT COUNT(*) FROM tasks", fetchone=True)[0]
        return tasks, total

    # completions
    def add_completion(self, user_id, task_id, link):
        self._execute("INSERT INTO completions (user_id, task_id, message_link, status) VALUES (?, ?, ?, 'pending')", (user_id, task_id, link))

    def get_pending_completions(self, page=0, per_page=5):
        offset = page * per_page
        completions = self._execute('''SELECT c.id, c.user_id, u.username, u.first_name, c.message_link, t.title, t.id
                                       FROM completions c 
                                       JOIN users u ON c.user_id = u.user_id 
                                       JOIN tasks t ON c.task_id = t.id 
                                       WHERE c.status = 'pending' 
                                       ORDER BY c.submitted_at DESC 
                                       LIMIT ? OFFSET ?''', (per_page, offset), fetchall=True) or []
        total = self._execute("SELECT COUNT(*) FROM completions WHERE status = 'pending'", fetchone=True)[0]
        return completions, total

    def approve_completion(self, comp_id, user_id):
        task = self._execute("SELECT title FROM completions c JOIN tasks t ON c.task_id = t.id WHERE c.id = ?", (comp_id,), fetchone=True)
        task_title = task[0] if task else "задание"
        self._execute("UPDATE completions SET status = 'approved' WHERE id = ?", (comp_id,))
        self.update_stars(user_id, 1)
        try:
            bot.send_message(user_id, f"✅ <b>ЗАЯВКА ОДОБРЕНА!</b>\n\n📝 Задание: {task_title}\n⭐ Начислено: 1 звезда\n\nПродолжай выполнять задания! 🚀", parse_mode='HTML')
        except: pass

    def reject_completion(self, comp_id, user_id):
        task = self._execute("SELECT title FROM completions c JOIN tasks t ON c.task_id = t.id WHERE c.id = ?", (comp_id,), fetchone=True)
        task_title = task[0] if task else "задание"
        self._execute("UPDATE completions SET status = 'rejected' WHERE id = ?", (comp_id,))
        try:
            bot.send_message(user_id, f"❌ <b>ЗАЯВКА ОТКЛОНЕНА</b>\n\n📝 Задание: {task_title}\n\nПричина: ссылка не прошла проверку.\nПопробуй выполнить задание заново!", parse_mode='HTML')
        except: pass

    # withdrawals gifts
    def add_withdrawal_gift(self, user_id, username, gift_name, stars):
        self._execute("INSERT INTO withdrawals (user_id, username, gift_name, stars_cost, status) VALUES (?, ?, ?, ?, 'pending')", (user_id, username, gift_name, stars))
        self.update_stars(user_id, -stars)

    def get_pending_withdrawals_gift(self, page=0, per_page=5):
        offset = page * per_page
        wd = self._execute("SELECT id, user_id, username, gift_name, stars_cost FROM withdrawals WHERE status = 'pending' ORDER BY created_at DESC LIMIT ? OFFSET ?", (per_page, offset), fetchall=True) or []
        total = self._execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'", fetchone=True)[0]
        return wd, total

    def approve_withdrawal_gift(self, wd_id, user_id, gift_name, stars):
        self._execute("UPDATE withdrawals SET status = 'approved' WHERE id = ?", (wd_id,))
        user = self.get_user(user_id)
        try:
            bot.send_message(user_id, f"✅ <b>ВЫВОД ПОДТВЕРЖДЕН!</b>\n\n🎁 Подарок: {gift_name}\n⭐ Списано: {stars} звезд\n💰 Твой баланс: {user[3]} звезд\n\nПодарок будет отправлен в ближайшее время! 🎉", parse_mode='HTML')
        except: pass

    # channel withdrawals
    def add_withdrawal_channel(self, user_id, username, channel_link, stars):
        self._execute("INSERT INTO channel_withdrawals (user_id, username, channel_link, stars_cost, status) VALUES (?, ?, ?, ?, 'pending')", (user_id, username, channel_link, stars))
        self.update_stars(user_id, -stars)

    def get_pending_withdrawals_channel(self, page=0, per_page=5):
        offset = page * per_page
        wd = self._execute("SELECT id, user_id, username, channel_link, stars_cost FROM channel_withdrawals WHERE status = 'pending' ORDER BY created_at DESC LIMIT ? OFFSET ?", (per_page, offset), fetchall=True) or []
        total = self._execute("SELECT COUNT(*) FROM channel_withdrawals WHERE status = 'pending'", fetchone=True)[0]
        return wd, total

    def approve_withdrawal_channel(self, wd_id, user_id, stars):
        self._execute("UPDATE channel_withdrawals SET status = 'approved' WHERE id = ?", (wd_id,))
        user = self.get_user(user_id)
        try:
            bot.send_message(user_id, f"✅ <b>ВЫВОД ПОДТВЕРЖДЕН!</b>\n\n⭐ Списано: {stars} звезд\n💰 Твой баланс: {user[3]} звезд\n\nЗадание выполнено успешно! 🎉", parse_mode='HTML')
        except: pass

    # support
    def add_support(self, user_id, username, first_name, msg):
        self._execute("INSERT INTO support (user_id, username, first_name, message, status) VALUES (?, ?, ?, ?, 'unread')", (user_id, username, first_name, msg))

    def get_unread_support(self, page=0, per_page=5):
        offset = page * per_page
        msgs = self._execute("SELECT id, user_id, username, first_name, message FROM support WHERE status = 'unread' ORDER BY created_at DESC LIMIT ? OFFSET ?", (per_page, offset), fetchall=True) or []
        total = self._execute("SELECT COUNT(*) FROM support WHERE status = 'unread'", fetchone=True)[0]
        return msgs, total

    def mark_support_read(self, msg_id):
        self._execute("UPDATE support SET status = 'read' WHERE id = ?", (msg_id,))

    # sessions
    def set_session(self, user_id, step, data=None):
        self._execute("INSERT OR REPLACE INTO sessions (user_id, step, data) VALUES (?, ?, ?)", (user_id, step, json.dumps(data) if data else None))

    def get_session(self, user_id):
        row = self._execute("SELECT step, data FROM sessions WHERE user_id = ?", (user_id,), fetchone=True)
        if row:
            return {'step': row[0], 'data': json.loads(row[1]) if row[1] else None}
        return None

    def clear_session(self, user_id):
        self._execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    # stats
    def get_stats(self):
        total_users = self._execute("SELECT COUNT(*) FROM users", fetchone=True)[0]
        total_stars = self._execute("SELECT SUM(stars) FROM users", fetchone=True)[0] or 0
        tasks_done = self._execute("SELECT COUNT(*) FROM completions WHERE status = 'approved'", fetchone=True)[0]
        withdrawals = self._execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'approved'", fetchone=True)[0] + \
                      self._execute("SELECT COUNT(*) FROM channel_withdrawals WHERE status = 'approved'", fetchone=True)[0]
        return total_users, total_stars, tasks_done, withdrawals

    # settings
    def get_setting(self, key):
        row = self._execute("SELECT value FROM settings WHERE key = ?", (key,), fetchone=True)
        return row[0] if row else None

    def update_setting(self, key, value):
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

db = Database()

# ============= КЛАВИАТУРЫ =============
def main_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btns = ["⭐ ЗВЕЗДЫ ЗА КОММЕНТАРИИ", "👤 ПРОФИЛЬ", "🏆 ТОП", "🎁 ВЫВОД ЗВЕЗД", "🛟 САППОРТ", "📰 НОВОСТИ"]
    if user_id and user_id in ADMIN_IDS:
        btns.append("👑 АДМИН ПАНЕЛЬ")
    markup.add(*[types.KeyboardButton(b) for b in btns])
    return markup

def back_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔙 НАЗАД"))
    return markup

def admin_back_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔙 НАЗАД В АДМИНКУ"))
    return markup

# ============= ОСНОВНЫЕ ФУНКЦИИ (пользовательские) =============
@bot.message_handler(commands=['start'])
def start(message):
    db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = db.get_setting('welcome_text') or f"🐻 <b>ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}!</b>\n\nПривет, {message.from_user.first_name}!\n\n👇 Выбери действие:"
    text = text.format(name=message.from_user.first_name)
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=main_keyboard(message.from_user.id))

def profile(message):
    user = db.get_user(message.from_user.id)
    if not user:
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        user = db.get_user(message.from_user.id)
    text = (f"🐻 <b>ПРОФИЛЬ</b>\n\n"
            f"<b>👤 Имя:</b> {user[2]}\n"
            f"<b>🆔 ID:</b> <code>{user[0]}</code>\n"
            f"<b>⭐ Баланс:</b> {user[3]}\n"
            f"<b>💰 Всего заработано:</b> {user[4]}\n"
            f"<b>✅ Выполнено заданий:</b> {user[5]}\n"
            f"<b>📅 В боте с:</b> {user[6][:10]}")
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=main_keyboard(message.from_user.id))

def top_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💰 ПО БАЛАНСУ", callback_data="top_stars"),
        types.InlineKeyboardButton("⭐ ПО ЗАРАБОТКУ", callback_data="top_earned"),
        types.InlineKeyboardButton("✅ ПО ЗАДАНИЯМ", callback_data="top_tasks")
    )
    bot.send_message(message.chat.id, "🏆 <b>ТОП ПОЛЬЗОВАТЕЛЕЙ</b>\n\nВыбери категорию:", parse_mode='HTML', reply_markup=markup)

def show_top(call, category):
    users = db.get_top_users(category)
    if not users:
        bot.answer_callback_query(call.id, "📭 Пока никого нет")
        return
    titles = {'stars': '💰 ПО БАЛАНСУ', 'earned': '⭐ ПО ЗАРАБОТКУ', 'tasks': '✅ ПО ЗАДАНИЯМ'}
    text = f"🏆 <b>{titles[category]}</b>\n\n"
    for i, (name, value, uid) in enumerate(users, 1):
        medal = "🥇 " if i == 1 else "🥈 " if i == 2 else "🥉 " if i == 3 else f"{i}. "
        uid_str = str(uid)
        hidden_id = uid_str[:4] + "***" + uid_str[-2:] if len(uid_str) > 6 else uid_str
        text += f"{medal}{name[:15]}\n   {value} | ID: {hidden_id}\n\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML')

def stars_section(message):
    tasks = db.get_tasks()
    if not tasks:
        bot.send_message(message.chat.id, "📭 <b>Нет активных заданий</b>\n\nЗагляни позже!", parse_mode='HTML', reply_markup=main_keyboard(message.from_user.id))
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for task in tasks:
        markup.add(types.InlineKeyboardButton(f"⭐ {task[1]} (+1⭐)", callback_data=f"task_{task[0]}"))
    bot.send_message(message.chat.id, "⭐ <b>ДОСТУПНЫЕ ЗАДАНИЯ</b>\n\nВыбери задание:", parse_mode='HTML', reply_markup=markup)

def task_detail(call, task_id):
    task = db.get_task_by_id(task_id)
    if not task:
        bot.answer_callback_query(call.id, "Задание не найдено")
        return
    title, description, text_to_send, target_group = task[1], task[2], task[3], task[4]
    group_text = f"\n📢 <b>Группа для отправки:</b>\n{target_group}\n" if target_group else ""
    text = (f"<b>⭐ {title}</b>\n\n"
            f"{description}\n\n"
            f"<b>📢 Текст для отправки:</b>\n<code>{text_to_send}</code>\n"
            f"{group_text}\n"
            f"📌 <b>Инструкция:</b>\n"
            f"1️⃣ Отправь этот текст в указанную группу\n"
            f"2️⃣ Нажми «ВЫПОЛНИЛ»\n"
            f"3️⃣ Отправь ссылку на твое сообщение\n\n"
            f"⭐ <b>Награда:</b> 1 звезда\n\n"
            f"⚠️ <b>Важно!</b> Группа должна быть публичной!")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ ВЫПОЛНИЛ", callback_data=f"complete_{task_id}"))
    markup.add(types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_tasks"))
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup, disable_web_page_preview=True)
    except:
        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup, disable_web_page_preview=True)

def start_complete(call, task_id):
    db.set_session(call.from_user.id, 'waiting_link', {'task_id': task_id})
    text = ("📎 <b>ОТПРАВЬ ССЫЛКУ НА СООБЩЕНИЕ</b>\n\n"
            "<b>Как скопировать ссылку:</b>\n"
            "1️⃣ Найди свое сообщение в группе\n"
            "2️⃣ Нажми на него и удерживай\n"
            "3️⃣ Выбери «Копировать ссылку»\n\n"
            "🔗 <b>Отправь ссылку сюда:</b>")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_task"))
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
    except:
        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def withdrawal_section(message):
    user = db.get_user(message.from_user.id)
    text = (f"🎁 <b>ВЫВОД ЗВЕЗД</b>\n\n"
            f"⭐ <b>Твой баланс:</b> {user[3]} звезд\n\n"
            f"<b>Выбери способ вывода:</b>")
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎁 ПОДАРОК TELEGRAM", callback_data="withdraw_gift"),
        types.InlineKeyboardButton("📝 ВЫВОД В КАНАЛ (15⭐)", callback_data="withdraw_channel")
    )
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def withdraw_gift_menu(call):
    user = db.get_user(call.from_user.id)
    gifts = [("🐻 МИШКА", 15), ("🎁 ПОДАРОК", 25), ("💐 БУКЕТ", 50), ("💍 КОЛЬЦО", 100)]
    text = f"🎁 <b>ВЫБЕРИ ПОДАРОК</b>\n\n⭐ Твой баланс: {user[3]} звезд\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2)
    for name, price in gifts:
        if user[3] >= price:
            markup.add(types.InlineKeyboardButton(f"{name} ({price}⭐)", callback_data=f"gift_{name}_{price}"))
        else:
            markup.add(types.InlineKeyboardButton(f"🔒 {name} ({price}⭐)", callback_data="noop"))
    markup.add(types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_withdraw"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)

def start_gift_withdrawal(call, gift_name, price):
    db.set_session(call.from_user.id, 'waiting_username', {'gift': gift_name, 'stars': price})
    text = (f"🎁 <b>ВЫВОД: {gift_name}</b>\n\n"
            f"⭐ <b>Стоимость:</b> {price} звезд\n\n"
            f"📝 <b>Отправь свой username</b>\n"
            f"(например: @username)")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_withdraw"))
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
    except:
        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def start_channel_withdrawal(call):
    db.set_session(call.from_user.id, 'waiting_channel_link', {'stars': 15})
    text = ("📝 <b>ВЫВОД В КАНАЛ (15⭐)</b>\n\n"
            "Отправь ссылку на канал Telegram, куда нужно отправить пост:\n\n"
            "Пример: https://t.me/channel_name")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_withdraw"))
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
    except:
        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def support_section(message):
    db.set_session(message.from_user.id, 'waiting_support', {})
    bot.send_message(message.chat.id, "🛟 <b>СЛУЖБА ПОДДЕРЖКИ</b>\n\nНапиши свой вопрос, администратор ответит:", parse_mode='HTML', reply_markup=back_keyboard())

def send_support_to_admin(user_id, username, first_name, msg_text):
    for admin_id in ADMIN_IDS:
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💬 ОТВЕТИТЬ", callback_data=f"reply_{user_id}"))
            bot.send_message(admin_id, f"💬 <b>НОВОЕ СООБЩЕНИЕ</b>\n\n👤 {first_name}\n🆔 <code>{user_id}</code>\n\n📝 {msg_text}", parse_mode='HTML', reply_markup=markup)
        except:
            pass

# ============= АДМИН ПАНЕЛЬ (исправленная) =============
def admin_panel(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btns = [
        "📋 ЗАЯВКИ НА ЗАДАНИЯ", "🎁 ЗАЯВКИ НА ВЫВОД", "💬 СООБЩЕНИЯ",
        "📢 РАССЫЛКА", "➕ ДОБАВИТЬ ЗАДАНИЕ", "🗑 УДАЛИТЬ ЗАДАНИЕ",
        "📊 СТАТИСТИКА", "⚙️ ИЗМЕНИТЬ ПРИВЕТСТВИЕ", "🔙 НАЗАД"
    ]
    markup.add(*[types.KeyboardButton(b) for b in btns])
    bot.send_message(message.chat.id, "👑 <b>АДМИН ПАНЕЛЬ</b>\n\nВыбери действие:", parse_mode='HTML', reply_markup=markup)

def admin_edit_welcome(message):
    db.set_session(message.from_user.id, 'edit_welcome', {})
    bot.send_message(message.chat.id, "📝 <b>ИЗМЕНЕНИЕ ПРИВЕТСТВИЯ</b>\n\nОтправь новый текст приветствия.\n\nИспользуй {name} для вставки имени пользователя.\n\nПример:\nПривет, {name}! Добро пожаловать в AERY!", parse_mode='HTML')

# ===== ЗАЯВКИ НА ЗАДАНИЯ =====
def admin_tasks(message, page=0):
    completions, total = db.get_pending_completions(page)
    if not completions:
        bot.send_message(message.chat.id, "📭 Нет заявок на задания", reply_markup=admin_back_keyboard())
        return
    per_page = 5
    total_pages = (total + per_page - 1) // per_page
    text = f"📋 <b>ЗАЯВКИ НА ЗАДАНИЯ</b>\n\n<b>Страница {page+1} из {total_pages}</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for comp in completions:
        comp_id, uid, username, name, link, title, task_id = comp
        markup.add(types.InlineKeyboardButton(f"#{comp_id} | {name} | {title}", callback_data=f"view_task_{comp_id}"))
    # Пагинация
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("◀️", callback_data=f"tasks_page_{page-1}"))
    nav.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(types.InlineKeyboardButton("▶️", callback_data=f"tasks_page_{page+1}"))
    if nav:
        markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin"))
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def admin_view_task(call, comp_id):
    # Получаем детали заявки
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT c.id, c.user_id, u.username, u.first_name, c.message_link, t.title, t.id
                 FROM completions c 
                 JOIN users u ON c.user_id = u.user_id 
                 JOIN tasks t ON c.task_id = t.id 
                 WHERE c.id = ?''', (comp_id,))
    comp = c.fetchone()
    conn.close()
    if not comp:
        bot.answer_callback_query(call.id, "Заявка не найдена")
        return
    comp_id, uid, username, name, link, title, task_id = comp
    text = (f"📋 <b>ЗАЯВКА #{comp_id}</b>\n\n"
            f"<b>👤 Пользователь:</b> {name}\n"
            f"<b>🆔 ID:</b> <code>{uid}</code>\n"
            f"<b>📝 Задание:</b> {title}\n"
            f"<b>🔗 Ссылка:</b> {link}\n\n"
            f"✅ <b>Проверь ссылку и прими решение:</b>")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ ПРИНЯТЬ", callback_data=f"ap_{comp_id}_{uid}"),
        types.InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"rj_{comp_id}_{uid}"),
        types.InlineKeyboardButton("◀️ НАЗАД", callback_data="back_to_tasks_list")
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)

# ===== ЗАЯВКИ НА ВЫВОД =====
def admin_withdrawals(message, page=0):
    gift_wd, gift_total = db.get_pending_withdrawals_gift(page)
    channel_wd, channel_total = db.get_pending_withdrawals_channel(page)
    if not gift_wd and not channel_wd:
        bot.send_message(message.chat.id, "📭 Нет заявок на вывод", reply_markup=admin_back_keyboard())
        return
    per_page = 5
    total_pages = max((gift_total + per_page - 1) // per_page, (channel_total + per_page - 1) // per_page)
    text = f"🎁 <b>ЗАЯВКИ НА ВЫВОД</b>\n\n<b>Страница {page+1} из {total_pages}</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    # Подарки Telegram
    for wd in gift_wd:
        wd_id, uid, username, gift, stars = wd
        markup.add(types.InlineKeyboardButton(f"🎁 #{wd_id} | @{username or uid} | {gift} ({stars}⭐)", callback_data=f"view_gift_{wd_id}"))
    # Вывод в канал
    for wd in channel_wd:
        wd_id, uid, username, link, stars = wd
        markup.add(types.InlineKeyboardButton(f"📝 #{wd_id} | @{username or uid} | {link[:30]}... ({stars}⭐)", callback_data=f"view_channel_{wd_id}"))
    # Пагинация
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("◀️", callback_data=f"withdraw_page_{page-1}"))
    nav.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(types.InlineKeyboardButton("▶️", callback_data=f"withdraw_page_{page+1}"))
    if nav:
        markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin"))
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def admin_view_gift(call, wd_id):
    # Получаем детали заявки на подарок
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, gift_name, stars_cost FROM withdrawals WHERE id = ?", (wd_id,))
    wd = c.fetchone()
    conn.close()
    if not wd:
        bot.answer_callback_query(call.id, "Заявка не найдена")
        return
    wd_id, uid, username, gift, stars = wd
    text = (f"🎁 <b>ЗАЯВКА #{wd_id}</b>\n\n"
            f"<b>👤 Пользователь:</b> @{username or uid}\n"
            f"<b>🎁 Подарок:</b> {gift}\n"
            f"<b>⭐ Стоимость:</b> {stars} звезд\n\n"
            f"✅ <b>Отправь подарок и нажми кнопку:</b>")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ ОТПРАВЛЕНО", callback_data=f"ag_{wd_id}_{uid}_{gift}_{stars}"))
    markup.add(types.InlineKeyboardButton("◀️ НАЗАД", callback_data="back_to_withdrawals_list"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)

def admin_view_channel(call, wd_id):
    # Получаем детали заявки на вывод в канал
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, channel_link, stars_cost FROM channel_withdrawals WHERE id = ?", (wd_id,))
    wd = c.fetchone()
    conn.close()
    if not wd:
        bot.answer_callback_query(call.id, "Заявка не найдена")
        return
    wd_id, uid, username, link, stars = wd
    text = (f"📝 <b>ЗАЯВКА #{wd_id}</b>\n\n"
            f"<b>👤 Пользователь:</b> @{username or uid}\n"
            f"<b>🔗 Ссылка на канал:</b> {link}\n"
            f"<b>⭐ Стоимость:</b> {stars} звезд\n\n"
            f"✅ <b>Проверь ссылку и нажми кнопку:</b>")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ ПОДТВЕРДИТЬ", callback_data=f"ac_{wd_id}_{uid}_{stars}"))
    markup.add(types.InlineKeyboardButton("◀️ НАЗАД", callback_data="back_to_withdrawals_list"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)

# ===== СООБЩЕНИЯ В САППОРТ =====
def admin_support(message, page=0):
    msgs, total = db.get_unread_support(page)
    if not msgs:
        bot.send_message(message.chat.id, "📭 Нет сообщений", reply_markup=admin_back_keyboard())
        return
    per_page = 5
    total_pages = (total + per_page - 1) // per_page
    text = f"💬 <b>СООБЩЕНИЯ В САППОРТ</b>\n\n<b>Страница {page+1} из {total_pages}</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for msg in msgs:
        msg_id, uid, username, name, msg_text = msg
        markup.add(types.InlineKeyboardButton(f"#{msg_id} | {name}", callback_data=f"view_support_{msg_id}"))
    # Пагинация
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("◀️", callback_data=f"support_page_{page-1}"))
    nav.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(types.InlineKeyboardButton("▶️", callback_data=f"support_page_{page+1}"))
    if nav:
        markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin"))
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def admin_view_support(call, msg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, first_name, message FROM support WHERE id = ?", (msg_id,))
    msg = c.fetchone()
    conn.close()
    if not msg:
        bot.answer_callback_query(call.id, "Сообщение не найдено")
        return
    msg_id, uid, username, name, msg_text = msg
    text = (f"💬 <b>СООБЩЕНИЕ</b>\n\n"
            f"<b>👤 От:</b> {name}\n"
            f"<b>🆔 ID:</b> <code>{uid}</code>\n"
            f"<b>📝 Текст:</b>\n{msg_text}\n\n"
            f"✍️ <b>Напиши ответ:</b>")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✍️ ОТВЕТИТЬ", callback_data=f"sr_{msg_id}_{uid}"))
    markup.add(types.InlineKeyboardButton("◀️ НАЗАД", callback_data="back_to_support_list"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)

# ===== РАССЫЛКА =====
def admin_mailing_start(message):
    db.set_session(message.from_user.id, 'admin_mailing', {})
    bot.send_message(message.chat.id, "📢 <b>РАССЫЛКА</b>\n\nОтправь текст сообщения для рассылки:", parse_mode='HTML')

def admin_mailing_send(admin_id, text):
    users = db._execute("SELECT user_id FROM users", fetchall=True) or []
    success = 0
    for user in users:
        try:
            bot.send_message(user[0], f"📢 <b>РАССЫЛКА ОТ АДМИНА</b>\n\n{text}", parse_mode='HTML')
            success += 1
            time.sleep(0.05)
        except:
            pass
    bot.send_message(admin_id, f"✅ Рассылка завершена\n\nОтправлено: {success} из {len(users)}")

# ===== СОЗДАНИЕ ЗАДАНИЯ =====
def admin_add_task_start(message):
    db.set_session(message.from_user.id, 'admin_task_title', {})
    text = ("➕ <b>ДОБАВЛЕНИЕ ЗАДАНИЯ</b>\n\n"
            "<b>Шаг 1/4:</b> Введите название задания\n\n"
            "Пример: «Реклама бота»")
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ===== УДАЛЕНИЕ ЗАДАНИЙ =====
def admin_delete_tasks_menu(message, page=0):
    tasks, total = db.get_all_tasks_paginated(page)
    if not tasks:
        bot.send_message(message.chat.id, "📭 Нет заданий для удаления", reply_markup=admin_back_keyboard())
        return
    per_page = 5
    total_pages = (total + per_page - 1) // per_page
    text = f"🗑 <b>УДАЛЕНИЕ ЗАДАНИЙ</b>\n\n<b>Страница {page + 1} из {total_pages}</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, task in enumerate(tasks, 1 + page * per_page):
        task_id, title, desc, txt, target, created_at = task
        markup.add(types.InlineKeyboardButton(f"{i}. {title} (ID: {task_id})", callback_data=f"delete_task_{task_id}"))
    # Пагинация
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("◀️", callback_data=f"delete_page_{page-1}"))
    nav.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(types.InlineKeyboardButton("▶️", callback_data=f"delete_page_{page+1}"))
    if nav:
        markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_admin"))
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def show_task_for_delete(call, task_id):
    task = db.get_task_by_id(task_id)
    if not task:
        bot.answer_callback_query(call.id, "Задание не найдено")
        return
    task_id, title, description, text_to_send, target_group, created_at = task
    group_text = f"\n📢 <b>Группа:</b> {target_group}" if target_group else ""
    text = (f"🗑 <b>УДАЛЕНИЕ ЗАДАНИЯ</b>\n\n"
            f"<b>📌 Название:</b> {title}\n"
            f"<b>📝 Описание:</b>\n{description}\n"
            f"<b>📢 Текст для отправки:</b>\n<code>{text_to_send}</code>\n"
            f"{group_text}\n"
            f"<b>🆔 ID:</b> <code>{task_id}</code>\n"
            f"<b>📅 Создано:</b> {created_at[:19]}\n\n"
            f"⚠️ <b>ВНИМАНИЕ!</b> Задание будет удалено безвозвратно!\n\n"
            f"✅ <b>Точно удалить это задание?</b>")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ ДА, УДАЛИТЬ", callback_data=f"confirm_delete_{task_id}"),
        types.InlineKeyboardButton("❌ НЕТ, НАЗАД", callback_data="back_to_delete_menu")
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup, disable_web_page_preview=True)

def confirm_delete_task(call, task_id):
    task = db.get_task_by_id(task_id)
    if not task:
        bot.answer_callback_query(call.id, "Задание уже удалено")
        bot.edit_message_text("❌ Задание не найдено", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        return
    title = task[1]
    db.delete_task(task_id)
    bot.edit_message_text(f"✅ <b>ЗАДАНИЕ УДАЛЕНО!</b>\n\n«{title}» успешно удалено.", call.message.chat.id, call.message.message_id, parse_mode='HTML')

# ============= ОБРАБОТКА СООБЩЕНИЙ =============
@bot.message_handler(func=lambda m: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text
    session = db.get_session(user_id)

    # Изменение приветствия
    if session and session['step'] == 'edit_welcome' and user_id in ADMIN_IDS:
        db.update_setting('welcome_text', text)
        db.clear_session(user_id)
        bot.send_message(message.chat.id, "✅ Приветствие обновлено!", reply_markup=main_keyboard(user_id))
        admin_panel(message)
        return

    # Саппорт
    if session and session['step'] == 'waiting_support':
        db.add_support(user_id, message.from_user.username, message.from_user.first_name, text)
        send_support_to_admin(user_id, message.from_user.username, message.from_user.first_name, text)
        db.clear_session(user_id)
        bot.send_message(message.chat.id, "✅ Сообщение отправлено! Администратор ответит в ближайшее время.", reply_markup=main_keyboard(user_id))
        return

    # Ссылка на выполнение задания
    if session and session['step'] == 'waiting_link':
        link = text
        if not link.startswith('https://t.me/'):
            bot.send_message(message.chat.id, "❌ Некорректная ссылка! Отправь ссылку вида https://t.me/...")
            return
        task_id = session['data']['task_id']
        db.add_completion(user_id, task_id, link)
        db.clear_session(user_id)
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, f"📋 Новая заявка от {message.from_user.first_name}\nЗадание #{task_id}\nСсылка: {link}")
            except:
                pass
        bot.send_message(message.chat.id, "✅ Заявка отправлена! Администратор проверит и начислит звезды.", reply_markup=main_keyboard(user_id))
        return

    # Username для подарка
    if session and session['step'] == 'waiting_username':
        username = text.strip().replace('@', '')
        if not username:
            bot.send_message(message.chat.id, "❌ Отправь корректный username")
            return
        gift = session['data']['gift']
        stars = session['data']['stars']
        user = db.get_user(user_id)
        if user[3] < stars:
            bot.send_message(message.chat.id, "❌ Недостаточно звезд!", reply_markup=main_keyboard(user_id))
            db.clear_session(user_id)
            return
        db.add_withdrawal_gift(user_id, username, gift, stars)
        db.clear_session(user_id)
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, f"🎁 Новая заявка на вывод\n👤 @{username}\n🎁 {gift}\n⭐ {stars}")
            except:
                pass
        bot.send_message(message.chat.id, f"✅ Заявка отправлена! {gift} будет отправлен в ближайшее время.", reply_markup=main_keyboard(user_id))
        return

    # Ссылка для вывода в канал
    if session and session['step'] == 'waiting_channel_link':
        link = text
        if not link.startswith('https://t.me/'):
            bot.send_message(message.chat.id, "❌ Некорректная ссылка!")
            return
        stars = session['data']['stars']
        user = db.get_user(user_id)
        if user[3] < stars:
            bot.send_message(message.chat.id, "❌ Недостаточно звезд!", reply_markup=main_keyboard(user_id))
            db.clear_session(user_id)
            return
        db.add_withdrawal_channel(user_id, message.from_user.username, link, stars)
        db.clear_session(user_id)
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, f"📝 Новая заявка на вывод в канал\n👤 {message.from_user.first_name}\n🔗 {link}\n⭐ {stars}")
            except:
                pass
        bot.send_message(message.chat.id, f"✅ Заявка отправлена! Администратор проверит ссылку.", reply_markup=main_keyboard(user_id))
        return

    # Рассылка
    if session and session['step'] == 'admin_mailing' and user_id in ADMIN_IDS:
        admin_mailing_send(user_id, text)
        db.clear_session(user_id)
        admin_panel(message)
        return

    # Создание задания
    if session and user_id in ADMIN_IDS:
        step = session['step']
        if step == 'admin_task_title':
            db.set_session(user_id, 'admin_task_desc', {'title': text})
            bot.send_message(message.chat.id, f"✅ Название: {text}\n\n<b>Шаг 2/4:</b> Введите описание задания\n\nПример: «Отправь текст в указанную группу»", parse_mode='HTML')
            return
        if step == 'admin_task_desc':
            data = session['data']
            data['description'] = text
            db.set_session(user_id, 'admin_task_text', data)
            bot.send_message(message.chat.id, f"✅ Описание сохранено\n\n<b>Шаг 3/4:</b> Введите текст, который нужно отправить в группу\n\nПример: «Лучший бот для заработка звёзд @StarsForCommentsBot»", parse_mode='HTML')
            return
        if step == 'admin_task_text':
            data = session['data']
            data['text_to_send'] = text
            db.set_session(user_id, 'admin_task_group', data)
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(types.InlineKeyboardButton("✅ ДА", callback_data="task_group_yes"), types.InlineKeyboardButton("❌ НЕТ", callback_data="task_group_no"))
            bot.send_message(message.chat.id, f"✅ Текст сохранен\n\n<b>Шаг 4/4:</b> Нужно указать конкретную группу для отправки?", parse_mode='HTML', reply_markup=markup)
            return
        if step == 'admin_task_group_input':
            data = session['data']
            target_group = text
            db.add_task(data['title'], data['description'], data['text_to_send'], target_group, user_id)
            db.clear_session(user_id)
            bot.send_message(message.chat.id, "✅ <b>ЗАДАНИЕ СОЗДАНО!</b>\n\nПользователи увидят его в разделе «Звезды за комментарии»", parse_mode='HTML', reply_markup=main_keyboard(user_id))
            admin_panel(message)
            return

    # Кнопки
    if text == "⭐ ЗВЕЗДЫ ЗА КОММЕНТАРИИ":
        stars_section(message)
    elif text == "👤 ПРОФИЛЬ":
        profile(message)
    elif text == "🏆 ТОП":
        top_menu(message)
    elif text == "🎁 ВЫВОД ЗВЕЗД":
        withdrawal_section(message)
    elif text == "🛟 САППОРТ":
        support_section(message)
    elif text == "📰 НОВОСТИ":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url=NEWS_CHANNEL))
        bot.send_message(message.chat.id, "📰 <b>НОВОСТНОЙ КАНАЛ</b>\n\nПодпишись, чтобы быть в курсе!", parse_mode='HTML', reply_markup=markup)
    elif text == "👑 АДМИН ПАНЕЛЬ" and user_id in ADMIN_IDS:
        admin_panel(message)
    elif text == "🔙 НАЗАД":
        start(message)
    elif text == "🔙 НАЗАД В АДМИНКУ" and user_id in ADMIN_IDS:
        admin_panel(message)
    elif text == "📋 ЗАЯВКИ НА ЗАДАНИЯ" and user_id in ADMIN_IDS:
        admin_tasks(message)
    elif text == "🎁 ЗАЯВКИ НА ВЫВОД" and user_id in ADMIN_IDS:
        admin_withdrawals(message)
    elif text == "💬 СООБЩЕНИЯ" and user_id in ADMIN_IDS:
        admin_support(message)
    elif text == "📢 РАССЫЛКА" and user_id in ADMIN_IDS:
        admin_mailing_start(message)
    elif text == "➕ ДОБАВИТЬ ЗАДАНИЕ" and user_id in ADMIN_IDS:
        admin_add_task_start(message)
    elif text == "🗑 УДАЛИТЬ ЗАДАНИЕ" and user_id in ADMIN_IDS:
        admin_delete_tasks_menu(message)
    elif text == "📊 СТАТИСТИКА" and user_id in ADMIN_IDS:
        total_users, total_stars, tasks_done, withdrawals = db.get_stats()
        stats_text = (f"📊 <b>СТАТИСТИКА</b>\n\n"
                      f"<b>👥 Пользователей:</b> {total_users}\n"
                      f"<b>⭐ Всего звезд:</b> {total_stars}\n"
                      f"<b>✅ Выполнено заданий:</b> {tasks_done}\n"
                      f"<b>🎁 Выводов:</b> {withdrawals}")
        bot.send_message(message.chat.id, stats_text, parse_mode='HTML')
    elif text == "⚙️ ИЗМЕНИТЬ ПРИВЕТСТВИЕ" and user_id in ADMIN_IDS:
        admin_edit_welcome(message)
    else:
        bot.send_message(message.chat.id, "Используй кнопки меню 👇", reply_markup=main_keyboard(user_id))

# ============= CALLBACK ОБРАБОТЧИК =============
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    bot.answer_callback_query(call.id)  # всегда отвечаем

    # --- Назад в админку ---
    if data == "back_to_admin":
        admin_panel(call.message)
        return

    # --- Возврат к спискам ---
    if data == "back_to_tasks_list":
        admin_tasks(call.message)
        return
    if data == "back_to_withdrawals_list":
        admin_withdrawals(call.message)
        return
    if data == "back_to_support_list":
        admin_support(call.message)
        return
    if data == "back_to_delete_menu":
        admin_delete_tasks_menu(call.message)
        return

    # --- Удаление заданий ---
    if data.startswith("delete_page_"):
        page = int(data.split("_")[2])
        admin_delete_tasks_menu(call.message, page)
        return
    if data.startswith("delete_task_"):
        task_id = int(data.split("_")[2])
        show_task_for_delete(call, task_id)
        return
    if data.startswith("confirm_delete_"):
        task_id = int(data.split("_")[2])
        confirm_delete_task(call, task_id)
        return

    # --- Создание задания (группа) ---
    if data == "task_group_yes":
        session = db.get_session(user_id)
        if session and session['step'] == 'admin_task_group':
            db.set_session(user_id, 'admin_task_group_input', session['data'])
            bot.edit_message_text("📎 <b>Отправь ссылку на группу</b>\n\nПример: https://t.me/group_name", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        return
    if data == "task_group_no":
        session = db.get_session(user_id)
        if session and session['step'] == 'admin_task_group':
            d = session['data']
            db.add_task(d['title'], d['description'], d['text_to_send'], None, user_id)
            db.clear_session(user_id)
            bot.edit_message_text("✅ <b>ЗАДАНИЕ СОЗДАНО!</b>", call.message.chat.id, call.message.message_id, parse_mode='HTML')
            admin_panel(call.message)
        return

    # --- Топ ---
    if data == "top_stars":
        show_top(call, 'stars')
        return
    if data == "top_earned":
        show_top(call, 'earned')
        return
    if data == "top_tasks":
        show_top(call, 'tasks')
        return

    # --- Задания пользователя ---
    if data.startswith("task_"):
        try:
            task_id = int(data.split("_")[1])
            task_detail(call, task_id)
        except:
            pass
        return
    if data == "back_to_tasks":
        stars_section(call.message)
        return
    if data.startswith("complete_"):
        try:
            task_id = int(data.split("_")[1])
            start_complete(call, task_id)
        except:
            pass
        return
    if data == "cancel_task":
        db.clear_session(user_id)
        stars_section(call.message)
        return

    # --- Вывод звезд ---
    if data == "withdraw_gift":
        withdraw_gift_menu(call)
        return
    if data == "withdraw_channel":
        start_channel_withdrawal(call)
        return
    if data == "back_to_withdraw":
        withdrawal_section(call.message)
        return
    if data.startswith("gift_"):
        parts = data.split("_")
        if len(parts) >= 3:
            gift_name = parts[1]
            try:
                price = int(parts[2])
                start_gift_withdrawal(call, gift_name, price)
            except:
                pass
        return
    if data == "cancel_withdraw":
        db.clear_session(user_id)
        withdrawal_section(call.message)
        return

    # --- Админ: заявки на задания (пагинация и просмотр) ---
    if data.startswith("tasks_page_"):
        page = int(data.split("_")[2])
        admin_tasks(call.message, page)
        return
    if data.startswith("view_task_"):
        comp_id = int(data.split("_")[2])
        admin_view_task(call, comp_id)
        return
    if data.startswith("ap_"):
        if user_id not in ADMIN_IDS:
            return
        parts = data.split("_")
        if len(parts) >= 3:
            comp_id = int(parts[1])
            uid = int(parts[2])
            db.approve_completion(comp_id, uid)
            bot.edit_message_text("✅ <b>ЗАЯВКА ОДОБРЕНА</b>\n\n+1 звезда начислена", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        return
    if data.startswith("rj_"):
        if user_id not in ADMIN_IDS:
            return
        parts = data.split("_")
        if len(parts) >= 3:
            comp_id = int(parts[1])
            uid = int(parts[2])
            db.reject_completion(comp_id, uid)
            bot.edit_message_text("❌ <b>ЗАЯВКА ОТКЛОНЕНА</b>", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        return

    # --- Админ: заявки на вывод ---
    if data.startswith("withdraw_page_"):
        page = int(data.split("_")[2])
        admin_withdrawals(call.message, page)
        return
    if data.startswith("view_gift_"):
        wd_id = int(data.split("_")[2])
        admin_view_gift(call, wd_id)
        return
    if data.startswith("view_channel_"):
        wd_id = int(data.split("_")[2])
        admin_view_channel(call, wd_id)
        return
    if data.startswith("ag_"):
        if user_id not in ADMIN_IDS:
            return
        parts = data.split("_")
        if len(parts) >= 5:
            wd_id = int(parts[1])
            uid = int(parts[2])
            gift = parts[3]
            stars = int(parts[4])
            db.approve_withdrawal_gift(wd_id, uid, gift, stars)
            bot.edit_message_text("✅ <b>ПОДАРОК ОТМЕЧЕН КАК ОТПРАВЛЕННЫЙ</b>", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        return
    if data.startswith("ac_"):
        if user_id not in ADMIN_IDS:
            return
        parts = data.split("_")
        if len(parts) >= 4:
            wd_id = int(parts[1])
            uid = int(parts[2])
            stars = int(parts[3])
            db.approve_withdrawal_channel(wd_id, uid, stars)
            bot.edit_message_text("✅ <b>ВЫВОД ПОДТВЕРЖДЕН</b>", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        return

    # --- Админ: саппорт ---
    if data.startswith("support_page_"):
        page = int(data.split("_")[2])
        admin_support(call.message, page)
        return
    if data.startswith("view_support_"):
        msg_id = int(data.split("_")[2])
        admin_view_support(call, msg_id)
        return
    if data.startswith("reply_"):
        if user_id not in ADMIN_IDS:
            return
        uid = int(data.split("_")[1])
        db.set_session(user_id, 'admin_reply', {'user_id': uid})
        bot.send_message(call.message.chat.id, "✍️ Напиши ответ для пользователя:")
        return
    if data.startswith("sr_"):
        if user_id not in ADMIN_IDS:
            return
        parts = data.split("_")
        if len(parts) >= 3:
            msg_id = int(parts[1])
            uid = int(parts[2])
            db.mark_support_read(msg_id)
            db.set_session(user_id, 'admin_reply', {'user_id': uid})
            bot.send_message(call.message.chat.id, "✍️ Напиши ответ для пользователя:")
        return

    if data == "noop":
        return

# Ответ админа пользователю
@bot.message_handler(func=lambda m: db.get_session(m.from_user.id) and db.get_session(m.from_user.id)['step'] == 'admin_reply' and m.from_user.id in ADMIN_IDS)
def admin_reply(message):
    session = db.get_session(message.from_user.id)
    user_id = session['data']['user_id']
    reply_text = message.text
    try:
        bot.send_message(user_id, f"🛟 <b>ОТВЕТ ОТ АДМИНИСТРАТОРА</b>\n\n{reply_text}", parse_mode='HTML')
        bot.send_message(message.chat.id, f"✅ Ответ отправлен пользователю")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Не удалось отправить сообщение: {e}")
    db.clear_session(message.from_user.id)

if __name__ == "__main__":
    print("=" * 50)
    print(f"🐻 {BOT_NAME} БОТ ЗАПУЩЕН")
    print(f"👑 Админы: {ADMIN_IDS}")
    print("=" * 50)
    if os.path.exists(DB_PATH):
        print("✅ База данных готова к работе")
    else:
        print("❌ Ошибка: База данных не создана!")
        sys.exit(1)
    bot.infinity_polling()