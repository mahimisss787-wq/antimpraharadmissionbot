import os
import time
import logging
import re
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

# Setup Flask Server for 24/7 Keep-Alive (Railway / Render)
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
                    "date": "Imported Previous Member",
                    "status": "approved"
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
admin_state = {}        # Admin interactive prompt states (e.g. awaiting_search)

# --- UTILITY & HELPER FUNCTIONS ---

def escape_md(text):
    """Safely escapes markdown characters to prevent Telegram formatting crashes."""
    if text is None:
        return "N/A"
    s = str(text)
    for ch in ['_', '*', '`', '[']:
        s = s.replace(ch, f"\\{ch}")
    return s

def safe_delete_message(chat_id, message_id):
    """Safely deletes a message without crashing if already deleted."""
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def track_user_activity(user_id, username="N/A", first_name="N/A"):
    user_id_str = str(user_id)
    if admissions_col is not None and user_id_str != "system_init":
        def _worker():
            try:
                admissions_col.update_one(
                    {"userId": user_id_str},
                    {"$setOnInsert": {
                        "userId": user_id_str,
                        "username": username or "N/A",
                        "firstName": first_name or "N/A",
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
            if record and record.get("name") and record.get("date") != "Imported Previous Member":
                status = record.get("status", "approved")
                if status == "approved":
                    admitted[user_id_str] = record
                    return True
        except Exception as e:
            logging.error(f"MongoDB check skipped: {e}")
    return False

def find_students(query_str):
    """Searches students by Name, Username, First Name, State, Preparation or User ID."""
    query_clean = query_str.strip().lstrip("@")
    results = []
    seen_ids = set()

    if admissions_col is not None:
        try:
            regex = re.compile(re.escape(query_clean), re.IGNORECASE)
            mongo_results = list(admissions_col.find({
                "$and": [
                    {"userId": {"$ne": "system_init"}},
                    {"$or": [
                        {"name": regex},
                        {"username": regex},
                        {"firstName": regex},
                        {"userId": regex},
                        {"preparation": regex},
                        {"state": regex}
                    ]}
                ]
            }).limit(15))
            for r in mongo_results:
                uid = str(r.get("userId"))
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    results.append(r)
        except Exception as e:
            logging.error(f"Search error in MongoDB: {e}")

    # Fallback / augment with PREVIOUS_STUDENTS
    q_lower = query_clean.lower()
    for s in PREVIOUS_STUDENTS:
        uid = str(s.get("userId"))
        if uid not in seen_ids:
            if (q_lower in s.get("name", "").lower() or
                q_lower in s.get("username", "").lower() or
                q_lower in uid or
                q_lower in s.get("preparation", "").lower() or
                q_lower in s.get("state", "").lower()):
                seen_ids.add(uid)
                results.append(s)

    return results

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

# --- ADMIN DASHBOARD & CARDS BUILDERS ---

def send_admin_dashboard(chat_id, target_msg_id=None):
    """Builds and displays the interactive Admin Control Center."""
    total = len(PREVIOUS_STUDENTS)
    approved = 0
    pending = 0
    rejected = 0

    if admissions_col is not None:
        try:
            total = admissions_col.count_documents({"userId": {"$ne": "system_init"}})
            approved = admissions_col.count_documents({"status": "approved"})
            pending = admissions_col.count_documents({"status": "pending"})
            rejected = admissions_col.count_documents({"status": "rejected"})
        except Exception as e:
            logging.error(f"Failed to fetch counts for dashboard: {e}")

    dash_text = (
        f"🎛️ *Antimprahar Admin Control Center*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 *Total Students:* `{total}`\n"
        f"✅ *Approved:* `{approved}`\n"
        f"⏳ *Pending Review:* `{pending}`\n"
        f"❌ *Rejected:* `{rejected}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Neeche diye gaye buttons se action select karein 👇"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🔍 Search Student", callback_data="dash_search"),
        InlineKeyboardButton(f"⏳ Pending ({pending})", callback_data="dash_pending")
    )
    markup.add(
        InlineKeyboardButton("📊 Members Summary", callback_data="dash_members"),
        InlineKeyboardButton("📢 Broadcast", callback_data="dash_broadcast")
    )
    markup.add(
        InlineKeyboardButton("🔄 Refresh Stats", callback_data="dash_refresh"),
        InlineKeyboardButton("🗑️ Close Panel", callback_data="dismiss_msg")
    )

    if target_msg_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=target_msg_id, text=dash_text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, dash_text, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, dash_text, reply_markup=markup, parse_mode="Markdown")

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
    
    # Store pending approval data
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
    
    # Show user a PENDING message
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
    
    # Send ADMIN an approval request card
    safe_name = escape_md(name)
    safe_prep = escape_md(preparation)
    safe_state = escape_md(state)
    safe_uname = escape_md(username)
    
    admin_text = (
        f"🆕 *New Admission Request!*\n\n"
        f"👤 Name: {safe_name}\n"
        f"📚 Preparation: {safe_prep}\n"
        f"📍 State: {safe_state}\n"
        f"🔗 Username: {safe_uname}\n"
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

# --- SEARCH EXECUTION HELPER ---

def execute_student_search(chat_id, query_str, edit_msg_id=None):
    """Performs search and sends or edits formatted results with interactive action buttons."""
    results = find_students(query_str)
    
    if not results:
        no_res_text = (
            f"🔍 *Search Results for:* \"{escape_md(query_str)}\"\n\n"
            f"❌ Koi student record nahi mila.\n\n"
            f"💡 *Tip:* Name ki spelling check karein ya User ID / Username daalkar try karein."
        )
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🔍 Try Again", callback_data="dash_search"),
            InlineKeyboardButton("🗑️ Dismiss", callback_data="dismiss_msg")
        )
        if edit_msg_id:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=edit_msg_id, text=no_res_text, reply_markup=markup, parse_mode="Markdown")
                return
            except Exception:
                pass
        bot.send_message(chat_id, no_res_text, reply_markup=markup, parse_mode="Markdown")
        return

    # If results found, display cleanly (up to 5 per card)
    count = len(results)
    header = f"🔍 *Found {count} match{'es' if count > 1 else ''} for:* \"`{escape_md(query_str)}`\"\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # If exactly 1 result, show rich single card
    if count == 1:
        r = results[0]
        uid = str(r.get("userId", "N/A"))
        name = escape_md(r.get("name", "N/A"))
        uname = escape_md(r.get("username", "N/A"))
        prep = escape_md(r.get("preparation", "N/A"))
        state = escape_md(r.get("state", "N/A"))
        date = escape_md(r.get("date", "N/A"))
        status = r.get("status", "approved" if r.get("date") == "Imported Previous Member" else "pending")
        status_emoji = {"approved": "✅ Approved", "pending": "⏳ Pending", "rejected": "❌ Rejected"}.get(status, "📦 Member")
        
        card_text = (
            f"{header}"
            f"👤 *Name:* {name}\n"
            f"🆔 *User ID:* `{uid}`\n"
            f"🔗 *Username:* {uname}\n"
            f"📚 *Preparation:* {prep}\n"
            f"📍 *State:* {state}\n"
            f"📅 *Admission Date:* {date}\n"
            f"🏷️ *Status:* {status_emoji}\n"
        )
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🔄 Reset Student", callback_data=f"ask_reset_{uid}"),
            InlineKeyboardButton("ℹ️ Full Info", callback_data=f"view_info_{uid}")
        )
        markup.add(
            InlineKeyboardButton("🔍 Search Again", callback_data="dash_search"),
            InlineKeyboardButton("🗑️ Close", callback_data="dismiss_msg")
        )
        if edit_msg_id:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=edit_msg_id, text=card_text, reply_markup=markup, parse_mode="Markdown")
                return
            except Exception:
                pass
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
        return

    # If multiple results (show top 5 with individual reset buttons)
    body_lines = []
    markup = InlineKeyboardMarkup()
    
    for i, r in enumerate(results[:5], 1):
        uid = str(r.get("userId", "N/A"))
        name = escape_md(r.get("name", "N/A"))
        uname = escape_md(r.get("username", "N/A"))
        prep = escape_md(r.get("preparation", "N/A"))
        status = r.get("status", "approved" if r.get("date") == "Imported Previous Member" else "pending")
        status_icon = {"approved": "✅", "pending": "⏳", "rejected": "❌"}.get(status, "📦")
        
        body_lines.append(
            f"{status_icon} *{i}. {name}* ({uname})\n"
            f"    🆔 `{uid}` | 📚 {prep}"
        )
        markup.add(
            InlineKeyboardButton(f"🔄 Reset #{i} ({name[:12]})", callback_data=f"ask_reset_{uid}"),
            InlineKeyboardButton(f"ℹ️ Info #{i}", callback_data=f"view_info_{uid}")
        )

    if count > 5:
        body_lines.append(f"\n⚠️ _Showing top 5 of {count} matches. Please narrow query if needed._")

    full_text = header + "\n".join(body_lines)
    markup.add(
        InlineKeyboardButton("🔍 Search Again", callback_data="dash_search"),
        InlineKeyboardButton("🗑️ Close", callback_data="dismiss_msg")
    )
    
    if edit_msg_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=edit_msg_id, text=full_text, reply_markup=markup, parse_mode="Markdown")
            return
        except Exception:
            pass
    bot.send_message(chat_id, full_text, reply_markup=markup, parse_mode="Markdown")

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

