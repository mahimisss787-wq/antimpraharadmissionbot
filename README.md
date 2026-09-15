# Telegram Admission Bot - Railway Setup Guide

Maine aapke n8n workflow ko poori tarah **Python** code me convert kar diya hai. Ab aap isko **Railway.app** par free 24/7 host kar sakte hain.

---

## 📁 Files Included
1. `main.py` - Main Telegram Bot Script.
2. `requirements.txt` - Required Python packages.
3. `Procfile` - Railway worker command.

---

## 🚀 Step-by-Step Railway Deployment Guide

### Step 1: GitHub Repository Banaein
1. Sabhi 3 files (`main.py`, `requirements.txt`, `Procfile`) ko ek naye folder me rakhein.
2. Apne GitHub account par ek Nayi **Public / Private Repository** banaein (Jaise: `telegram-admission-bot`).
3. Ye files apne GitHub repo me upload/push kar dein.

---

### Step 2: Railway.app Par Deploy Karein
1. [Railway.app](https://railway.app/) par jayein aur GitHub se login karein.
2. **"New Project"** -> **"Deploy from GitHub repo"** par click karein.
3. Apni repo `telegram-admission-bot` select karein.
4. Railway automatically detect kar lega ki yeh Python project hai.

---

### Step 3: Environment Variables Set Karein
Deploy hone ke baad Railway me **Variables** tab me jayein aur yeh keys add karein:

| Variable Key | Default Value / Info |
|---|---|
| `BOT_TOKEN` | `8944237255:AAE3SqXZyukH-HpazVhkMJryIFD2BJK6zTM` |
| `ADMIN_ID` | `6416451659` |
| `GROUP_CHAT_ID` | `-1003493006883` |
| `SPREADSHEET_ID` | `1zvgEFhy29CRqliTra1kPdviEVP503hjLAxmy8axhys0` |
| `GOOGLE_CREDENTIALS_JSON` | *(Optional)* Google Service Account Credentials JSON string |

---

### Step 4: Bot Activate Karein
- Railway Variables add hone ke baad automatic rebuild and deploy kar dega.
- Aapka bot Telegram par **24/7 bina rukawat** chalega! 🎉
