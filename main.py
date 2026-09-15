import os
import time
import json
import logging
from datetime import datetime
import pytz
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Environment Variables / Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "8944237255:AAE3SqXZyukH-HpazVhkMJryIFD2BJK6zTM")
ADMIN_ID = os.getenv("ADMIN_ID", "6416451659")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "-1003493006883")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1zvgEFhy29CRqliTra1kPdviEVP503hjLAxmy8axhys0")

# Optional Google Sheets setup
gspread_client = None
sheet = None
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

if GOOGLE_CREDS_JSON:
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds_dict = json.loads(GOOGLE_CREDS_JSON)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gspread_client = gspread.authorize(creds)
        sheet = gspread_client.open_by_key(SPREADSHEET_ID).sheet1
        logging.info("Google Sheets connected successfully!")
    except Exception as e:
        logging.error(f"Google Sheets connection failed: {e}")
elif os.path.exists("credentials.json"):
    try:
        import gspread
        gspread_client = gspread.service_account(filename="credentials.json")
        sheet = gspread_client.open_by_key(SPREADSHEET_ID).sheet1
        logging.info("Google Sheets connected using credentials.json!")
    except Exception as e:
        logging.error(f"Google Sheets connection failed: {e}")
else:
    logging.warning("Google Sheets credentials not provided. Data will be saved in memory only.")

# Initialize Telegram Bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# Global State Memory
conversations = {}
admitted = {}

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


# --- HELPER FUNCTIONS ---

def save_to_google_sheets(row_data):
    """Save user admission record to Google Sheets if configured"""
    if sheet:
        try:
            sheet.append_row([
                row_data["userId"],
                row_data["name"],
                row_data["username"],
                row_data["preparation"],
                row_data["state"],
                row_data["dateTime"]
            ])
            logging.info(f"Saved to Google Sheets for User {row_data['userId']}")
        except Exception as e:
            logging.error(f"Failed to append to Google Sheets: {e}")

def complete_admission(chat_id, user_id, username, first_name, name, preparation, state):
    """Complete the admission process, save data, create invite link, and notify user/admin."""
    tz = pytz.timezone("Asia/Kolkata")
    formatted_date = datetime.now(tz).strftime("%d/%m/%Y, %I:%M:%S %p")
    
    # Store in admitted memory
    admitted[str(user_id)] = {
        "name": name,
        "preparation": preparation,
        "state": state,
        "username": username,
        "firstName": first_name,
        "userId": str(user_id),
        "date": formatted_date
    }
    
    # Remove from active conversations
    if str(user_id) in conversations:
        del conversations[str(user_id)]
        
    # Save to Google Sheets
    save_to_google_sheets({
        "userId": str(user_id),
        "name": name,
        "username": username,
        "preparation": preparation,
        "state": state,
        "dateTime": formatted_date
    })
    
    # Generate 1-time 30-second Group Invite Link
    invite_link = "#"
    try:
        expire_time = int(time.time()) + 30
        res = bot.create_chat_invite_link(chat_id=GROUP_CHAT_ID, member_limit=1, expire_date=expire_time)
        invite_link = res.invite_link
    except Exception as e:
        logging.error(f"Failed to create chat invite link: {e}")
        invite_link = "https://t.me"

    # Send Success message to User with Invite Link
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
    
    # Send Notification to Admin
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


# --- COMMAND HANDLERS ---

@bot.message_handler(commands=['resetall'])
def handle_reset_all(message):
    user_id = str(message.from_user.id)
    if user_id != str(ADMIN_ID):
        return
    admitted.clear()
    conversations.clear()
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
        
    was_admitted = target_id in admitted
    had_convo = target_id in conversations
    
    if was_admitted or had_convo:
        admitted.pop(target_id, None)
        conversations.pop(target_id, None)
        bot.reply_to(message, f"✅ *Reset Successful!*\n\nUser ID: `{target_id}` ka admission record remove kar diya gaya hai.")
    else:
        bot.reply_to(message, f"⚠️ *User Not Found!*\n\nUser ID: `{target_id}` ka koi admission record nahi mila.")

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = str(message.from_user.id)
    conversations.pop(user_id, None)
    
    welcome_text = (
        "👋 Welcome to *Study Group Admission Bot*!\n\n"
        "Admission process shuru karne ke liye niche button par click karein 👇"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_welcome_keyboard())

