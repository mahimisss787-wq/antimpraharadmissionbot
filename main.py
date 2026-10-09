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

@bot.message_handler(commands=['reset'])
def handle_reset_user(message):
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        return
    
    parts = message.text.split(maxsplit=1)
    target_id = parts[1].strip() if len(parts) > 1 else ""
    
    # Check if replying to an approval card or user message
    if not target_id and message.reply_to_message:
        reply_text = message.reply_to_message.text or ""
        # Extract User ID from card if present
        import re
        match = re.search(r"User ID:\s*`?(\d+)`?", reply_text)
        if match:
            target_id = match.group(1)
        elif message.reply_to_message.forward_from:
            target_id = str(message.reply_to_message.forward_from.id)
            
    if not target_id:
        bot.reply_to(message, "⚠️ *Usage:* `/reset <User_ID>` ya kisi user card/message par **Reply** karke `/reset` likhein.")
        return
        
    admitted.pop(target_id, None)
    conversations.pop(target_id, None)
    pending_approvals.pop(target_id, None)
    
    if admissions_col is not None:
        try:
            admissions_col.delete_one({"userId": target_id})
        except Exception as e:
            logging.error(f"Failed to delete user from MongoDB: {e}")
            
    bot.reply_to(message, f"✅ *Reset Successful!*\n\nUser ID: `{target_id}` ka saara admission record delete kar diya gaya hai. Ab yeh user dobara fresh admission le sakta hai.")

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

    # --- ADMIN APPROVAL / REJECTION HANDLING ---
    if data.startswith("approve_") and user_id == str(ADMIN_ID):
        target_user_id = data.replace("approve_", "")
        pending = pending_approvals.get(target_user_id)
        
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
            expire_time = int(time.time()) + 120  # 2 minute valid link
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
            f"🚀 Niche button par click karke group mein add ho jayein (Link valid for 2 minutes)."
        )
        user_markup = InlineKeyboardMarkup()
        user_markup.add(InlineKeyboardButton("🚀 Join Study Group Now", url=invite_link))
        
        try:
            bot.send_message(user_chat_id, success_text, reply_markup=user_markup, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to send approval to user {target_user_id}: {e}")
        
        # Update admin message to show APPROVED
        try:
            updated_admin_text = call.message.text + f"\n\n✅ *APPROVED* ✅"
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=updated_admin_text, parse_mode="Markdown")
        except Exception:
            pass
        
        # Remove from pending
        pending_approvals.pop(target_user_id, None)
        return
    
    if data.startswith("reject_") and user_id == str(ADMIN_ID):
        target_user_id = data.replace("reject_", "")
        pending = pending_approvals.get(target_user_id)
        
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
        
        # Update admin message to show REJECTED
        try:
            updated_admin_text = call.message.text + f"\n\n❌ *REJECTED* ❌"
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=updated_admin_text, parse_mode="Markdown")
        except Exception:
            pass
        
        # Remove from pending
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

if __name__ == "__main__":
    logging.info("Bot starting with Auto-Imported 21 Previous Members...")
    
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

