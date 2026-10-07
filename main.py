import os
import time
import logging
from datetime import datetime
import pytz
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
from flask import Flask
from pymongo import MongoClient
import certifi

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "8944237255:AAE3SqXZyukH-HpazVhkMJryIFD2BJK6zTM")
ADMIN_ID = os.getenv("ADMIN_ID", "6416451659")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "-1003493006883")
MONGO_URI = os.getenv("MONGO_URI")

# Setup Flask Server for Render Keep-Alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Antimprahar Admission Bot is alive and running 24/7!"

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# MongoDB Setup with SSL Certifi & Auto Database Creation
mongo_client = None
db = None
admissions_col = None

if MONGO_URI:
    try:
        mongo_client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000
        )
        db = mongo_client["antimprahar_db"]
        admissions_col = db["admissions"]
        
        # System initialization check
        admissions_col.update_one(
            {"userId": "system_init"},
            {"$set": {"system": "initialized", "status": "active"}},
            upsert=True
        )
        logging.info("MongoDB initialized and connected successfully!")
    except Exception as e:
        logging.error(f"MongoDB connection failed: {e}")
else:
    logging.warning("MONGO_URI not provided. Running with in-memory storage.")

# Initialize Telegram Bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

conversations = {}
admitted = {}

def track_user_activity(user_id, username="N/A", first_name="N/A"):
    user_id_str = str(user_id)
    if admissions_col is not None and user_id_str != "system_init":
        def _worker():
            try:
                admissions_col.update_one(
                    {"userId": user_id_str},
                    {"$setOnInsert": {
                        "userId": user_id_str,
                        "username": username,
                        "firstName": first_name,
                        "registeredAt": datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d/%m/%Y, %I:%M:%S %p")
                    }},
                    upsert=True
                )
            except Exception as e:
                logging.error(f"Failed to track user activity: {e}")
        threading.Thread(target=_worker, daemon=True).start()

def save_to_mongodb(row_data):
    if admissions_col is not None:
        def _worker():
            try:
                admissions_col.update_one(
                    {"userId": str(row_data["userId"])},
                    {"$set": row_data},
                    upsert=True
                )
                logging.info(f"Saved to MongoDB for User {row_data['userId']}")
            except Exception as e:
                logging.error(f"Failed save to MongoDB: {e}")
        threading.Thread(target=_worker, daemon=True).start()

def is_user_admitted(user_id):
    user_id_str = str(user_id)
    if user_id_str in admitted:
        return True
    if admissions_col is not None:
        try:
            record = admissions_col.find_one({"userId": user_id_str})
            if record and record.get("name"):
                admitted[user_id_str] = record
                return True
        except Exception as e:
            logging.error(f"MongoDB check skipped: {e}")
    return False

# --- KEYBOARD BUILDERS ---

def get_welcome_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📝 Start Admission Process", callback_data="start_admission"))
    return markup

def get_prep_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📚 UPSC", callback_data="prep_UPSC"),
        InlineKeyboardButton("🎯 SSC", callback_data="prep_SSC"),
        InlineKeyboardButton("🩺 NEET", callback_data="prep_NEET"),
        InlineKeyboardButton("⚡ JEE", callback_data="prep_JEE")
    )
    markup.add(InlineKeyboardButton("✍️ Other (Doosra Exam)", callback_data="prep_OTHER"))
    return markup

def get_state_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📍 UP", callback_data="state_UP"),
        InlineKeyboardButton("📍 Bihar", callback_data="state_Bihar"),
        InlineKeyboardButton("📍 MP", callback_data="state_MP"),
        InlineKeyboardButton("📍 Rajasthan", callback_data="state_Rajasthan"),
        InlineKeyboardButton("📍 Delhi", callback_data="state_Delhi")
    )
    markup.add(InlineKeyboardButton("🌐 Other State", callback_data="state_OTHER"))
    return markup

def get_fallback_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📝 Start Admission", callback_data="start_admission"))
    return markup