# --- COMMAND HANDLERS (ADMIN & USERS) ---

@bot.message_handler(commands=['admin', 'panel'])
def handle_admin_panel(message):
    """Opens the Admin Control Center and cleans the trigger command."""
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        return
    safe_delete_message(message.chat.id, message.message_id)
    send_admin_dashboard(message.chat.id)

@bot.message_handler(commands=['search'])
def handle_search_command(message):
    """Search for students by Name, Username, or ID."""
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        return

    safe_delete_message(message.chat.id, message.message_id)
    parts = message.text.split(maxsplit=1)
    
    if len(parts) > 1 and parts[1].strip():
        query = parts[1].strip()
        execute_student_search(message.chat.id, query)
    else:
        # Ask for query interactively
        prompt_text = (
            "🔍 *Search Student*\n\n"
            "Kisko search karna hai? Student ka **Name**, **Username** (jaise `@username`), ya **User ID** likhkar bhejein:\n\n"
            "_Example:_ `Mohit` ya `@niistharajput` ya `8305041634`"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Cancel", callback_data="dismiss_msg"))
        sent = bot.send_message(message.chat.id, prompt_text, reply_markup=markup, parse_mode="Markdown")
        admin_state[user_id] = {"action": "awaiting_search", "prompt_msg_id": sent.message_id}

@bot.message_handler(commands=['info'])
def handle_info(message):
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        return
    
    parts = message.text.split(maxsplit=1)
    target_id = parts[1].strip() if len(parts) > 1 else ""
    
    # Support replying to a message
    if not target_id and message.reply_to_message:
        reply_text = message.reply_to_message.text or ""
        match = re.search(r"User ID:\s*`?(\d+)`?", reply_text)
        if match:
            target_id = match.group(1)
        elif message.reply_to_message.forward_from:
            target_id = str(message.reply_to_message.forward_from.id)
    
    safe_delete_message(message.chat.id, message.message_id)
    
    if not target_id:
        bot.send_message(message.chat.id, "⚠️ *Usage:* `/info <User_ID ya Name>` ya kisi card par **Reply** karke `/info` likhein.", parse_mode="Markdown")
        return
    
    # If not purely digits, use search
    if not target_id.isdigit():
        execute_student_search(message.chat.id, target_id)
        return
    
    record = None
    if admissions_col is not None:
        try:
            record = admissions_col.find_one({"userId": target_id})
        except Exception as e:
            logging.error(f"Failed to fetch user info: {e}")
    
    if not record:
        for s in PREVIOUS_STUDENTS:
            if s.get("userId") == target_id:
                record = s
                break
                
    if not record:
        bot.send_message(message.chat.id, f"❌ User ID `{target_id}` ka koi record nahi mila.", parse_mode="Markdown")
        return

    name = escape_md(record.get("name", "N/A"))
    preparation = escape_md(record.get("preparation", "N/A"))
    state = escape_md(record.get("state", "N/A"))
    username = escape_md(record.get("username", "N/A"))
    first_name = escape_md(record.get("firstName", "N/A"))
    date = escape_md(record.get("date", "N/A"))
    status = record.get("status", "approved" if record.get("date") == "Imported Previous Member" else "pending")
    registered_at = escape_md(record.get("registeredAt", "N/A"))
    
    status_emoji = {"approved": "✅ Approved", "pending": "⏳ Pending", "rejected": "❌ Rejected"}.get(status, "📦 Member")
    
    info_text = (
        f"📋 *Student Details Card*\n\n"
        f"👤 *Name:* {name}\n"
        f"🆔 *User ID:* `{target_id}`\n"
        f"🔗 *Username:* {username}\n"
        f"📛 *First Name:* {first_name}\n"
        f"📚 *Preparation:* {preparation}\n"
        f"📍 *State:* {state}\n"
        f"📅 *Admission Date:* {date}\n"
        f"🕐 *First Seen:* {registered_at}\n"
        f"🏷️ *Status:* {status_emoji}"
    )
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🔄 Reset User", callback_data=f"ask_reset_{target_id}"),
        InlineKeyboardButton("🗑️ Clear", callback_data="dismiss_msg")
    )
    bot.send_message(message.chat.id, info_text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['members'])
