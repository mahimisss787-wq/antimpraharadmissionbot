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

# PREVIOUS MEMBERS DATA FOR AUTO-IMPORT TO MONGODB
PREVIOUS_STUDENTS = [
    {"userId": "8914751355", "name": "Mohit", "username": "@niistharajput", "preparation": "BPSC", "state": "MP"},
    {"userId": "8727877982", "name": "Shreya Singh", "username": "N/A", "preparation": "SSC", "state": "UP"},
    {"userId": "8048730537", "name": "Shivam", "username": "N/A", "preparation": "SSC", "state": "UP"},
    {"userId": "1216936280", "name": "Ajay shukla", "username": "@Wowhum", "preparation": "UPSC", "state": "UP"},
    {"userId": "8581382271", "name": "Nikku gupta", "username": "@Gupat_91", "preparation": "UPSC", "state": "Bihar"},
    {"userId": "6416451659", "name": "Mahi", "username": "N/A", "preparation": "UPSC", "state": "Bihar"},
    {"userId": "8560759903", "name": "Ak", "username": "N/A", "preparation": "BPSC", "state": "Bihar"},
    {"userId": "8691169222", "name": "Abhishek Kumar", "username": "N/A", "preparation": "UPSC", "state": "Bihar"},
    {"userId": "8615194107", "name": "Pritam Singh rajput", "username": "N/A", "preparation": "All competitive exams", "state": "Bihar"},
    {"userId": "6380680769", "name": "Riya Raj", "username": "N/A", "preparation": "Up police constable", "state": "UP"},
    {"userId": "7118259188", "name": "Babu rao ganpat Raao apte", "username": "@amitjha469", "preparation": "UPSC", "state": "WB"},
    {"userId": "8120287961", "name": "N Gupta", "username": "N/A", "preparation": "BPSC", "state": "Bihar"},
    {"userId": "7874637513", "name": "Rocky", "username": "N/A", "preparation": "SSC", "state": "Bihar"},
    {"userId": "8832346172", "name": "Radhe", "username": "N/A", "preparation": "Other", "state": "Bihar"},
    {"userId": "8521478087", "name": "Priyanka", "username": "N/A", "preparation": "SSC", "state": "Rajasthan"},
    {"userId": "1549916238", "name": "Jaya", "username": "N/A", "preparation": "BSSC", "state": "Bihar"},
    {"userId": "6017441443", "name": "Ssc", "username": "N/A", "preparation": "SSC", "state": "Bihar"},
    {"userId": "1488543107", "name": "Sharma ji", "username": "@Sharmaji7979", "preparation": "BPSC", "state": "Bihar"},
    {"userId": "7383971004", "name": "Idiot", "username": "N/A", "preparation": "Bihar Librarian", "state": "Bihar"},
    {"userId": "8170142646", "name": "Paridhi agrawal", "username": "N/A", "preparation": "BPSC", "state": "Bihar"},
    {"userId": "8466013841", "name": "Sonali kumari", "username": "N/A", "preparation": "Railway", "state": "Bihar"}
]

# MongoDB Setup
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

        # Seed all 21 previous members into MongoDB automatically
        for s in PREVIOUS_STUDENTS:
            admissions_col.update_one(
                {"userId": s["userId"]},
                {"$setOnInsert": {
                    "userId": s["userId"],
                    "name": s["name"],
                    "username": s["username"],
                    "preparation": s["preparation"],
                    "state": s["state"],
                    "date": "Imported Previous Member"
                }},
                upsert=True
            )

        logging.info("MongoDB initialized and all 21 previous members imported successfully!")
    except Exception as e:
        logging.error(f"MongoDB connection failed: {e}")
else:
    logging.warning("MONGO_URI not provided. Running with in-memory storage.")

# Initialize Telegram Bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

conversations = {}
admitted = {}
pending_approvals = {}  # Stores pending admission data until admin approves/rejects
broadcast_store = {}    # Stores broadcast message IDs for deletion

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
            # Only count as admitted if: has name, NOT imported, AND status is approved (or old records without status)
            if record and record.get("name") and record.get("date") != "Imported Previous Member":
                status = record.get("status", "approved")  # Old records without status are treated as approved
                if status == "approved":
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