def complete_admission(chat_id, user_id, username, first_name, name, preparation, state):
    tz = pytz.timezone("Asia/Kolkata")
    formatted_date = datetime.now(tz).strftime("%d/%m/%Y, %I:%M:%S %p")
    
    row_data = {
        "name": name,
        "preparation": preparation,
        "state": state,
        "username": username,
        "firstName": first_name,
        "userId": str(user_id),
        "date": formatted_date
    }
    
    admitted[str(user_id)] = row_data
    if str(user_id) in conversations:
        del conversations[str(user_id)]
        
    save_to_mongodb(row_data)
    
    invite_link = "https://t.me"
    try:
        expire_time = int(time.time()) + 30
        res = bot.create_chat_invite_link(chat_id=GROUP_CHAT_ID, member_limit=1, expire_date=expire_time)
        invite_link = res.invite_link
    except Exception as e:
        logging.error(f"Failed to create chat invite link: {e}")

    success_text = (
        f"✅ *Admission Successful!*\n\n"
        f"🎓 Name: {name}\n"
        f"📚 Preparation: {preparation}\n"
        f"📍 State: {state}\n\n"
        f"⚡ Niche *Join Study Group* button par click karke group join karein. Link sirf *30 second* valid hai!"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚀 Join Study Group Now", url=invite_link))
    bot.send_message(chat_id, success_text, reply_markup=markup)
    
    admin_text = (
        f"🆕 *New Admission!*\n\n"
        f"👤 Name: {name}\n"
        f"📚 Preparation: {preparation}\n"
        f"📍 State: {state}\n"
        f"🔗 Username: {username}\n"
        f"🆔 User ID: {user_id}\n"
        f"📅 Date: {formatted_date}"
    )
    try:
        bot.send_message(ADMIN_ID, admin_text)
    except Exception as e:
        logging.error(f"Failed to notify Admin: {e}")

# --- BROADCAST COMMAND (ADMIN ONLY) ---

@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        bot.reply_to(message, "⛔ Aapke paas broadcast bhejne ki permission nahi hai.")
        return

    has_reply = message.reply_to_message is not None
    command_text = message.text.split(maxsplit=1)
    text_to_send = command_text[1].strip() if len(command_text) > 1 else ""

    if not has_reply and not text_to_send:
        guide_msg = (
            "📢 *Broadcast Command Usage Guide*\n\n"
            "**Option 1 (Text Broadcast):**\n"
            "`/broadcast Aapka Message Yahan Likhien`\n\n"
            "**Option 2 (Media Broadcast - Photo/Video/File):**\n"
            "Kisi bhi photo, video ya post ko bhej kar uspar **Reply** karke `/broadcast` likhein."
        )
        bot.reply_to(message, guide_msg)
        return

    target_user_ids = set()
    if admissions_col is not None:
        try:
            records = admissions_col.find({}, {"userId": 1})
            for r in records:
                u = r.get("userId")
                if u and u != "system_init":
                    target_user_ids.add(str(u))
        except Exception as e:
            logging.error(f"Failed to fetch users for broadcast: {e}")

    target_user_ids.update(admitted.keys())
    target_user_ids.update(conversations.keys())

    if not target_user_ids:
        bot.reply_to(message, "⚠️ Koi target users nahi mile broadcast ke liye.")
        return

    status_msg = bot.reply_to(message, f"⏳ *Broadcast processing...*\n\nTotal Users: `{len(target_user_ids)}` users ko message bheja ja raha hai...")

    def run_broadcast_task():
        success_count = 0
        failed_count = 0

        for target_id in target_user_ids:
            try:
                if has_reply:
                    bot.copy_message(
                        chat_id=target_id,
                        from_chat_id=message.chat.id,
                        message_id=message.reply_to_message.message_id
                    )
                else:
                    bot.send_message(chat_id=target_id, text=text_to_send, parse_mode="Markdown")
                success_count += 1
                time.sleep(0.05)
            except Exception as e:
                failed_count += 1
                logging.warning(f"Could not send broadcast to user {target_id}: {e}")

        report_text = (
            f"📢 *Broadcast Summary Report*\n\n"
            f"👥 Total Target Users: `{len(target_user_ids)}` \n"
            f"✅ Successfully Delivered: `{success_count}`\n"
            f"🚫 Failed / Blocked: `{failed_count}`"
        )
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text=report_text, parse_mode="Markdown")
        except Exception:
            bot.send_message(message.chat.id, report_text, parse_mode="Markdown")

    threading.Thread(target=run_broadcast_task, daemon=True).start()