@bot.message_handler(commands=['admission'])
def handle_admission_command(message):
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    if user_id in admitted:
        bot.send_message(chat_id, "⚠️ Aap pehle se admission le chuke ho!\n\nDobara admission nahi le sakte. Agar koi issue hai toh admin se contact karein.")
        return
        
    conversations[user_id] = {"step": "awaiting_name", "chatId": chat_id}
    bot.send_message(chat_id, "📋 *Study Group Admission*\n\nWelcome! Admission process shuru karte hain.\n\n✏️ Apna *Full Name* likhkar bhejein:")


# --- CALLBACK QUERY HANDLER (BUTTON CLICKS) ---

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    chat_id = str(call.message.chat.id)
    user_id = str(call.from_user.id)
    username = f"@{call.from_user.username}" if call.from_user.username else "N/A"
    first_name = call.from_user.first_name or "N/A"
    data = call.data
    
    # Always answer callback query to remove button spinner
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
        
    # Remove Inline Buttons after click
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=None)
    except Exception:
        pass
        
    # Check if already admitted
    if user_id in admitted:
        bot.send_message(chat_id, "⚠️ Aap pehle se admission le chuke ho!\n\nDobara admission nahi le sakte. Agar koi issue hai toh admin se contact karein.")
        return

    # Start Admission button click
    if data == "start_admission":
        conversations[user_id] = {"step": "awaiting_name", "chatId": chat_id}
        bot.send_message(chat_id, "📋 *Study Group Admission*\n\nWelcome! Admission process shuru karte hain.\n\n✏️ Apna *Full Name* likhkar bhejein:")
        return

    convo = conversations.get(user_id)
    if not convo:
        bot.send_message(chat_id, "🤔 Pehle /admission command bhejein ya niche button click karke admission process shuru karein.", reply_markup=get_fallback_keyboard())
        return

    # Step 2: Preparation Button Click
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

    # Step 3: State Button Click
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
    
    # Check if already admitted
    if user_id in admitted:
        bot.send_message(chat_id, "⚠️ Aap pehle se admission le chuke ho!\n\nDobara admission nahi le sakte. Agar koi issue hai toh admin se contact karein.")
        return

    convo = conversations.get(user_id)
    if not convo:
        bot.send_message(chat_id, "🤔 Pehle /admission command bhejein ya niche button click karke admission process shuru karein.", reply_markup=get_fallback_keyboard())
        return

    # Step 1: Name Input
    if convo.get("step") == "awaiting_name":
        convo["name"] = text
        convo["step"] = "awaiting_preparation"
        bot.send_message(chat_id, "📚 Aap kis exam ki *preparation* kar rahe ho?\n\n(Niche diye gaye buttons me se select karein 👇)", reply_markup=get_prep_keyboard())
        return

    # Step 2 Custom: Exam Name Input
    if convo.get("step") == "awaiting_preparation_custom":
        convo["preparation"] = text
        convo["step"] = "awaiting_state"
        bot.send_message(chat_id, "📍 Aap kaunse *State* se ho?\n\n(Niche diye gaye buttons me se select karein 👇)", reply_markup=get_state_keyboard())
        return

    # Step 3 Custom: State Name Input
    if convo.get("step") == "awaiting_state_custom":
        name = convo.get("name", "N/A")
        prep = convo.get("preparation", "N/A")
        complete_admission(chat_id, user_id, username, first_name, name, prep, text)
        return

    # Fallback if text received during button step
    if convo.get("step") == "awaiting_preparation":
        bot.send_message(chat_id, "📚 Kripya niche diye gaye buttons me se select karein 👇", reply_markup=get_prep_keyboard())
        return

    if convo.get("step") == "awaiting_state":
        bot.send_message(chat_id, "📍 Kripya niche diye gaye buttons me se select karein 👇", reply_markup=get_state_keyboard())
        return


# --- MAIN EXECUTION LOOP ---

if __name__ == "__main__":
    logging.info("Bot starting...")
    bot.infinity_polling(skip_pending=True)