def safe_delete_message(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def complete_admission_in_place(chat_id, user_id, username, first_name, name, preparation, state, target_msg_id=None):
    tz = pytz.timezone("Asia/Kolkata")
    formatted_date = datetime.now(tz).strftime("%d/%m/%Y, %I:%M:%S %p")
    
    row_data = {
        "name": name,
        "preparation": preparation,
        "state": state,
        "username": username,
        "firstName": first_name,
        "userId": str(user_id),
        "date": formatted_date,
        "status": "pending"  # Pending until admin approves
    }
    
    if str(user_id) in conversations:
        del conversations[str(user_id)]
        
    save_to_mongodb(row_data)
    
    # Store pending approval data for later use
    pending_approvals[str(user_id)] = {
        "chatId": chat_id,
        "name": name,
        "preparation": preparation,
        "state": state,
        "username": username,
        "firstName": first_name,
        "date": formatted_date,
        "targetMsgId": target_msg_id
    }
    
    # Show user a PENDING message (no invite link yet)
    pending_text = (
        f"📋 *Thank You for Registering!*\n\n"
        f"🎓 *Name:* {name}\n"
        f"📚 *Preparation:* {preparation}\n"
        f"📍 *State:* {state}\n\n"
        f"✅ Aapke details successfully submit ho gaye hain!\n"
        f"🔍 Humari team aapki details verify kar rahi hai. Complete hote hi aapko group link mil jayega."
    )
    
    if target_msg_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=target_msg_id, text=pending_text, parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, pending_text, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, pending_text, parse_mode="Markdown")
    
    # Send ADMIN an approval request with Accept/Reject buttons
    admin_text = (
        f"🆕 *New Admission Request!*\n\n"
        f"👤 Name: {name}\n"
        f"📚 Preparation: {preparation}\n"
        f"📍 State: {state}\n"
        f"🔗 Username: {username}\n"
        f"🆔 User ID: `{user_id}`\n"
        f"📅 Date: {formatted_date}\n\n"
        f"⬇️ *Accept ya Reject karein:*"
    )
    admin_markup = InlineKeyboardMarkup()
    admin_markup.add(
        InlineKeyboardButton("✅ Accept", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
    )
    try:
        bot.send_message(ADMIN_ID, admin_text, reply_markup=admin_markup, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to send approval request to Admin: {e}")

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

    bcast_id = str(int(time.time()))
    broadcast_store[bcast_id] = []

    adjusted_entities = None
    if not has_reply and message.entities and text_to_send:
        prefix_len = message.text.find(text_to_send)
        if prefix_len != -1:
            adjusted_entities = []
            for entity in message.entities:
                if entity.offset >= prefix_len:
                    import copy
                    e = copy.copy(entity)
                    e.offset -= prefix_len
                    adjusted_entities.append(e)

    def run_broadcast_task():
        success_count = 0
        failed_count = 0

        for target_id in target_user_ids:
            try:
                if has_reply:
                    sent = bot.copy_message(
                        chat_id=target_id,
                        from_chat_id=message.chat.id,
                        message_id=message.reply_to_message.message_id
                    )
                    msg_id = sent.message_id
                else:
                    if adjusted_entities:
                        sent = bot.send_message(chat_id=target_id, text=text_to_send, entities=adjusted_entities)
                    else:
                        sent = bot.send_message(chat_id=target_id, text=text_to_send, parse_mode="Markdown")
                    msg_id = sent.message_id
                    
                success_count += 1
                broadcast_store[bcast_id].append((target_id, msg_id))
                time.sleep(0.05)
            except Exception as e:
                failed_count += 1
                logging.warning(f"Could not send broadcast to user {target_id}: {e}")

        report_text = (
            f"📢 *Broadcast Summary Report*\n\n"
            f"👥 Total Target Users: `{len(target_user_ids)}` \n"
            f"✅ Successfully Delivered: `{success_count}`\n"
            f"🚫 Failed / Blocked: `{failed_count}`\n\n"
            f"💡 *Is broadcast ko sabhi members ke inbox se delete karne ke liye niche button dabayein:*"
        )
        report_markup = InlineKeyboardMarkup()
        report_markup.add(InlineKeyboardButton("🗑️ Delete This Broadcast", callback_data=f"delbcast_{bcast_id}"))
        
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text=report_text, reply_markup=report_markup, parse_mode="Markdown")
        except Exception:
            bot.send_message(message.chat.id, report_text, reply_markup=report_markup, parse_mode="Markdown")

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