# --- COMMAND HANDLERS ---

@bot.message_handler(commands=['resetall'])
def handle_reset_all(message):
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        return
    admitted.clear()
    conversations.clear()
    if admissions_col is not None:
        try:
            admissions_col.delete_many({"userId": {"$ne": "system_init"}})
        except Exception as e:
            logging.error(f"Failed to reset MongoDB: {e}")
    bot.reply_to(message, "🧹 *All Data Cleared!*\n\nSabhi users ka admission record delete kar diya gaya hai.")

@bot.message_handler(commands=['reset'])
def handle_reset_user(message):
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        return
    
    parts = message.text.split(maxsplit=1)
    target_id = parts[1].strip() if len(parts) > 1 else ""
    
    if not target_id or target_id.lower() in ['me', 'self']:
        target_id = user_id
        
    was_admitted = is_user_admitted(target_id)
    
    if was_admitted:
        admitted.pop(target_id, None)
        conversations.pop(target_id, None)
        if admissions_col is not None:
            try:
                admissions_col.delete_one({"userId": target_id})
            except Exception as e:
                logging.error(f"Failed to delete user from MongoDB: {e}")
        bot.reply_to(message, f"✅ *Reset Successful!*\n\nUser ID: `{target_id}` ka admission record remove kar diya gaya hai.")
    else:
        bot.reply_to(message, f"⚠️ *User Not Found!*\n\nUser ID: `{target_id}` ka koi admission record nahi mila.")

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = str(message.from_user.id)
    conversations.pop(user_id, None)
    
    track_user_activity(user_id, message.from_user.username, message.from_user.first_name)

    welcome_text = (
        "👋 Welcome to *Study Group Admission Bot*!\n\n"
        "Admission process shuru karne ke liye niche button par click karein 👇"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_welcome_keyboard())

@bot.message_handler(commands=['admission'])
def handle_admission_command(message):
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    track_user_activity(user_id, message.from_user.username, message.from_user.first_name)

    if is_user_admitted(user_id):
        bot.send_message(chat_id, "⚠️ Aap pehle se admission le chuke ho!\n\nDobara admission nahi le sakte. Agar koi issue hai toh admin se contact karein.")
        return
        
    conversations[user_id] = {"step": "awaiting_name", "chatId": chat_id}
    bot.send_message(chat_id, "📋 *Study Group Admission*\n\nWelcome! Admission process shuru karte hain.\n\n✏️ Apna *Full Name* likhkar bhejein:")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    chat_id = str(call.message.chat.id)
    user_id = str(call.from_user.id)
    username = f"@{call.from_user.username}" if call.from_user.username else "N/A"
    first_name = call.from_user.first_name or "N/A"
    data = call.data
    
    track_user_activity(user_id, call.from_user.username, call.from_user.first_name)

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
        
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=None)
    except Exception:
        pass
        
    if is_user_admitted(user_id):
        bot.send_message(chat_id, "⚠️ Aap pehle se admission le chuke ho!\n\nDobara admission nahi le sakte. Agar koi issue hai toh admin se contact karein.")
        return

    if data == "start_admission":
        conversations[user_id] = {"step": "awaiting_name", "chatId": chat_id}
        bot.send_message(chat_id, "📋 *Study Group Admission*\n\nWelcome! Admission process shuru karte hain.\n\n✏️ Apna *Full Name* likhkar bhejein:")
        return

    convo = conversations.get(user_id)
    if not convo:
        bot.send_message(chat_id, "🤔 Pehle /admission command bhejein ya niche button click karke admission process shuru karein.", reply_markup=get_fallback_keyboard())
        return

    if convo.get("step") == "awaiting_preparation":
        if data.startswith("prep_"):
            prep_choice = data.replace("prep_", "")
            if prep_choice == "OTHER":
                convo["step"] = "awaiting_preparation_custom"
                bot.send_message(chat_id, "✍️ Apne exam ka naam type karke bhejein:\n\n(Example: Banking, Board Exams, Defence, etc.)")
            else:
                convo["preparation"] = prep_choice
                convo["step"] = "awaiting_state"
                bot.send_message(chat_id, "📍 Aap kaunse *State* se ho?\n\n(Niche diye gaye buttons me se select karein 👇)", reply_markup=get_state_keyboard())
        return

    if convo.get("step") == "awaiting_state":
        if data.startswith("state_"):
            state_choice = data.replace("state_", "")
            if state_choice == "OTHER":
                convo["step"] = "awaiting_state_custom"
                bot.send_message(chat_id, "🌐 Apne *State* ka naam type karke bhejein:")
            else:
                name = convo.get("name", "N/A")
                prep = convo.get("preparation", "N/A")
                complete_admission(chat_id, user_id, username, first_name, name, prep, state_choice)
        return