def handle_members(message):
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        return
    
    safe_delete_message(message.chat.id, message.message_id)

    if admissions_col is None:
        bot.send_message(message.chat.id, "⚠️ MongoDB connected nahi hai. Data dekh nahi sakte.")
        return
    
    try:
        parts = message.text.split(maxsplit=1)
        status_filter = parts[1].strip().lower() if len(parts) > 1 else None
        
        query = {"userId": {"$ne": "system_init"}}
        if status_filter in ["approved", "pending", "rejected"]:
            query["status"] = status_filter
        
        records = list(admissions_col.find(query).sort("date", -1))
        
        if not records:
            filter_text = f" ({status_filter})" if status_filter else ""
            bot.send_message(message.chat.id, f"📭 Koi student record nahi mila{filter_text}.")
            return
        
        total = len(records)
        approved_count = sum(1 for r in records if r.get("status") == "approved")
        pending_count = sum(1 for r in records if r.get("status") == "pending")
        rejected_count = sum(1 for r in records if r.get("status") == "rejected")
        imported_count = sum(1 for r in records if r.get("date") == "Imported Previous Member")
        
        header = (
            f"📊 *Members Summary*\n\n"
            f"👥 Total: `{total}` | ✅ Approved: `{approved_count}`\n"
            f"⏳ Pending: `{pending_count}` | ❌ Rejected: `{rejected_count}`\n"
            f"📦 Imported: `{imported_count}`\n"
            f"{'─' * 30}\n\n"
        )
        
        member_lines = []
        for i, r in enumerate(records[:40], 1):
            name = escape_md(r.get("name", "N/A"))
            uid = r.get("userId", "N/A")
            prep = escape_md(r.get("preparation", "N/A"))
            status = r.get("status", "approved" if r.get("date") == "Imported Previous Member" else "pending")
            status_emoji = {"approved": "✅", "pending": "⏳", "rejected": "❌"}.get(status, "📦")
            
            member_lines.append(
                f"{status_emoji} *{i}. {name}*\n"
                f"    🆔 `{uid}` | 📚 {prep}\n"
            )
        
        full_text = header + "\n".join(member_lines)
        if total > 40:
            full_text += f"\n⚠️ _Sirf pehle 40 dikha rahe hain. Kisi specific student ko dhoondhne ke liye `/search <Name>` use karein._"
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🔍 Search Student", callback_data="dash_search"),
            InlineKeyboardButton("🗑️ Close List", callback_data="dismiss_msg")
        )
        bot.send_message(message.chat.id, full_text, reply_markup=markup, parse_mode="Markdown")
            
    except Exception as e:
        logging.error(f"Failed to fetch members: {e}")
        bot.send_message(message.chat.id, f"⚠️ Error: {e}")

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

@bot.message_handler(commands=['reset', 'remove'])
def handle_reset_user(message):
    """Upgraded /reset command: Supports numeric ID, Name, or message Reply, with clean confirmation."""
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        return
    
    parts = message.text.split(maxsplit=1)
    target = parts[1].strip() if len(parts) > 1 else ""
    
    # Check if replying to an approval card or user message
    if not target and message.reply_to_message:
        reply_text = message.reply_to_message.text or ""
        match = re.search(r"User ID:\s*`?(\d+)`?", reply_text)
        if match:
            target = match.group(1)
        elif message.reply_to_message.forward_from:
            target = str(message.reply_to_message.forward_from.id)
            
    safe_delete_message(message.chat.id, message.message_id)

    if not target:
        prompt_text = (
            "⚠️ *Reset / Remove Usage:*\n\n"
            "• `/reset <User_ID>` (Direct reset by ID)\n"
            "• `/reset <Name>` (Reset by Student Name)\n"
            "• Ya `/admin` kholkar *Search Student* dabayein."
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🗑️ Dismiss", callback_data="dismiss_msg"))
        bot.send_message(message.chat.id, prompt_text, reply_markup=markup, parse_mode="Markdown")
        return

    # If target is not numeric, search by Name / Username
    if not target.isdigit():
        execute_student_search(message.chat.id, target)
        return

    # If numeric ID, show safety confirmation
    target_id = target
    rec = None
    if admissions_col is not None:
        try:
            rec = admissions_col.find_one({"userId": target_id})
        except Exception:
            pass
            
    name = escape_md(rec.get("name", "Student")) if rec else "Student"

    confirm_text = (
        f"⚠️ *Reset Confirmation*\n\n"
        f"Kya aap sach me is student ka admission record delete karna chahte hain?\n\n"
        f"👤 *Name:* {name}\n"
        f"🆔 *User ID:* `{target_id}`\n\n"
        f"⚠️ _Delete karne ke baad yeh user dobara fresh admission le sakega._"
    )
    confirm_markup = InlineKeyboardMarkup()
    confirm_markup.add(
        InlineKeyboardButton("✅ Haan, Reset Karein", callback_data=f"confirm_reset_{target_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data="dismiss_msg")
    )
    bot.send_message(message.chat.id, confirm_text, reply_markup=confirm_markup, parse_mode="Markdown")

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
        
    prompt_msg = bot.send_message(chat_id, "📋 *Study Group Admission*\n\nWelcome! Admission process shuru karte hain.\n\n✏️ Apna *Full Name* likhkar bhejein:")
    conversations[user_id] = {"step": "awaiting_name", "chatId": chat_id, "msgId": prompt_msg.message_id}

# --- CALLBACK QUERY HANDLER ---

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

    # --- DISMISS / CLEAR MESSAGE ---
    if data == "dismiss_msg":
        safe_delete_message(chat_id, call.message.message_id)
        return

    # --- ADMIN DASHBOARD ACTIONS ---
    if data == "dash_refresh" and user_id == str(ADMIN_ID):
        send_admin_dashboard(chat_id, target_msg_id=call.message.message_id)
        return

    if data == "dash_search" and user_id == str(ADMIN_ID):
        prompt_text = (
            "🔍 *Search Student*\n\n"
            "Kisko search karna hai? Student ka **Name**, **Username** (jaise `@username`), ya **User ID** likhkar bhejein:\n\n"
            "_Example:_ `Mohit` ya `@niistharajput` ya `8305041634`"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Dashboard", callback_data="dash_refresh"))
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=prompt_text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
        admin_state[user_id] = {"action": "awaiting_search", "prompt_msg_id": call.message.message_id}
        return

    if data == "dash_members" and user_id == str(ADMIN_ID):
        call.message.text = "/members"
        handle_members(call.message)
        return

    if data == "dash_broadcast" and user_id == str(ADMIN_ID):
        bcast_info = (
            "📢 *Broadcast Help*\n\n"
            "Broadcast bhejne ke 2 tareeqe hain:\n\n"
            "1️⃣ **Text Message:**\n"
            "`/broadcast Aapka message yahan`\n\n"
            "2️⃣ **Photo / Video / Audio:**\n"
            "Kisi bhi post ko bhej kar uspar **Reply** karke `/broadcast` likhein."
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Dashboard", callback_data="dash_refresh"))
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=bcast_info, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
        return

    if data == "dash_pending" and user_id == str(ADMIN_ID):
        pending_list = []
        if admissions_col is not None:
            try:
                pending_list = list(admissions_col.find({"status": "pending"}))
            except Exception as e:
                logging.error(f"Failed to query pending: {e}")

        if not pending_list:
            text = "✅ *All Caught Up!*\n\nFilhal koi pending admission request nahi hai."
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Back to Dashboard", callback_data="dash_refresh"))
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                pass
            return

        text = f"⏳ *Pending Admission Requests ({len(pending_list)})*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        markup = InlineKeyboardMarkup()
        for p in pending_list[:5]:
            uid = str(p.get("userId"))
            name = escape_md(p.get("name", "N/A"))
            prep = escape_md(p.get("preparation", "N/A"))
            text += f"• *{name}* (ID: `{uid}`) - 📚 {prep}\n"
            markup.row(
                InlineKeyboardButton(f"✅ Accept ({name[:10]})", callback_data=f"approve_{uid}"),
                InlineKeyboardButton(f"❌ Reject", callback_data=f"reject_{uid}")
            )
        markup.add(InlineKeyboardButton("🔙 Back to Dashboard", callback_data="dash_refresh"))
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
        return

    # --- RESET FLOW (ASK & CONFIRM) ---
    if data.startswith("ask_reset_") and user_id == str(ADMIN_ID):
        target_uid = data.replace("ask_reset_", "")
        rec = None
        if admissions_col is not None:
            try:
                rec = admissions_col.find_one({"userId": target_uid})
            except Exception:
                pass
        if not rec:
            for s in PREVIOUS_STUDENTS:
                if s.get("userId") == target_uid:
                    rec = s
                    break

        name = escape_md(rec.get("name", "Student")) if rec else "Student"
        confirm_text = (
            f"⚠️ *Reset Confirmation*\n\n"
            f"Kya aap sach me is student ka admission record delete karna chahte hain?\n\n"
            f"👤 *Name:* {name}\n"
            f"🆔 *User ID:* `{target_uid}`\n\n"
            f"⚠️ _Delete karne ke baad yeh user dobara fresh admission le sakega._"
        )
        confirm_markup = InlineKeyboardMarkup()
        confirm_markup.add(
            InlineKeyboardButton("✅ Haan, Reset Karein", callback_data=f"confirm_reset_{target_uid}"),
            InlineKeyboardButton("❌ Cancel", callback_data="dismiss_msg")
        )
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=confirm_text, reply_markup=confirm_markup, parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, confirm_text, reply_markup=confirm_markup, parse_mode="Markdown")
        return

    if data.startswith("confirm_reset_") and user_id == str(ADMIN_ID):
        target_uid = data.replace("confirm_reset_", "")
        admitted.pop(target_uid, None)
        conversations.pop(target_uid, None)
        pending_approvals.pop(target_uid, None)
        
        deleted_name = "Student"
        if admissions_col is not None:
            try:
                rec = admissions_col.find_one({"userId": target_uid})
                if rec and rec.get("name"):
                    deleted_name = rec["name"]
                admissions_col.delete_one({"userId": target_uid})
            except Exception as e:
                logging.error(f"Failed to reset from MongoDB: {e}")
                
        success_text = (
            f"✅ *Reset Successful!*\n\n"
            f"👤 Student: *{escape_md(deleted_name)}*\n"
            f"🆔 User ID: `{target_uid}`\n\n"
            f"Record delete kar diya gaya hai. Yeh user ab dobara fresh admission le sakta hai."
        )
        done_markup = InlineKeyboardMarkup()
        done_markup.add(
            InlineKeyboardButton("🔍 Search Again", callback_data="dash_search"),
            InlineKeyboardButton("🗑️ Clear", callback_data="dismiss_msg")
        )
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=success_text, reply_markup=done_markup, parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, success_text, reply_markup=done_markup, parse_mode="Markdown")
        return

    # --- VIEW FULL INFO ---
    if data.startswith("view_info_") and user_id == str(ADMIN_ID):
        target_uid = data.replace("view_info_", "")
        rec = None
        if admissions_col is not None:
            try:
                rec = admissions_col.find_one({"userId": target_uid})
            except Exception:
                pass
        if not rec:
            for s in PREVIOUS_STUDENTS:
                if s.get("userId") == target_uid:
                    rec = s
                    break

        if not rec:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"❌ Record not found for User ID `{target_uid}`.", parse_mode="Markdown")
            except Exception:
                pass
            return

        name = escape_md(rec.get("name", "N/A"))
        preparation = escape_md(rec.get("preparation", "N/A"))
        state = escape_md(rec.get("state", "N/A"))
        username_val = escape_md(rec.get("username", "N/A"))
        first_name_val = escape_md(rec.get("firstName", "N/A"))
        date = escape_md(rec.get("date", "N/A"))
        status = rec.get("status", "approved" if rec.get("date") == "Imported Previous Member" else "pending")
        registered_at = escape_md(rec.get("registeredAt", "N/A"))
        status_emoji = {"approved": "✅ Approved", "pending": "⏳ Pending", "rejected": "❌ Rejected"}.get(status, "📦 Member")

        info_text = (
            f"📋 *Student Details*\n\n"
            f"👤 *Name:* {name}\n"
            f"🆔 *User ID:* `{target_uid}`\n"
            f"🔗 *Username:* {username_val}\n"
            f"📛 *First Name:* {first_name_val}\n"
            f"📚 *Preparation:* {preparation}\n"
            f"📍 *State:* {state}\n"
            f"📅 *Admission Date:* {date}\n"
            f"🕐 *First Seen:* {registered_at}\n"
            f"🏷️ *Status:* {status_emoji}"
        )
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🔄 Reset User", callback_data=f"ask_reset_{target_uid}"),
            InlineKeyboardButton("🗑️ Clear", callback_data="dismiss_msg")
        )
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=info_text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, info_text, reply_markup=markup, parse_mode="Markdown")
        return

    # --- ADMIN APPROVAL / REJECTION HANDLING ---
    if data.startswith("approve_") and user_id == str(ADMIN_ID):
        target_user_id = data.replace("approve_", "")
        pending = pending_approvals.get(target_user_id)
        
        # If not in memory, check MongoDB
        if not pending and admissions_col is not None:
            try:
                rec = admissions_col.find_one({"userId": target_user_id})
                if rec:
                    pending = {
                        "chatId": str(rec.get("userId")),
                        "name": rec.get("name", "Student"),
                        "preparation": rec.get("preparation", "N/A"),
                        "state": rec.get("state", "N/A"),
                        "username": rec.get("username", "N/A"),
                        "date": rec.get("date", "N/A")
                    }
            except Exception:
                pass

        if not pending:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=call.message.text + "\n\n⚠️ *Already processed or expired.*", parse_mode="Markdown")
            except Exception:
                pass
            return
        
        # Mark as admitted
        admitted[target_user_id] = pending
        
        # Update MongoDB status to approved
        if admissions_col is not None:
            def _approve_worker():
                try:
                    admissions_col.update_one(
                        {"userId": target_user_id},
                        {"$set": {"status": "approved"}}
                    )
                except Exception as e:
                    logging.error(f"Failed to update approval status: {e}")
            threading.Thread(target=_approve_worker, daemon=True).start()
        
        # Generate invite link for the user
        invite_link = "https://t.me"
        try:
            expire_time = int(time.time()) + 300  # 5 minute valid link
            res = bot.create_chat_invite_link(chat_id=GROUP_CHAT_ID, member_limit=1, expire_date=expire_time)
            invite_link = res.invite_link
        except Exception as e:
            logging.error(f"Failed to create invite link: {e}")
        
        # Send SUCCESS message to user with invite link
        user_chat_id = pending["chatId"]
        success_text = (
            f"🥳 *Congratulations! Admission Confirmed*\n\n"
            f"🎓 *Name:* {pending['name']}\n"
            f"📚 *Preparation:* {pending['preparation']}\n"
            f"📍 *State:* {pending['state']}\n\n"
            f"🌟 Aapka *Antimprahar Study Group* mein welcome hai! Aapki seat confirm kar li gayi hai.\n\n"
            f"🚀 Niche button par click karke group mein add ho jayein (Link valid for 5 minutes)."
        )
        user_markup = InlineKeyboardMarkup()
        user_markup.add(InlineKeyboardButton("🚀 Join Study Group Now", url=invite_link))
        
        try:
            bot.send_message(user_chat_id, success_text, reply_markup=user_markup, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to send approval to user {target_user_id}: {e}")
        
        # Update admin message to show APPROVED with Quick Reset & Clear buttons
        try:
            updated_admin_text = call.message.text.replace("⬇️ Accept ya Reject karein:", "") + f"\n✅ *APPROVED* ✅"
            action_markup = InlineKeyboardMarkup()
            action_markup.add(
                InlineKeyboardButton("🔄 Reset User", callback_data=f"ask_reset_{target_user_id}"),
                InlineKeyboardButton("🗑️ Clear Card", callback_data="dismiss_msg")
            )
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=updated_admin_text, reply_markup=action_markup, parse_mode="Markdown")
        except Exception:
            pass
        
        pending_approvals.pop(target_user_id, None)
        return
    
    if data.startswith("reject_") and user_id == str(ADMIN_ID):
        target_user_id = data.replace("reject_", "")
        pending = pending_approvals.get(target_user_id)
        
        if not pending and admissions_col is not None:
            try:
                rec = admissions_col.find_one({"userId": target_user_id})
                if rec:
                    pending = {
                        "chatId": str(rec.get("userId")),
                        "name": rec.get("name", "Student")
                    }
            except Exception:
                pass

        if not pending:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=call.message.text + "\n\n⚠️ *Already processed or expired.*", parse_mode="Markdown")
            except Exception:
                pass
            return
        
        # Update MongoDB status to rejected
        if admissions_col is not None:
            def _reject_worker():
                try:
                    admissions_col.update_one(
                        {"userId": target_user_id},
                        {"$set": {"status": "rejected"}}
                    )
                except Exception as e:
                    logging.error(f"Failed to update rejection status: {e}")
            threading.Thread(target=_reject_worker, daemon=True).start()
        
        # Send REJECTION message to user
        user_chat_id = pending["chatId"]
        reject_text = (
            f"❌ *Admission Status Update*\n\n"
            f"Aapke admission application ka review kiya gaya hai. Filhal aapki request approve nahi ho saki hai.\n\n"
            f"Agar aapko is baare mein koi jankari chahiye ya aap dobara apply karna chahte hain, toh kripya support / admin se sampark karein.\n\n"
            f"👤 *Our H.O.D :* @niistharajput\n\n"
            f"Dhanyawad."
        )
        try:
            bot.send_message(user_chat_id, reject_text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to send rejection to user {target_user_id}: {e}")
        
        # Update admin message to show REJECTED with Quick Reset & Clear buttons
        try:
            updated_admin_text = call.message.text.replace("⬇️ Accept ya Reject karein:", "") + f"\n❌ *REJECTED* ❌"
            action_markup = InlineKeyboardMarkup()
            action_markup.add(
                InlineKeyboardButton("🔄 Reset User", callback_data=f"ask_reset_{target_user_id}"),
                InlineKeyboardButton("🗑️ Clear Card", callback_data="dismiss_msg")
            )
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=updated_admin_text, reply_markup=action_markup, parse_mode="Markdown")
        except Exception:
            pass
        
        pending_approvals.pop(target_user_id, None)
        return

    # --- DELETE BROADCAST HANDLING ---
    if data.startswith("delbcast_") and user_id == str(ADMIN_ID):
        bcast_id = data.replace("delbcast_", "")
        records = broadcast_store.get(bcast_id, [])
        
        if not records:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=call.message.text + "\n\n⚠️ *Yeh broadcast pehle hi delete ho chuka hai ya record nahi mila.*", parse_mode="Markdown")
            except Exception:
                pass
            return
        
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"⏳ *Deleting broadcast from {len(records)} users' chats...*", parse_mode="Markdown")
        except Exception:
            pass
        
        def run_delete_task():
            deleted_count = 0
            for target_id, msg_id in records:
                safe_delete_message(target_id, msg_id)
                deleted_count += 1
                time.sleep(0.05)
            
            broadcast_store.pop(bcast_id, None)
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"🧹 *Broadcast Deleted!*\n\n✅ `{deleted_count}` members ke inbox se broadcast message delete kar diya gaya hai.", parse_mode="Markdown")
            except Exception:
                bot.send_message(chat_id, f"🧹 *Broadcast Deleted!*\n\n✅ `{deleted_count}` members ke inbox se broadcast message delete kar diya gaya hai.", parse_mode="Markdown")
                
        threading.Thread(target=run_delete_task, daemon=True).start()
        return

    # --- STUDENT ADMISSION HANDLERS ---
    if is_user_admitted(user_id):
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="⚠️ Aap pehle se admission le chuke ho!\n\nDobara admission nahi le sakte. Agar koi issue hai toh admin se contact karein.")
        except Exception:
            pass
        return

    if data == "start_admission":
        prompt_text = "📋 *Study Group Admission*\n\nWelcome! Admission process shuru karte hain.\n\n✏️ Apna *Full Name* likhkar bhejein:"
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=prompt_text, parse_mode="Markdown")
            msg_id = call.message.message_id
        except Exception:
            m = bot.send_message(chat_id, prompt_text, parse_mode="Markdown")
            msg_id = m.message_id
            
        conversations[user_id] = {"step": "awaiting_name", "chatId": chat_id, "msgId": msg_id}
        return

    convo = conversations.get(user_id)
    if not convo:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🤔 Pehle /admission command bhejein ya niche button click karke admission process shuru karein.", reply_markup=get_fallback_keyboard())
        except Exception:
            pass
        return

    if convo.get("step") == "awaiting_preparation":
        if data.startswith("prep_"):
            prep_choice = data.replace("prep_", "")
            if prep_choice == "OTHER":
                convo["step"] = "awaiting_preparation_custom"
                prompt_text = "✍️ Apne exam ka naam type karke bhejein:\n\n(Example: Banking, Board Exams, Defence, etc.)"
                try:
                    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=prompt_text)
                except Exception:
                    pass
            else:
                convo["preparation"] = prep_choice
                convo["step"] = "awaiting_state"
                prompt_text = "📍 Aap kaunse *State* se ho?\n\n(Niche diye gaye buttons me se select karein 👇)"
                try:
                    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=prompt_text, reply_markup=get_state_keyboard(), parse_mode="Markdown")
                except Exception:
                    pass
        return

    if convo.get("step") == "awaiting_state":
        if data.startswith("state_"):
            state_choice = data.replace("state_", "")
            if state_choice == "OTHER":
                convo["step"] = "awaiting_state_custom"
                prompt_text = "🌐 Apne *State* ka naam type karke bhejein:"
                try:
                    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=prompt_text)
                except Exception:
                    pass
            else:
                name = convo.get("name", "N/A")
                prep = convo.get("preparation", "N/A")
                complete_admission_in_place(chat_id, user_id, username, first_name, name, prep, state_choice, target_msg_id=call.message.message_id)
        return