@bot.message_handler(func=lambda msg: True, content_types=['text'])
def handle_text_messages(message):
    if message.chat.type != 'private':
        return
        
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    username = f"@{message.from_user.username}" if message.from_user.username else "N/A"
    first_name = message.from_user.first_name or "N/A"
    text = message.text.strip()
    
    track_user_activity(user_id, message.from_user.username, message.from_user.first_name)

    if is_user_admitted(user_id):
        bot.send_message(chat_id, "⚠️ Aap pehle se admission le chuke ho!\n\nDobara admission nahi le sakte. Agar koi issue hai toh admin se contact karein.")
        return

    convo = conversations.get(user_id)
    if not convo:
        bot.send_message(chat_id, "🤔 Pehle /admission command bhejein ya niche button click karke admission process shuru karein.", reply_markup=get_fallback_keyboard())
        return

    if convo.get("step") == "awaiting_name":
        convo["name"] = text
        convo["step"] = "awaiting_preparation"
        bot.send_message(chat_id, "📚 Aap kis exam ki *preparation* kar rahe ho?\n\n(Niche diye gaye buttons me se select karein 👇)", reply_markup=get_prep_keyboard())
        return

    if convo.get("step") == "awaiting_preparation_custom":
        convo["preparation"] = text
        convo["step"] = "awaiting_state"
        bot.send_message(chat_id, "📍 Aap kaunse *State* se ho?\n\n(Niche diye gaye buttons me se select karein 👇)", reply_markup=get_state_keyboard())
        return

    if convo.get("step") == "awaiting_state_custom":
        name = convo.get("name", "N/A")
        prep = convo.get("preparation", "N/A")
        complete_admission(chat_id, user_id, username, first_name, name, prep, text)
        return

    if convo.get("step") == "awaiting_preparation":
        bot.send_message(chat_id, "📚 Kripya niche diye gaye buttons me se select karein 👇", reply_markup=get_prep_keyboard())
        return

    if convo.get("step") == "awaiting_state":
        bot.send_message(chat_id, "📍 Kripya niche diye gaye buttons me se select karein 👇", reply_markup=get_state_keyboard())
        return

if __name__ == "__main__":
    logging.info("Bot starting with Broadcast feature...")
    
    threading.Thread(target=run_flask, daemon=True).start()

    try:
        bot.remove_webhook(drop_pending_updates=True)
        time.sleep(1)
        logging.info("Existing webhook removed successfully.")
    except Exception as e:
        logging.warning(f"Could not remove webhook: {e}")
        
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            logging.error(f"Polling error encountered: {e}. Retrying in 5 seconds...")
            time.sleep(5)