# --- TEXT MESSAGE HANDLER ---

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

    # --- ADMIN INTERACTIVE QUERY HANDLING (SEARCH) ---
    if user_id == str(ADMIN_ID) and admin_state.get(user_id, {}).get("action") == "awaiting_search":
        prompt_msg_id = admin_state[user_id].get("prompt_msg_id")
        admin_state.pop(user_id, None)
        safe_delete_message(chat_id, message.message_id)
        execute_student_search(chat_id, text, edit_msg_id=prompt_msg_id)
        return

    if is_user_admitted(user_id):
        bot.send_message(chat_id, "⚠️ Aap pehle se admission le chuke ho!\n\nDobara admission nahi le sakte. Agar koi issue hai toh admin se contact karein.")
        return

    convo = conversations.get(user_id)
    if not convo:
        bot.send_message(chat_id, "🤔 Pehle /admission command bhejein ya niche button click karke admission process shuru karein.", reply_markup=get_fallback_keyboard())
        return

    target_msg_id = convo.get("msgId")

    if convo.get("step") == "awaiting_name":
        convo["name"] = text
        convo["step"] = "awaiting_preparation"
        
        safe_delete_message(chat_id, message.message_id)
        
        prompt_text = "📚 Aap kis exam ki *preparation* kar rahe ho?\n\n(Niche diye gaye buttons me se select karein 👇)"
        if target_msg_id:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=target_msg_id, text=prompt_text, reply_markup=get_prep_keyboard(), parse_mode="Markdown")
            except Exception:
                m = bot.send_message(chat_id, prompt_text, reply_markup=get_prep_keyboard(), parse_mode="Markdown")
                convo["msgId"] = m.message_id
        else:
            m = bot.send_message(chat_id, prompt_text, reply_markup=get_prep_keyboard(), parse_mode="Markdown")
            convo["msgId"] = m.message_id
        return

    if convo.get("step") == "awaiting_preparation_custom":
        convo["preparation"] = text
        convo["step"] = "awaiting_state"
        
        safe_delete_message(chat_id, message.message_id)
        
        prompt_text = "📍 Aap kaunse *State* se ho?\n\n(Niche diye gaye buttons me se select karein 👇)"
        if target_msg_id:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=target_msg_id, text=prompt_text, reply_markup=get_state_keyboard(), parse_mode="Markdown")
            except Exception:
                m = bot.send_message(chat_id, prompt_text, reply_markup=get_state_keyboard(), parse_mode="Markdown")
                convo["msgId"] = m.message_id
        else:
            m = bot.send_message(chat_id, prompt_text, reply_markup=get_state_keyboard(), parse_mode="Markdown")
            convo["msgId"] = m.message_id
        return

    if convo.get("step") == "awaiting_state_custom":
        safe_delete_message(chat_id, message.message_id)
        
        name = convo.get("name", "N/A")
        prep = convo.get("preparation", "N/A")
        complete_admission_in_place(chat_id, user_id, username, first_name, name, prep, text, target_msg_id=target_msg_id)
        return

    if convo.get("step") == "awaiting_preparation":
        safe_delete_message(chat_id, message.message_id)
        prompt_text = "📚 Kripya niche diye gaye buttons me se select karein 👇"
        if target_msg_id:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=target_msg_id, text=prompt_text, reply_markup=get_prep_keyboard())
            except Exception:
                pass
        return

    if convo.get("step") == "awaiting_state":
        safe_delete_message(chat_id, message.message_id)
        prompt_text = "📍 Kripya niche diye gaye buttons me se select karein 👇"
        if target_msg_id:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=target_msg_id, text=prompt_text, reply_markup=get_state_keyboard())
            except Exception:
                pass
        return

# --- MAIN RUNNER ---

if __name__ == "__main__":
    logging.info("Antimprahar Bot starting with Search, Professional UI & Auto-Imported Members...")
    
    # Start Flask Webserver for Keep-Alive in background thread
    threading.Thread(target=run_flask, daemon=True).start()

    try:
        bot.remove_webhook()
        time.sleep(2)
        logging.info("Existing webhook removed successfully.")
    except Exception as e:
        logging.warning(f"Could not remove webhook: {e}")
        
    try:
        updates = bot.get_updates(offset=-1, timeout=1)
        if updates:
            bot.get_updates(offset=updates[-1].update_id + 1, timeout=1)
        logging.info("Pending updates cleared.")
    except Exception as e:
        logging.warning(f"Could not clear pending updates: {e}")
        
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            logging.error(f"Polling error encountered: {e}. Retrying in 5 seconds...")
            time.sleep(5)
