#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Digital Marketplace Telegram Bot (Legal products only)
- Buy / Sell digital products (bots, source code, websites, templates, courses, files)
- Wallet: deposit (manual + gateway placeholder) / withdraw
- Seller listings with photos, price, duration
- In-bot buyer↔seller contact
- Admin: users, orders, broadcast, payment methods, min deposit/withdraw, gateway keys
- Support + FAQ
Main Admin: 8289191009
"""

import logging
import json
import urllib.request
import urllib.error
import sqlite3
import string
import random
from datetime import datetime
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

# ================== CONFIG ==================
BOT_TOKEN = "8957497265:AAGWKalRRqWjXfORxcjwTdEo9aEYJ7c5M20"  # <-- BotFather token
MAIN_ADMIN_ID = 8289191009
DB_PATH = "marketplace.db"
BOT_VERSION = "1.0.0"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
(
    DEP_METHOD,
    DEP_AMOUNT,
    DEP_PROOF,
    WD_AMOUNT,
    WD_METHOD,
    WD_DETAILS,
    SELL_CAT,
    SELL_TITLE,
    SELL_DESC,
    SELL_PRICE,
    SELL_DURATION,
    SELL_STOCK,
    SELL_PHOTO,
    SELL_DELIVERY,
    CHAT_MSG,
    BROADCAST_MSG,
    SET_VALUE,
    ADD_PAY_NAME,
    ADD_PAY_INFO,
    EDIT_STOCK,
    EDIT_PRICE,
    EDIT_TITLE,
    EDIT_DELIVERY,
    BAL_USER,
    BAL_AMT,
    BLOCK_USER,
    DEP_GW_AMOUNT,
) = range(27)


# ================== DB ==================
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            is_seller INTEGER DEFAULT 0,
            referrer_id INTEGER,
            joined_at TEXT,
            last_active TEXT
        );
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'admin',
            added_at TEXT
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            emoji TEXT DEFAULT '📦',
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER,
            category_id INTEGER,
            title TEXT,
            description TEXT,
            price REAL,
            duration TEXT,
            photo_file_id TEXT,
            delivery_info TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER,
            seller_id INTEGER,
            product_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'paid',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            method TEXT,
            proof_file_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS withdraws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            method TEXT,
            details TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            info TEXT,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS force_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            title TEXT,
            link TEXT,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            kind TEXT,
            amount REAL,
            note TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            sender_id INTEGER,
            message TEXT,
            created_at TEXT
        );
        """
    )

    defaults = {
        "min_deposit": "50",
        "default_lang": "bn",

        "min_deposit_binance": "140",
        "min_deposit_mobile": "50",

        "min_withdraw": "100",
        "bot_enabled": "1",
        "withdraw_enabled": "1",
        "referral_bonus": "10",
        "support_username": "",
        "faq_text": (
            "ℹ️ <b>FAQ — কীভাবে ব্যবহার করবেন</b>\n\n"
            "💰 <b>Wallet</b> — ব্যালেন্স দেখুন\n"
            "🛒 <b>Market</b> — ক্যাটাগরি বেছে প্রোডাক্ট কিনুন (ব্যালেন্স লাগবে)\n"
            "📤 <b>Sell</b> — প্রোডাক্ট লিস্ট করুন + স্টক সংখ্যা দিন\n"
            "📦 <b>My Products</b> — এডিট/স্টক বাড়ান/অফ করুন\n"
            "🧾 <b>Orders</b> — কেনা ও বেচার অর্ডার\n"
            "📜 <b>History</b> — কেনাকাটা ও সেল আলাদা\n"
            "💳 <b>Deposit</b> — মেথড বেছে টাকা পাঠিয়ে TrxID+স্ক্রিনশট দিন\n"
            "💸 <b>Withdraw</b> — উইথড্র রিকোয়েস্ট\n"
            "👥 <b>Referral</b> — লিংক শেয়ার; রেফার্ড কিনলে কমিশন\n"
            "🔄 <b>Update</b> — বট আপডেট চেক\n"
            "👨‍💻 <b>Developer</b> — ডেভেলপারের সাথে যোগাযোগ\n"
            "🆘 Support / ℹ️ FAQ — সাহায্য\n\n"
            "শুধু বৈধ ডিজিটাল প্রোডাক্ট।"
        ),
        "welcome_text": "🛒 <b>Digital Marketplace</b>\nবৈধ ডিজিটাল প্রোডাক্ট কিনুন ও বিক্রি করুন।",
        "admin_commission_percent": "10",
        "update_text": "✅ Bot already up to date.\nকোনো নতুন আপডেট নেই।",
        "developer_prefill": "আমি ওয়েবসাইট বা বট বানাতে চাই",
        "developer_username": "",
        "referral_shop_percent": "5",
        "gateway_nagorik_api": "",
        "gateway_nagorik_secret": "",
        "gateway_rupantor_api": "",
        "gateway_rupantor_secret": "",
        "gateway_enabled": "0",
        "gateway_name": "Auto Gateway",
        "gateway_api_key": "",
        "gateway_secret": "",
        "gateway_create_url": "https://client-pg.daweblab.com/api/payment/create",
        "gateway_verify_url": "https://client-pg.daweblab.com/api/payment/verify",
        "gateway_header_name": "api-key",
        "gateway_min": "10",
        "gateway_daweblab_api": "",
        "gateway_daweblab_secret": "",
        "maintenance": "0",
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    cur.execute(
        "INSERT OR IGNORE INTO admins (user_id, role, added_at) VALUES (?, 'main', ?)",
        (MAIN_ADMIN_ID, datetime.now().isoformat()),
    )

    # default categories (legal digital only)
    cur.execute("SELECT COUNT(*) c FROM categories")
    if cur.fetchone()["c"] == 0:
        for name, emoji in [
            ("Bot", "🤖"),
            ("Source Code", "💻"),
            ("Website", "🌐"),
            ("Template", "📄"),
            ("Course", "📚"),
            ("Digital File", "📁"),
            ("Other", "📦"),
        ]:
            cur.execute(
                "INSERT INTO categories (name, emoji) VALUES (?, ?)", (name, emoji)
            )

    # payment methods: admin sets up manually (no default seed)


    # migrations
    try:
        cur.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 1")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE payment_methods ADD COLUMN min_amount REAL DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'bn'")
    except Exception:
        pass

    conn.commit()
    conn.close()


def get_setting(key, default=""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value))
    )
    conn.commit()
    conn.close()



def _http_json(method: str, url: str, headers: dict, payload: Optional[dict] = None, timeout: int = 30):
    data = None
    hdrs = dict(headers or {})
    hdrs.setdefault("Content-Type", "application/json")
    hdrs.setdefault("Accept", "application/json")
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body) if body else {}
            except Exception:
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body) if body else {"error": str(e)}
        except Exception:
            return e.code, {"error": str(e), "raw": body}
    except Exception as e:
        return 0, {"error": str(e)}


def gateway_headers():
    key = get_setting("gateway_api_key") or get_setting("gateway_daweblab_api") or ""
    secret = get_setting("gateway_secret") or get_setting("gateway_daweblab_secret") or ""
    hname = (get_setting("gateway_header_name") or "api-key").strip()
    h = {}
    if key:
        if hname.lower() in ("authorization", "bearer"):
            h["Authorization"] = f"Bearer {key}"
        else:
            h[hname] = key
    if secret:
        h["secret-key"] = secret
        h["X-Secret-Key"] = secret
    return h


def gateway_extract_url(obj):
    if not isinstance(obj, dict):
        return None
    for k in ("payment_url", "checkout_url", "url", "redirect_url", "link", "pay_url"):
        if obj.get(k):
            return str(obj[k])
    data = obj.get("data")
    if isinstance(data, dict):
        for k in ("payment_url", "checkout_url", "url", "redirect_url", "link", "pay_url"):
            if data.get(k):
                return str(data[k])
    return None


def gateway_extract_trx(obj):
    if not isinstance(obj, dict):
        return None
    for k in ("transaction_id", "trx_id", "trxId", "payment_id", "invoice_id", "id", "order_id"):
        if obj.get(k):
            return str(obj[k])
    data = obj.get("data")
    if isinstance(data, dict):
        for k in ("transaction_id", "trx_id", "trxId", "payment_id", "invoice_id", "id", "order_id"):
            if data.get(k):
                return str(data[k])
    return None


def gateway_is_paid(obj):
    if not isinstance(obj, dict):
        return False
    status = str(obj.get("status") or obj.get("payment_status") or "").lower()
    if status in ("paid", "success", "completed", "successful", "complete", "ok"):
        return True
    data = obj.get("data")
    if isinstance(data, dict):
        status = str(data.get("status") or data.get("payment_status") or "").lower()
        if status in ("paid", "success", "completed", "successful", "complete", "ok"):
            return True
    if obj.get("success") is True or obj.get("paid") is True:
        return True
    return False


def get_user_lang(uid: int) -> str:
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT lang FROM users WHERE user_id=?", (uid,))
        r = cur.fetchone()
        conn.close()
        if r and r["lang"]:
            return r["lang"]
    except Exception:
        pass
    return get_setting("default_lang", "bn") or "bn"


def resolve_method_min(method_name: str, method_row_min=None) -> float:
    """Binance/USDT use binance min; bKash/Nagad/Rocket/Upay use mobile min; else row or global."""
    name = (method_name or "").lower()
    try:
        row_min = float(method_row_min or 0)
    except Exception:
        row_min = 0.0
    if row_min > 0:
        return row_min
    if any(x in name for x in ("binance", "usdt", "bep20", "crypto")):
        try:
            return float(get_setting("min_deposit_binance", "140") or 140)
        except Exception:
            return 140.0
    if any(x in name for x in ("bkash", "bkas", "nagad", "rocket", "upay", "nagd")):
        try:
            return float(get_setting("min_deposit_mobile", "50") or 50)
        except Exception:
            return 50.0
    try:
        return float(get_setting("min_deposit", "50") or 50)
    except Exception:
        return 50.0




def is_admin(uid: int) -> bool:
    if uid == MAIN_ADMIN_ID:
        return True
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    ok = cur.fetchone() is not None
    conn.close()
    return ok


def is_main(uid: int) -> bool:
    return uid == MAIN_ADMIN_ID


def ensure_user(uid, username=None, full_name=None, referrer_id=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    if not cur.fetchone():
        if referrer_id and int(referrer_id) == int(uid):
            referrer_id = None
        cur.execute(
            """INSERT INTO users (user_id, username, full_name, referrer_id, joined_at, last_active)
               VALUES (?,?,?,?,?,?)""",
            (
                uid,
                username,
                full_name,
                referrer_id,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            ),
        )
        if referrer_id:
            try:
                bonus = float(get_setting("referral_bonus", "10") or 0)
            except Exception:
                bonus = 10
            if bonus > 0:
                cur.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id=?",
                    (bonus, referrer_id),
                )
                try:
                    cur.execute(
                        "INSERT INTO history (user_id, kind, amount, note, created_at) VALUES (?,?,?,?,?)",
                        (referrer_id, "referral", bonus, "ref %s" % uid, datetime.now().isoformat()),
                    )
                except Exception:
                    pass
    else:
        cur.execute(
            "UPDATE users SET username=?, full_name=?, last_active=? WHERE user_id=?",
            (username, full_name, datetime.now().isoformat(), uid),
        )
    conn.commit()
    conn.close()


def get_user(uid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    return row


def add_balance(uid: int, amount: float, note: str = ""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    conn.commit()
    conn.close()


MENU = {
    "bn": {
        "wallet": "💰 Wallet",
        "profile": "👤 Profile",
        "market": "🛒 Market",
        "sell": "📤 Sell",
        "my_products": "📦 My Products",
        "orders": "🧾 Orders",
        "history": "📜 History",
        "referral": "👥 Referral",
        "deposit": "💳 Deposit",
        "withdraw": "💸 Withdraw",
        "support": "🆘 Support",
        "faq": "ℹ️ FAQ",
        "update": "🔄 Update",
        "developer": "👨‍💻 Developer",
        "lang": "🌐 Language",
        "admin": "🔧 Admin Panel",
    },
    "en": {
        "wallet": "💰 Wallet",
        "profile": "👤 Profile",
        "market": "🛒 Market",
        "sell": "📤 Sell",
        "my_products": "📦 My Products",
        "orders": "🧾 Orders",
        "history": "📜 History",
        "referral": "👥 Referral",
        "deposit": "💳 Deposit",
        "withdraw": "💸 Withdraw",
        "support": "🆘 Support",
        "faq": "ℹ️ FAQ",
        "update": "🔄 Update",
        "developer": "👨‍💻 Developer",
        "lang": "🌐 Language",
        "admin": "🔧 Admin Panel",
    },
}


def user_kb(show_admin=False, lang="bn"):
    m = MENU.get(lang) or MENU["bn"]
    rows = [
        [m["wallet"], m["profile"]],
        [m["market"], m["sell"]],
        [m["my_products"], m["orders"]],
        [m["history"], m["referral"]],
        [m["deposit"], m["withdraw"]],
        [m["support"], m["faq"]],
        [m["update"], m["developer"]],
        [m["lang"]],
    ]
    if show_admin:
        rows.append([m["admin"]])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def admin_kb(main=False):
    rows = [
        ["👥 Users", "📄 Export Users"],
        ["📊 Stats", "🛍️ All Products"],
        ["➕ Admin Add Product", "📂 Categories"],
        ["📥 Deposits", "💸 Withdrawals"],
        ["💳 Payment Methods", "🔑 Gateway Keys"],
        ["📢 Force Channels", "🎁 Referral Bonus"],
        ["⚙️ Settings", "📢 Broadcast"],
        ["🤖 Bot ON/OFF", "💸 WD ON/OFF"],
    ]
    if main:
        rows.append(["👑 Add Admin", "🗑️ Remove Admin"])
        rows.append(["🔄 Ownership Transfer"])
    rows.append(["🏠 User Panel"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def get_force_channels():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM force_channels WHERE is_active=1")
    rows = cur.fetchall()
    conn.close()
    return rows


async def check_force_join(bot, user_id):
    missing = []
    for ch in get_force_channels():
        raw = str(ch["chat_id"]).strip()
        cands = []
        if raw.lstrip("-").isdigit():
            cands += [int(raw), raw]
        else:
            cands.append(raw if raw.startswith("@") else "@" + raw)
        ok = False
        for cid in cands:
            try:
                m = await bot.get_chat_member(chat_id=cid, user_id=user_id)
                st = str(getattr(m, "status", m.status))
                if st in ("member", "administrator", "creator", "ChatMemberStatus.MEMBER", "ChatMemberStatus.ADMINISTRATOR", "ChatMemberStatus.OWNER"):
                    ok = True
                    break
                if hasattr(m.status, "name") and m.status.name in ("MEMBER", "ADMINISTRATOR", "OWNER"):
                    ok = True
                    break
            except Exception:
                pass
        if not ok:
            missing.append(ch)
    return missing


# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref = None
    if context.args:
        try:
            ref = int(context.args[0])
        except ValueError:
            ref = None
    ensure_user(user.id, user.username, user.full_name, ref)
    u = get_user(user.id)
    if u and u["is_blocked"]:
        await update.message.reply_text("আপনি ব্লকড।")
        return
    if get_setting("bot_enabled", "1") != "1" and not is_admin(user.id):
        await update.message.reply_text("🤖 বট এখন বন্ধ (Admin)।")
        return
    if get_setting("maintenance") == "1" and not is_admin(user.id):
        await update.message.reply_text("🔧 Maintenance mode।")
        return
    missing = await check_force_join(context.bot, user.id)
    if missing and not is_admin(user.id):
        buttons = []
        for ch in missing:
            title = ch["title"] or ch["chat_id"]
            link = ch["link"] or ""
            if link:
                buttons.append([InlineKeyboardButton("Join " + str(title), url=link)])
            else:
                buttons.append([InlineKeyboardButton(str(title), callback_data="noop")])
        buttons.append([InlineKeyboardButton("✅ আমি জয়েন করেছি", callback_data="check_join")])
        await update.message.reply_text(
            "🔒 আগে চ্যানেল জয়েন করুন:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return
    await update.message.reply_text(
        get_setting("welcome_text"),
        parse_mode=ParseMode.HTML,
        reply_markup=user_kb(is_admin(user.id), get_user_lang(user.id)),
    )


async def check_join_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    missing = await check_force_join(context.bot, q.from_user.id)
    if missing:
        await q.answer("এখনো জয়েন করেননি!", show_alert=True)
        return
    try:
        await q.message.delete()
    except Exception:
        pass
    await context.bot.send_message(
        q.from_user.id,
        get_setting("welcome_text"),
        parse_mode=ParseMode.HTML,
        reply_markup=user_kb(is_admin(q.from_user.id)),
    )


async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    me = await context.bot.get_me()
    link = "https://t.me/%s?start=%s" % (me.username, uid)
    bonus = get_setting("referral_bonus", "10")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM users WHERE referrer_id=?", (uid,))
    cnt = cur.fetchone()["c"]
    conn.close()
    await update.message.reply_text(
        "👥 <b>Referral</b>\n\nলিংক:\n<code>%s</code>\n\nবোনাস: <b>%s</b> BDT\nমোট: %s" % (link, bonus, cnt),
        parse_mode=ParseMode.HTML,
    )


async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    import io
    from telegram import InputFile
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, full_name, balance, referrer_id, joined_at FROM users ORDER BY user_id")
    rows = cur.fetchall()
    conn.close()
    lines = ["user_id\tusername\tfull_name\tbalance\treferrer\tjoined"]
    for r in rows:
        lines.append("%s\t%s\t%s\t%s\t%s\t%s" % (
            r["user_id"], r["username"] or "", r["full_name"] or "",
            r["balance"], r["referrer_id"] or "", r["joined_at"] or ""))
    bio = io.BytesIO("\n".join(lines).encode("utf-8"))
    bio.name = "users.txt"
    await update.message.reply_document(document=InputFile(bio), caption="Users %s" % len(rows))


async def toggle_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cur = get_setting("bot_enabled", "1")
    set_setting("bot_enabled", "0" if cur == "1" else "1")
    await update.message.reply_text("🤖 bot_enabled = " + get_setting("bot_enabled"))


async def toggle_wd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cur = get_setting("withdraw_enabled", "1")
    set_setting("withdraw_enabled", "0" if cur == "1" else "1")
    await update.message.reply_text("💸 withdraw_enabled = " + get_setting("withdraw_enabled"))


async def force_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chs = get_force_channels()
    text = "📢 Force Channels\n\n"
    buttons = []
    for c in chs:
        text += "#%s %s\n" % (c["id"], c["title"] or c["chat_id"])
        buttons.append([InlineKeyboardButton("Remove #%s" % c["id"], callback_data="rmch_%s" % c["id"])])
    buttons.append([InlineKeyboardButton("➕ Add Channel", callback_data="addch")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def rmch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    cid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM force_channels WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    await q.edit_message_text("Removed")


async def addch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await_ch"] = True
    await q.edit_message_text("Channel @username or -100id পাঠান (বট Admin হতে হবে):")


async def ref_bonus_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data["set_key"] = "referral_bonus"
    await update.message.reply_text("বর্তমান: %s\nনতুন বোনাস লিখুন:" % get_setting("referral_bonus"))


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    uid = update.effective_user.id
    await update.message.reply_text(
        "বাতিল।",
        reply_markup=user_kb(is_admin(uid)) if not context.user_data.get("in_admin") else admin_kb(),
    )
    return ConversationHandler.END


# ================== WALLET ==================
async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    if not u:
        ensure_user(uid, update.effective_user.username, update.effective_user.full_name)
        u = get_user(uid)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM users WHERE referrer_id=?", (uid,))
    refs = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM orders WHERE buyer_id=?", (uid,))
    buys = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM orders WHERE seller_id=?", (uid,))
    sales = cur.fetchone()["c"]
    conn.close()
    status = "🚫 Blocked / Inactive" if u["is_blocked"] else "✅ Active"
    await update.message.reply_text(
        f"👤 <b>Profile</b>\n\n"
        f"🆔 User ID: <code>{uid}</code>\n"
        f"👤 Username: @{u['username'] or '-'}\n"
        f"📝 Name: {u['full_name'] or '-'}\n"
        f"💰 Balance: <b>{u['balance']:.2f}</b> BDT\n"
        f"📅 Joined: {u['joined_at'] or '-'}\n"
        f"👥 Referrals: {refs}\n"
        f"🛒 Purchases: {buys} | 📤 Sales: {sales}\n"
        f"📊 Status: {status}",
        parse_mode=ParseMode.HTML,
    )


async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    bal = u["balance"] if u else 0
    await update.message.reply_text(
        f"💰 <b>Wallet</b>\n\nBalance: <b>{bal:.2f}</b> BDT\n"
        f"Min Deposit: {get_setting('min_deposit')}\n"
        f"Min Withdraw: {get_setting('min_withdraw')}",
        parse_mode=ParseMode.HTML,
    )


# ================== MARKET ==================
async def market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM categories WHERE is_active=1 ORDER BY id")
    cats = cur.fetchall()
    conn.close()
    if not cats:
        await update.message.reply_text("ক্যাটাগরি নেই।")
        return
    buttons = [
        [InlineKeyboardButton(f"{c['emoji']} {c['name']}", callback_data=f"cat_{c['id']}")]
        for c in cats
    ]
    await update.message.reply_text(
        "🛒 <b>Market — ক্যাটাগরি বেছে নিন</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cat_id = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT p.*, c.name cname, c.emoji FROM products p "
        "JOIN categories c ON c.id=p.category_id "
        "WHERE p.category_id=? AND p.is_active=1 ORDER BY p.id DESC LIMIT 30",
        (cat_id,),
    )
    products = cur.fetchall()
    conn.close()
    if not products:
        await q.edit_message_text("এই ক্যাটাগরিতে প্রোডাক্ট নেই।")
        return
    buttons = [
        [
            InlineKeyboardButton(
                f"{p['title'][:28]} — {p['price']:.0f}৳",
                callback_data=f"prod_{p['id']}",
            )
        ]
        for p in products
    ]
    buttons.append([InlineKeyboardButton("« Back", callback_data="back_market")])
    await q.edit_message_text(
        "🛍️ প্রোডাক্ট বেছে নিন:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def back_market_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM categories WHERE is_active=1 ORDER BY id")
    cats = cur.fetchall()
    conn.close()
    buttons = [
        [InlineKeyboardButton(f"{c['emoji']} {c['name']}", callback_data=f"cat_{c['id']}")]
        for c in cats
    ]
    await q.edit_message_text(
        "🛒 <b>Market — ক্যাটাগরি</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def prod_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT p.*, c.name cname, u.username suser FROM products p "
        "JOIN categories c ON c.id=p.category_id "
        "LEFT JOIN users u ON u.user_id=p.seller_id "
        "WHERE p.id=?",
        (pid,),
    )
    p = cur.fetchone()
    conn.close()
    if not p or not p["is_active"]:
        await q.edit_message_text("প্রোডাক্ট পাওয়া যায়নি।")
        return
    try:
        stock = int(p["stock"] if p["stock"] is not None else 1)
    except Exception:
        stock = 1
    text = (
        f"📦 <b>{p['title']}</b>\n"
        f"ক্যাটাগরি: {p['cname']}\n"
        f"দাম: <b>{p['price']:.2f} BDT</b>\n"
        f"মেয়াদ: {p['duration']}\n"
        f"স্টক: <b>{stock}</b>\n"
        f"সেলার: @{p['suser'] or p['seller_id']}\n\n"
        f"{p['description'] or ''}"
    )
    buttons = [
        [InlineKeyboardButton("🛒 Buy Now", callback_data=f"buy_{p['id']}")],
        [InlineKeyboardButton("💬 Contact Seller", callback_data=f"csell_{p['id']}")],
        [InlineKeyboardButton("« Back", callback_data=f"cat_{p['category_id']}")],
    ]
    kb = InlineKeyboardMarkup(buttons)
    if p["photo_file_id"]:
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_photo(
            q.from_user.id,
            p["photo_file_id"],
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
    else:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def buy_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    pid = int(q.data.split("_")[1])
    uid = q.from_user.id

    # prevent double-click race
    lock_key = f"buying_{uid}_{pid}"
    if context.user_data.get(lock_key):
        await q.answer("⏳ প্রসেস হচ্ছে, অপেক্ষা করুন...", show_alert=True)
        return
    context.user_data[lock_key] = True

    try:
        await q.answer("⏳ কেনা হচ্ছে...")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM products WHERE id=? AND is_active=1", (pid,))
        p = cur.fetchone()
        if not p:
            conn.close()
            await q.answer("প্রোডাক্ট নেই।", show_alert=True)
            return
        if p["seller_id"] == uid:
            conn.close()
            await q.answer("নিজের প্রোডাক্ট কিনতে পারবেন না।", show_alert=True)
            return

        # stock check
        try:
            stock = int(p["stock"] if p["stock"] is not None else 1)
        except Exception:
            stock = 1
        if stock < 1:
            conn.close()
            await q.answer("স্টক শেষ!", show_alert=True)
            return

        cur.execute("SELECT balance, referrer_id FROM users WHERE user_id=?", (uid,))

        u = cur.fetchone()
        bal = u["balance"] if u else 0
        price = float(p["price"])
        if bal < price:
            conn.close()
            await q.answer(f"ব্যালেন্স কম। দরকার {price:.0f}, আছে {bal:.0f}", show_alert=True)
            return

        # commission
        try:
            pct = float(get_setting("admin_commission_percent", "10") or 0)
        except Exception:
            pct = 10.0
        if pct < 0:
            pct = 0
        if pct > 100:
            pct = 100
        commission = round(price * pct / 100.0, 2)
        seller_gets = round(price - commission, 2)

        cur.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?",
            (price, uid, price),
        )
        if cur.rowcount == 0:
            conn.close()
            await q.answer("ব্যালেন্স কম / ডাবল ক্লিক।", show_alert=True)
            return

        cur.execute(
            "UPDATE products SET stock = stock - 1 WHERE id=? AND stock >= 1",
            (pid,),
        )
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            await q.answer("স্টক শেষ!", show_alert=True)
            return

        cur.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id=?",
            (seller_gets, p["seller_id"]),
        )
        if commission > 0:
            # platform admin earns commission
            cur.execute("SELECT user_id FROM users WHERE user_id=?", (MAIN_ADMIN_ID,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT OR IGNORE INTO users (user_id, username, joined_at, last_active) VALUES (?,?,?,?)",
                    (MAIN_ADMIN_ID, "admin", datetime.now().isoformat(), datetime.now().isoformat()),
                )
            cur.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?",
                (commission, MAIN_ADMIN_ID),
            )

        cur.execute(
            """INSERT INTO orders (buyer_id, seller_id, product_id, amount, status, created_at)
               VALUES (?,?,?,?, 'paid', ?)""",
            (uid, p["seller_id"], pid, price, datetime.now().isoformat()),
        )
        order_id = cur.lastrowid
        try:
            cur.execute(
                "INSERT INTO history (user_id, kind, amount, note, created_at) VALUES (?,?,?,?,?)",
                (uid, "purchase", -price, f"order {order_id}", datetime.now().isoformat()),
            )
            cur.execute(
                "INSERT INTO history (user_id, kind, amount, note, created_at) VALUES (?,?,?,?,?)",
                (p["seller_id"], "sale", seller_gets, f"order {order_id} fee {commission}", datetime.now().isoformat()),
            )
        except Exception:
            pass

        # referral shopping commission
        try:
            ref_id = u["referrer_id"] if u else None
            if ref_id and ref_id != uid:
                rshop = float(get_setting("referral_shop_percent", "5") or 0)
                if rshop > 0:
                    rbonus = round(price * rshop / 100.0, 2)
                    if rbonus > 0:
                        cur.execute(
                            "UPDATE users SET balance = balance + ? WHERE user_id=?",
                            (rbonus, ref_id),
                        )
                        cur.execute(
                            "INSERT INTO history (user_id, kind, amount, note, created_at) VALUES (?,?,?,?,?)",
                            (ref_id, "ref_shop", rbonus, f"order {order_id}", datetime.now().isoformat()),
                        )
                        try:
                            await context.bot.send_message(
                                ref_id,
                                f"🎁 রেফার কমিশন +{rbonus:.2f} BDT (Order #{order_id})",
                            )
                        except Exception:
                            pass
        except Exception:
            pass

        conn.commit()
        conn.close()

        delivery = p["delivery_info"] or "(সেলার ডেলিভারি দিবেন)"
        success = (
            f"✅ <b>কিনা সফল!</b>\n\n"
            f"🧾 Order: <b>#{order_id}</b>\n"
            f"📦 প্রোডাক্ট: <b>{p['title']}</b>\n"
            f"💰 দাম: <b>{price:.2f} BDT</b>\n\n"
            f"📥 <b>আপনার ডেলিভারি / ডাউনলোড ইনফো:</b>\n"
            f"<code>{delivery}</code>\n\n"
            f"💡 Orders মেনু থেকে আবার Delivery দেখতে পারবেন।\n"
            f"সেলার চ্যাটও করা যাবে।"
        )
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📥 Delivery আবার দেখুন", callback_data=f"dlv_{order_id}")],
                [InlineKeyboardButton("💬 Chat Seller", callback_data=f"chatord_{order_id}")],
            ]
        )
        # photo messages cannot always edit_text — always send new clear message
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            await q.edit_message_caption(caption=f"✅ কেনা হয়েছে! Order #{order_id}")
        except Exception:
            try:
                await q.edit_message_text(f"✅ কেনা হয়েছে! Order #{order_id}")
            except Exception:
                pass

        await context.bot.send_message(
            uid, success, parse_mode=ParseMode.HTML, reply_markup=kb
        )

        try:
            await context.bot.send_message(
                p["seller_id"],
                f"🎉 নতুন সেল!\nOrder #{order_id}\n"
                f"প্রোডাক্ট: {p['title']}\n"
                f"বায়ার: `{uid}`\n"
                f"মোট: {price:.2f}\n"
                f"আপনি পাবেন: {seller_gets:.2f} (কমিশন {commission:.2f})",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        if commission > 0:
            try:
                await context.bot.send_message(
                    MAIN_ADMIN_ID,
                    f"💼 কমিশন +{commission:.2f} BDT (Order #{order_id}, {pct}%)",
                )
            except Exception:
                pass
    finally:
        context.user_data.pop(lock_key, None)


async def delivery_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    oid = int(q.data.split("_")[1])
    uid = q.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id=?", (oid,))
    o = cur.fetchone()
    if not o or o["buyer_id"] != uid:
        conn.close()
        await q.answer("অর্ডার নেই।", show_alert=True)
        return
    cur.execute("SELECT title, delivery_info FROM products WHERE id=?", (o["product_id"],))
    p = cur.fetchone()
    conn.close()
    title = p["title"] if p else "-"
    delivery = (p["delivery_info"] if p else None) or "(কোনো ডেলিভারি ইনফো নেই)"
    await context.bot.send_message(
        uid,
        f"📥 <b>Delivery — Order #{oid}</b>\n"
        f"প্রোডাক্ট: {title}\n\n"
        f"<code>{delivery}</code>",
        parse_mode=ParseMode.HTML,
    )


# ================== SELL ==================
async def sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM categories WHERE is_active=1")
    cats = cur.fetchall()
    conn.close()
    buttons = [
        [InlineKeyboardButton(f"{c['emoji']} {c['name']}", callback_data=f"scat_{c['id']}")]
        for c in cats
    ]
    await update.message.reply_text(
        "📤 <b>Sell Product</b>\nক্যাটাগরি বেছে নিন:\n"
        "⚠️ শুধু বৈধ ডিজিটাল প্রোডাক্ট।",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SELL_CAT


async def sell_cat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["sell_cat"] = int(q.data.split("_")[1])
    await q.edit_message_text("প্রোডাক্টের নাম/টাইটেল লিখুন:")
    return SELL_TITLE


async def sell_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sell_title"] = update.message.text.strip()[:120]
    await update.message.reply_text("বিবরণ লিখুন:")
    return SELL_DESC


async def sell_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sell_desc"] = update.message.text.strip()[:2000]
    await update.message.reply_text("দাম (BDT, শুধু সংখ্যা):")
    return SELL_PRICE


async def sell_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("সঠিক দাম লিখুন।")
        return SELL_PRICE
    context.user_data["sell_price"] = price
    await update.message.reply_text(
        "মেয়াদ লিখুন (যেমন: Lifetime / 30 days / 1 year):"
    )
    return SELL_DURATION


async def sell_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sell_duration"] = update.message.text.strip()[:80]
    await update.message.reply_text(
        "📦 স্টক কতগুলো আছে? (সংখ্যা লিখুন, যেমন: 1 বা 10):"
    )
    return SELL_STOCK


async def sell_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stock = int(update.message.text.strip())
        if stock < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("সঠিক স্টক সংখ্যা লিখুন (কমপক্ষে 1)।")
        return SELL_STOCK
    context.user_data["sell_stock"] = stock
    await update.message.reply_text("প্রোডাক্টের ছবি পাঠান (অথবা /skip):")
    return SELL_PHOTO


async def sell_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data["sell_photo"] = update.message.photo[-1].file_id
    else:
        context.user_data["sell_photo"] = None
    await update.message.reply_text(
        "ডেলিভারি ইনফো লিখুন (লিংক, কোড, ফাইল ইনস্ট্রাকশন — কেনার পর বায়ার দেখবে):"
    )
    return SELL_DELIVERY


async def sell_photo_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sell_photo"] = None
    await update.message.reply_text("ডেলিভারি ইনফো লিখুন:")
    return SELL_DELIVERY


async def sell_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    delivery = update.message.text.strip()[:3000]
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO products
        (seller_id, category_id, title, description, price, duration,
         photo_file_id, delivery_info, is_active, created_at, stock)
        VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
        (
            uid,
            context.user_data["sell_cat"],
            context.user_data["sell_title"],
            context.user_data["sell_desc"],
            context.user_data["sell_price"],
            context.user_data["sell_duration"],
            context.user_data.get("sell_photo"),
            delivery,
            datetime.now().isoformat(),
            int(context.user_data.get("sell_stock") or 1),
        ),
    )
    pid = cur.lastrowid
    cur.execute("UPDATE users SET is_seller=1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    for k in list(context.user_data.keys()):
        if k.startswith("sell_"):
            context.user_data.pop(k, None)
    await update.message.reply_text(
        f"✅ প্রোডাক্ট লিস্ট হয়েছে! ID: #{pid}",
        reply_markup=user_kb(is_admin(uid)),
    )
    return ConversationHandler.END


# ================== MY PRODUCTS ==================
async def my_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM products WHERE seller_id=? ORDER BY id DESC LIMIT 20", (uid,)
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("আপনার কোনো প্রোডাক্ট নেই। Sell দিয়ে যোগ করুন।")
        return
    buttons = []
    for p in rows:
        st = "✅" if p["is_active"] else "⏸"
        try:
            sk = int(p["stock"] if p["stock"] is not None else 1)
        except Exception:
            sk = 1
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{st} {p['title'][:20]} ({p['price']:.0f}) stock:{sk}",
                    callback_data=f"myprod_{p['id']}",
                )
            ]
        )
    await update.message.reply_text(
        "📦 <b>My Products</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def myprod_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[1])
    uid = q.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=? AND seller_id=?", (pid, uid))
    p = cur.fetchone()
    conn.close()
    if not p:
        await q.edit_message_text("নেই।")
        return
    buttons = [
        [
            InlineKeyboardButton(
                "⏸ Pause" if p["is_active"] else "▶️ Activate",
                callback_data=f"ptog_{pid}",
            )
        ],
        [InlineKeyboardButton("📦 Edit Stock", callback_data=f"peditstock_{pid}")],
        [InlineKeyboardButton("💰 Edit Price", callback_data=f"peditprice_{pid}")],
        [InlineKeyboardButton("📝 Edit Title", callback_data=f"pedittitle_{pid}")],
        [InlineKeyboardButton("📥 Edit Delivery", callback_data=f"peditdlv_{pid}")],
        [InlineKeyboardButton("🗑 Delete", callback_data=f"pdel_{pid}")],
    ]
    await q.edit_message_text(
        f"#{p['id']} <b>{p['title']}</b>\n"
        f"Price: {p['price']}\nStock: {p['stock'] if p['stock'] is not None else 1}\nActive: {p['is_active']}\n{(p['description'] or '')[:200]}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def ptog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[1])
    uid = q.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE products SET is_active = 1 - is_active WHERE id=? AND seller_id=?",
        (pid, uid),
    )
    conn.commit()
    conn.close()
    await q.edit_message_text("✅ স্ট্যাটাস আপডেট হয়েছে।")


async def pdel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[1])
    uid = q.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id=? AND seller_id=?", (pid, uid))
    conn.commit()
    conn.close()
    await q.edit_message_text("🗑 ডিলিট হয়েছে।")


# ================== ORDERS ==================

async def pedit_prompt_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")
    # peditstock_1 / peditprice_1 / pedittitle_1 / peditdlv_1
    kind = parts[0].replace("pedit", "")  # stock/price/title/dlv
    pid = int(parts[1])
    uid = q.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM products WHERE id=? AND seller_id=?", (pid, uid))
    if not cur.fetchone():
        conn.close()
        await q.edit_message_text("নেই।")
        return
    conn.close()
    context.user_data["edit_pid"] = pid
    if "stock" in q.data:
        context.user_data["edit_field"] = "stock"
        await q.edit_message_text("নতুন স্টক সংখ্যা লিখুন:")
        return EDIT_STOCK
    if "price" in q.data:
        context.user_data["edit_field"] = "price"
        await q.edit_message_text("নতুন দাম লিখুন:")
        return EDIT_PRICE
    if "title" in q.data:
        context.user_data["edit_field"] = "title"
        await q.edit_message_text("নতুন টাইটেল লিখুন:")
        return EDIT_TITLE
    if "dlv" in q.data:
        context.user_data["edit_field"] = "delivery"
        await q.edit_message_text("নতুন ডেলিভারি ইনফো লিখুন:")
        return EDIT_DELIVERY
    return ConversationHandler.END


async def edit_stock_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        v = int(update.message.text.strip())
        if v < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("সঠিক সংখ্যা লিখুন।")
        return EDIT_STOCK
    pid = context.user_data.get("edit_pid")
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE products SET stock=? WHERE id=? AND seller_id=?", (v, pid, uid))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ স্টক = {v}", reply_markup=user_kb(is_admin(uid)))
    return ConversationHandler.END


async def edit_price_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        v = float(update.message.text.strip())
        if v <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("সঠিক দাম লিখুন।")
        return EDIT_PRICE
    pid = context.user_data.get("edit_pid")
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE products SET price=? WHERE id=? AND seller_id=?", (v, pid, uid))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ দাম = {v}", reply_markup=user_kb(is_admin(uid)))
    return ConversationHandler.END


async def edit_title_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = update.message.text.strip()[:120]
    pid = context.user_data.get("edit_pid")
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE products SET title=? WHERE id=? AND seller_id=?", (v, pid, uid))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ টাইটেল আপডেট", reply_markup=user_kb(is_admin(uid)))
    return ConversationHandler.END


async def edit_delivery_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = update.message.text.strip()[:3000]
    pid = context.user_data.get("edit_pid")
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE products SET delivery_info=? WHERE id=? AND seller_id=?", (v, pid, uid)
    )
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ ডেলিভারি আপডেট", reply_markup=user_kb(is_admin(uid)))
    return ConversationHandler.END



async def orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT o.*, p.title FROM orders o
           LEFT JOIN products p ON p.id=o.product_id
           WHERE o.buyer_id=? OR o.seller_id=?
           ORDER BY o.id DESC LIMIT 15""",
        (uid, uid),
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("কোনো অর্ডার নেই।")
        return
    buttons = []
    for o in rows:
        role = "Buy" if o["buyer_id"] == uid else "Sell"
        buttons.append(
            [
                InlineKeyboardButton(
                    f"#{o['id']} {role} {o['title'] or ''} {o['amount']:.0f}",
                    callback_data=f"chatord_{o['id']}",
                )
            ]
        )
    await update.message.reply_text(
        "🧾 <b>Orders</b> — চ্যাট করতে ট্যাপ করুন",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def chatord_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    oid = int(q.data.split("_")[1])
    uid = q.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id=?", (oid,))
    o = cur.fetchone()
    if not o or uid not in (o["buyer_id"], o["seller_id"]):
        conn.close()
        await q.edit_message_text("অর্ডার নেই।")
        return
    cur.execute(
        "SELECT * FROM chats WHERE order_id=? ORDER BY id DESC LIMIT 10", (oid,)
    )
    msgs = list(reversed(cur.fetchall()))
    conn.close()
    other = o["seller_id"] if uid == o["buyer_id"] else o["buyer_id"]
    lines = [f"💬 Order #{oid} chat (other: `{other}`)\n"]
    for m in msgs:
        who = "You" if m["sender_id"] == uid else "Them"
        lines.append(f"<b>{who}:</b> {m['message'][:200]}")
    lines.append("\nমেসেজ লিখুন (এই চ্যাটে পাঠাতে):")
    context.user_data["chat_order"] = oid
    context.user_data["chat_other"] = other
    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )
    await context.bot.send_message(
        uid,
        f"Order #{oid} — মেসেজ লিখুন (/cancel বাতিল):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CHAT_MSG


async def chat_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    oid = context.user_data.get("chat_order")
    other = context.user_data.get("chat_other")
    if not oid:
        return ConversationHandler.END
    text = update.message.text.strip()[:1000]
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chats (order_id, sender_id, message, created_at) VALUES (?,?,?,?)",
        (oid, uid, text, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(
        "✅ পাঠানো হয়েছে।",
        reply_markup=user_kb(is_admin(uid)),
    )
    try:
        await context.bot.send_message(
            other,
            f"💬 Order #{oid} নতুন মেসেজ:\n{text}\n\nReply: Orders → #{oid}",
        )
    except Exception:
        pass
    context.user_data.pop("chat_order", None)
    context.user_data.pop("chat_other", None)
    return ConversationHandler.END


async def csell_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Contact seller before buy — open temp chat via product."""
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT seller_id, title FROM products WHERE id=?", (pid,))
    p = cur.fetchone()
    conn.close()
    if not p:
        return
    seller = p["seller_id"]
    if seller == q.from_user.id:
        await q.answer("এটা আপনারই।", show_alert=True)
        return
    # create a zero-order contact thread using product id as negative marker in user_data
    context.user_data["chat_order"] = -pid
    context.user_data["chat_other"] = seller
    await q.message.reply_text(
        f"সেলারকে মেসেজ লিখুন (প্রোডাক্ট: {p['title']}):\n/cancel বাতিল",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CHAT_MSG


# ================== DEPOSIT ==================
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payment_methods WHERE is_active=1")
    methods = cur.fetchall()
    conn.close()
    if not methods:
        await update.message.reply_text("পেমেন্ট মেথড সেট নেই। অ্যাডমিনকে বলুন।")
        return ConversationHandler.END
    try:
        default_min = float(get_setting("min_deposit", "50") or 50)
    except Exception:
        default_min = 50.0
    buttons = []
    for m in methods:
        try:
            row_min = float(m["min_amount"] or 0)
        except Exception:
            row_min = 0
        effective = resolve_method_min(m["name"], row_min)
        label = "%s (min %.0f)" % (m["name"], effective)
        buttons.append([InlineKeyboardButton(label, callback_data="dep_%s" % m["id"])])
    if get_setting("gateway_enabled") == "1":
        buttons.append(
            [InlineKeyboardButton("Auto Gateway (min 10+)", callback_data="dep_gw")]
        )
    await update.message.reply_text(
        "💳 <b>Deposit</b>\nপ্রতি মেথডের নিজস্ব minimum আলাদা।\nমেথড বেছে নিন:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return DEP_METHOD


async def dep_method_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "dep_gw":
        if get_setting("gateway_enabled") != "1":
            await q.edit_message_text("Auto Gateway OFF. Admin ON করুক।")
            return ConversationHandler.END
        api = get_setting("gateway_api_key") or get_setting("gateway_daweblab_api") or ""
        if not api:
            await q.edit_message_text("API Key নেই। Admin → Gateway Keys এ সেট করুন।")
            return ConversationHandler.END
        try:
            gmin = float(get_setting("gateway_min") or 10)
        except Exception:
            gmin = 10.0
        if gmin < 10:
            gmin = 10.0
        context.user_data["dep_gw"] = True
        context.user_data["dep_min"] = gmin
        await q.edit_message_text(
            "Auto Gateway\nMin: %.0f BDT\n\nপরিমাণ লিখুন:" % gmin
        )
        return DEP_GW_AMOUNT
    mid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payment_methods WHERE id=?", (mid,))
    m = cur.fetchone()
    conn.close()
    if not m:
        await q.edit_message_text("মেথড নেই।")
        return ConversationHandler.END
    context.user_data["dep_method"] = m["name"]
    context.user_data["dep_info"] = m["info"]
    try:
        row_min = float(m["min_amount"] or 0)
    except Exception:
        row_min = 0
    mmin = resolve_method_min(m["name"], row_min)
    context.user_data["dep_min"] = mmin
    await q.edit_message_text(
        f"মেথড: <b>{m['name']}</b>\n\n{m['info']}\n\n"
        f"পরিমাণ লিখুন (এই মেথডের min {mmin:.0f} BDT):",
        parse_mode=ParseMode.HTML,
    )
    return DEP_AMOUNT


async def dep_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        mn = float(context.user_data.get("dep_min") or get_setting("min_deposit", "50") or 50)
    except Exception:
        mn = 50.0
    try:
        amt = float(update.message.text.strip())
        if amt < mn:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"সঠিক পরিমাণ (এই মেথডের min {mn:.0f} BDT)")
        return DEP_AMOUNT
    context.user_data["dep_amount"] = amt
    await update.message.reply_text(
        f"{context.user_data['dep_info']}\n\n"
        f"পরিমাণ: <b>{amt}</b>\nপেমেন্ট করে স্ক্রিনশট পাঠান:",
        parse_mode=ParseMode.HTML,
    )
    return DEP_PROOF


async def dep_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("স্ক্রিনশট (ফটো) পাঠান।")
        return DEP_PROOF
    uid = update.effective_user.id
    fid = update.message.photo[-1].file_id
    amt = context.user_data["dep_amount"]
    method = context.user_data["dep_method"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO deposits (user_id, amount, method, proof_file_id, status, created_at)
           VALUES (?,?,?,?, 'pending', ?)""",
        (uid, amt, method, fid, datetime.now().isoformat()),
    )
    did = cur.lastrowid
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"✅ ডিপোজিট রিকোয়েস্ট #{did} পাঠানো হয়েছে। অ্যাডমিন অ্যাপ্রুভ করবে।",
        reply_markup=user_kb(is_admin(uid)),
    )
    # notify admins
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins")
    admins = [r["user_id"] for r in cur.fetchall()]
    conn.close()
    if MAIN_ADMIN_ID not in admins:
        admins.append(MAIN_ADMIN_ID)
    for aid in admins:
        try:
            await context.bot.send_photo(
                aid,
                fid,
                caption=f"💳 Deposit #{did}\nUser: `{uid}`\n{amt} via {method}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✅ Approve", callback_data=f"depok_{did}"),
                            InlineKeyboardButton("❌ Reject", callback_data=f"deprj_{did}"),
                        ]
                    ]
                ),
            )
        except Exception:
            pass
    context.user_data.clear()
    return ConversationHandler.END


async def depok_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    did = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM deposits WHERE id=?", (did,))
    d = cur.fetchone()
    if not d or d["status"] != "pending":
        conn.close()
        await q.edit_message_caption(caption="ইতিমধ্যে প্রসেসড।")
        return
    cur.execute("UPDATE deposits SET status='approved' WHERE id=?", (did,))
    cur.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id=?",
        (d["amount"], d["user_id"]),
    )
    conn.commit()
    conn.close()
    await q.edit_message_caption(caption=f"✅ Approved #{did}")
    try:
        await context.bot.send_message(
            d["user_id"],
            f"✅ ডিপোজিট অ্যাপ্রুভড: +{d['amount']} BDT",
        )
    except Exception:
        pass


async def deprj_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    did = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE deposits SET status='rejected' WHERE id=? AND status='pending'", (did,))
    cur.execute("SELECT user_id FROM deposits WHERE id=?", (did,))
    d = cur.fetchone()
    conn.commit()
    conn.close()
    await q.edit_message_caption(caption=f"❌ Rejected #{did}")
    if d:
        try:
            await context.bot.send_message(d["user_id"], f"❌ ডিপোজিট #{did} রিজেক্ট।")
        except Exception:
            pass


# ================== WITHDRAW ==================


async def dep_gw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        mn = float(context.user_data.get("dep_min") or get_setting("gateway_min") or 50)
    except Exception:
        mn = 50.0
    try:
        amt = float(update.message.text.strip())
        if amt < mn:
            raise ValueError
    except ValueError:
        await update.message.reply_text("সঠিক পরিমাণ (min %.0f)" % mn)
        return DEP_GW_AMOUNT

    uid = update.effective_user.id
    u = update.effective_user
    create_url = get_setting("gateway_create_url") or "https://client-pg.daweblab.com/api/payment/create"
    order_id = "tg_%s_%s" % (uid, int(datetime.now().timestamp()))
    payload = {
        "amount": amt,
        "cus_name": (u.full_name or u.username or str(uid))[:80],
        "cus_email": "%s@telegram.user" % uid,
        "metadata": {"user_id": uid, "bot": "marketplace"},
        "redirect_url": "https://t.me/",
        "cancel_url": "https://t.me/",
        "order_id": order_id,
        "trx_id": order_id,
        "full_name": (u.full_name or str(uid))[:80],
        "customer_name": (u.full_name or str(uid))[:80],
    }
    status, resp = _http_json("POST", create_url, gateway_headers(), payload)
    pay_url = gateway_extract_url(resp) if isinstance(resp, dict) else None
    trx = gateway_extract_trx(resp) if isinstance(resp, dict) else None
    if not trx:
        trx = order_id

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO deposits (user_id, amount, method, proof_file_id, status, created_at) VALUES (?,?,?,?,?,?)",
        (uid, amt, get_setting("gateway_name") or "AutoGateway", trx, "pending_gw", datetime.now().isoformat()),
    )
    dep_id = cur.lastrowid
    conn.commit()
    conn.close()

    if pay_url:
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Pay Now", url=pay_url)],
                [InlineKeyboardButton("I Paid - Verify", callback_data="gwver_%s" % dep_id)],
            ]
        )
    else:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Verify", callback_data="gwver_%s" % dep_id)]]
        )
    if pay_url:
        uname = (u.full_name or u.username or str(uid))
        msg = (
            "<b>Payment Details</b>\n"
            "====================\n"
            "Payment created successfully\n"
            "Name: %s\n"
            "User ID: %s\n"
            "Pay Amount: %.2f BDT\n"
            "Nicher Pay Now button e click korun.\n"
            "===================="
        ) % (uname, uid, amt)
    else:
        msg = (
            "পেমেন্ট লিংক আসেনি (HTTP %s).\n"
            "Admin API URL/Key চেক করুন।\n"
            "Response: <code>%s</code>\n"
            "Ref: <code>%s</code> Amount: %.2f"
        ) % (status, str(resp)[:300], trx, amt)
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb)
    try:
        await context.bot.send_message(
            MAIN_ADMIN_ID,
            "Auto GW deposit request\nUser: %s\nAmount: %s\nRef: %s" % (uid, amt, trx),
        )
    except Exception:
        pass
    return ConversationHandler.END


async def gw_verify_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("যাচাই হচ্ছে...")
    dep_id = int(q.data.split("_")[1])
    uid = q.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM deposits WHERE id=?", (dep_id,))
    d = cur.fetchone()
    if not d or d["user_id"] != uid:
        conn.close()
        await q.edit_message_text("ডিপোজিট নেই।")
        return
    if d["status"] == "approved":
        conn.close()
        await q.edit_message_text("আগেই অ্যাপ্রুভড।")
        return

    verify_url = get_setting("gateway_verify_url") or "https://client-pg.daweblab.com/api/payment/verify"
    trx = d["proof_file_id"]
    payload = {
        "transaction_id": trx,
        "trx_id": trx,
        "payment_id": trx,
        "order_id": trx,
        "amount": d["amount"],
    }
    status, resp = _http_json("POST", verify_url, gateway_headers(), payload)
    paid = gateway_is_paid(resp) if isinstance(resp, dict) else False
    if not paid and isinstance(resp, dict):
        low = str(resp).lower()
        if ("success" in low or "paid" in low) and "fail" not in low and "pending" not in low:
            paid = True

    if not paid:
        conn.close()
        await q.edit_message_text(
            "এখনো paid নয় (HTTP %s).\nপেমেন্ট শেষে আবার Verify চাপুন।\n<code>%s</code>"
            % (status, str(resp)[:250]),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Verify again", callback_data="gwver_%s" % dep_id)]]
            ),
        )
        return

    cur.execute(
        "UPDATE deposits SET status='approved' WHERE id=? AND status!='approved'",
        (dep_id,),
    )
    if cur.rowcount:
        cur.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id=?",
            (d["amount"], uid),
        )
        try:
            cur.execute(
                "INSERT INTO history (user_id, kind, amount, note, created_at) VALUES (?,?,?,?,?)",
                (uid, "deposit", d["amount"], "gw %s" % trx, datetime.now().isoformat()),
            )
        except Exception:
            pass
    conn.commit()
    conn.close()
    await q.edit_message_text(
        "পেমেন্ট ভেরিফাইড! +%.2f BDT যোগ হয়েছে।" % float(d["amount"])
    )
    try:
        await context.bot.send_message(
            MAIN_ADMIN_ID, "Auto GW approved User %s +%s" % (uid, d["amount"])
        )
    except Exception:
        pass



async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_setting("withdraw_enabled", "1") != "1":
        await update.message.reply_text("💸 উইথড্র বন্ধ।")
        return ConversationHandler.END
    u = get_user(update.effective_user.id)
    bal = u["balance"] if u else 0
    await update.message.reply_text(
        f"💸 Balance: {bal:.2f}\nMin withdraw: {get_setting('min_withdraw')}\n"
        f"কত টাকা উইথড্র? (সংখ্যা):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return WD_AMOUNT


async def wd_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text.strip())
        mn = float(get_setting("min_withdraw", "100"))
        if amt < mn:
            raise ValueError("min")
    except ValueError:
        await update.message.reply_text("সঠিক পরিমাণ লিখুন।")
        return WD_AMOUNT
    u = get_user(update.effective_user.id)
    if not u or u["balance"] < amt:
        await update.message.reply_text(
            "পর্যাপ্ত ব্যালেন্স নেই।",
            reply_markup=user_kb(is_admin(update.effective_user.id)),
        )
        return ConversationHandler.END
    context.user_data["wd_amount"] = amt
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM payment_methods WHERE is_active=1")
    methods = [r["name"] for r in cur.fetchall()]
    conn.close()
    buttons = [[InlineKeyboardButton(m, callback_data=f"wdm_{m}")] for m in methods]
    await update.message.reply_text(
        "মেথড বেছে নিন:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return WD_METHOD


async def wd_method_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["wd_method"] = q.data.replace("wdm_", "", 1)
    await q.edit_message_text("নম্বর / UID / বিবরণ লিখুন:")
    return WD_DETAILS


async def wd_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    details = update.message.text.strip()[:300]
    amt = context.user_data["wd_amount"]
    method = context.user_data["wd_method"]
    u = get_user(uid)
    if not u or u["balance"] < amt:
        await update.message.reply_text(
            "ব্যালেন্স কম।",
            reply_markup=user_kb(is_admin(uid)),
        )
        return ConversationHandler.END
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET balance = balance - ? WHERE user_id=?", (amt, uid)
    )
    cur.execute(
        """INSERT INTO withdraws (user_id, amount, method, details, status, created_at)
           VALUES (?,?,?,?, 'pending', ?)""",
        (uid, amt, method, details, datetime.now().isoformat()),
    )
    wid = cur.lastrowid
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"✅ Withdraw #{wid} সাবমিট। অ্যাডমিন যাচাই করে পাঠাবে।",
        reply_markup=user_kb(is_admin(uid)),
    )
    for aid in [MAIN_ADMIN_ID]:
        try:
            await context.bot.send_message(
                aid,
                f"💸 WD #{wid}\nUser `{uid}`\n{amt} via {method}\n{details}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✅ Done", callback_data=f"wdok_{wid}"),
                            InlineKeyboardButton("❌ Reject", callback_data=f"wdrj_{wid}"),
                        ]
                    ]
                ),
            )
        except Exception:
            pass
    context.user_data.clear()
    return ConversationHandler.END


async def wdok_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    wid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM withdraws WHERE id=?", (wid,))
    w = cur.fetchone()
    if not w or w["status"] != "pending":
        conn.close()
        await q.edit_message_text("Already processed.")
        return
    cur.execute("UPDATE withdraws SET status='done' WHERE id=?", (wid,))
    conn.commit()
    conn.close()
    await q.edit_message_text(f"✅ WD #{wid} done")
    try:
        await context.bot.send_message(w["user_id"], f"✅ উইথড্র #{wid} সম্পন্ন।")
    except Exception:
        pass


async def wdrj_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    wid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM withdraws WHERE id=?", (wid,))
    w = cur.fetchone()
    if not w or w["status"] != "pending":
        conn.close()
        return
    cur.execute("UPDATE withdraws SET status='rejected' WHERE id=?", (wid,))
    cur.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id=?",
        (w["amount"], w["user_id"]),
    )
    conn.commit()
    conn.close()
    await q.edit_message_text(f"❌ WD #{wid} rejected, refunded")
    try:
        await context.bot.send_message(
            w["user_id"], f"❌ উইথড্র #{wid} রিজেক্ট — ব্যালেন্স ফেরত।"
        )
    except Exception:
        pass


# ================== SUPPORT / FAQ ==================
async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    un = get_setting("support_username", "").strip().lstrip("@")
    if not un:
        await update.message.reply_text("সাপোর্ট ইউজারনেম সেট নেই।")
        return
    await update.message.reply_text(
        "🆘 Support",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{un}")]]
        ),
    )


async def faq_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        get_setting("faq_text"),
        parse_mode=ParseMode.HTML,
    )


# ================== ADMIN ==================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🔧 Admin Panel", reply_markup=admin_kb(is_main(update.effective_user.id)))


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM users")
    total = cur.fetchone()["c"]
    cur.execute(
        "SELECT user_id, username, balance, is_blocked FROM users ORDER BY user_id DESC LIMIT 25"
    )
    rows = cur.fetchall()
    conn.close()
    text = f"👥 Users: {total}\n\n"
    for r in rows:
        flag = "🚫" if r["is_blocked"] else "✅"
        text += f"{flag} `{r['user_id']}` @{r['username'] or '-'} — {r['balance']:.0f}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM users")
    users = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM products WHERE is_active=1")
    products = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM orders")
    orders = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM deposits WHERE status='pending'")
    deps = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM withdraws WHERE status='pending'")
    wds = cur.fetchone()["c"]
    cur.execute("SELECT COALESCE(SUM(balance),0) s FROM users")
    bal = cur.fetchone()["s"]
    conn.close()
    await update.message.reply_text(
        f"📊 <b>Stats</b>\n👥 {users}\n🛍️ Products {products}\n"
        f"🧾 Orders {orders}\n💳 Pending dep {deps}\n💸 Pending wd {wds}\n"
        f"💰 Total wallet {bal:.2f}",
        parse_mode=ParseMode.HTML,
    )


async def admin_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM deposits WHERE status='pending' ORDER BY id DESC LIMIT 15"
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("কোনো pending deposit নেই।")
        return
    for d in rows:
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅", callback_data=f"depok_{d['id']}"),
                    InlineKeyboardButton("❌", callback_data=f"deprj_{d['id']}"),
                ]
            ]
        )
        if d["proof_file_id"]:
            await update.message.reply_photo(
                d["proof_file_id"],
                caption=f"#{d['id']} user `{d['user_id']}` {d['amount']} {d['method']}",
                parse_mode=ParseMode.HTML,
                reply_markup=buttons,
            )
        else:
            await update.message.reply_text(
                f"#{d['id']} user `{d['user_id']}` {d['amount']} {d['method']}",
                parse_mode=ParseMode.HTML,
                reply_markup=buttons,
            )


async def admin_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM withdraws WHERE status='pending' ORDER BY id DESC LIMIT 15"
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("কোনো pending withdraw নেই।")
        return
    for w in rows:
        await update.message.reply_text(
            f"#{w['id']} `{w['user_id']}` {w['amount']} {w['method']}\n{w['details']}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅", callback_data=f"wdok_{w['id']}"),
                        InlineKeyboardButton("❌", callback_data=f"wdrj_{w['id']}"),
                    ]
                ]
            ),
        )


async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, title, price, seller_id, is_active FROM products ORDER BY id DESC LIMIT 20")
    rows = cur.fetchall()
    conn.close()
    text = "🛍️ Products\n\n"
    for p in rows:
        text += f"#{p['id']} {p['title'][:30]} {p['price']} s:{p['seller_id']} a:{p['is_active']}\n"
    await update.message.reply_text(text or "খালি")


async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = (
        f"⚙️ <b>Settings</b>\n"
        f"Min deposit: {get_setting('min_deposit')}\n"
        f"Min withdraw: {get_setting('min_withdraw')}\n"
        f"Commission: {get_setting('admin_commission_percent','10')}%\n"
        f"Support: @{get_setting('support_username') or '-'}\n"
        f"Gateway: {get_setting('gateway_enabled')}\n"
        f"Maintenance: {get_setting('maintenance')}\n\n"
        f"বাটন দিয়ে এডিট করুন:"
    )
    buttons = [
        [InlineKeyboardButton("Min Deposit (default)", callback_data="set_min_deposit")],
        [InlineKeyboardButton("Binance Min Deposit", callback_data="set_min_deposit_binance")],
        [InlineKeyboardButton("Mobile Banking Min", callback_data="set_min_deposit_mobile")],
        [InlineKeyboardButton("Admin Commission %", callback_data="set_admin_commission_percent")],
        [InlineKeyboardButton("Referral Shop %", callback_data="set_referral_shop_percent")],
        [InlineKeyboardButton("Developer Username", callback_data="set_developer_username")],
        [InlineKeyboardButton("Developer Prefill Text", callback_data="set_developer_prefill")],
        [InlineKeyboardButton("Update Message Text", callback_data="set_update_text")],
        [InlineKeyboardButton("Min Withdraw", callback_data="set_min_withdraw")],
        [InlineKeyboardButton("Support Username", callback_data="set_support_username")],
        [InlineKeyboardButton("FAQ Text", callback_data="set_faq_text")],
        [InlineKeyboardButton("🔧 Maintenance Mode ON/OFF", callback_data="tog_maint")],
    ]
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def set_field_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    if q.data == "tog_maint":
        cur = get_setting("maintenance", "0")
        set_setting("maintenance", "0" if cur == "1" else "1")
        on = get_setting("maintenance") == "1"
        await q.edit_message_text(
            "🔧 Maintenance Mode: " + ("ON — ইউজার বট ব্যবহার করতে পারবে না" if on else "OFF — বট স্বাভাবিক")
        )
        return
    key = q.data.replace("set_", "", 1)
    context.user_data["set_key"] = key
    await q.edit_message_text(f"নতুন মান লিখুন ({key}):")
    return SET_VALUE


async def set_value_recv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    key = context.user_data.get("set_key")
    if not key:
        return ConversationHandler.END
    set_setting(key, update.message.text.strip())
    context.user_data.pop("set_key", None)
    await update.message.reply_text(
        f"✅ {key} আপডেট।",
        reply_markup=admin_kb(),
    )
    return ConversationHandler.END


async def gateway_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    api = get_setting("gateway_api_key") or get_setting("gateway_daweblab_api") or ""
    sec = get_setting("gateway_secret") or get_setting("gateway_daweblab_secret") or ""
    lines = [
        "Auto Payment Gateway Setup",
        "Sob kichu Admin Panel theke set kora jabe.",
        "",
        "Name: %s" % (get_setting("gateway_name") or "Auto Gateway"),
        "Enabled: %s" % get_setting("gateway_enabled"),
        "Min: %s BDT" % (get_setting("gateway_min") or get_setting("min_deposit")),
        "API Key: %s" % ((api or "(empty)")[:24]),
        "Secret: %s" % ((sec or "(empty)")[:12]),
        "Header: %s" % (get_setting("gateway_header_name") or "api-key"),
        "Create: %s" % (get_setting("gateway_create_url") or "-"),
        "Verify: %s" % (get_setting("gateway_verify_url") or "-"),
        "",
        "1-7 set then ON/OFF.",
    ]
    body = chr(10).join(lines)
    buttons = [
        [InlineKeyboardButton("1) API Key", callback_data="set_gateway_api_key")],
        [InlineKeyboardButton("2) Secret Key", callback_data="set_gateway_secret")],
        [InlineKeyboardButton("3) Header Name", callback_data="set_gateway_header_name")],
        [InlineKeyboardButton("4) Create URL", callback_data="set_gateway_create_url")],
        [InlineKeyboardButton("5) Verify URL", callback_data="set_gateway_verify_url")],
        [InlineKeyboardButton("6) Gateway Name", callback_data="set_gateway_name")],
        [InlineKeyboardButton("7) Gateway Min", callback_data="set_gateway_min")],
        [InlineKeyboardButton("ON/OFF Gateway", callback_data="tog_gw")],
    ]
    await update.message.reply_text(body, reply_markup=InlineKeyboardMarkup(buttons))


async def tog_gw_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    cur = get_setting("gateway_enabled", "0")
    set_setting("gateway_enabled", "0" if cur == "1" else "1")
    await q.edit_message_text(f"Gateway enabled = {get_setting('gateway_enabled')}")


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        "📢 সব ইউজারকে কী পাঠাবেন? (টেক্সট):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return BROADCAST_MSG


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    msg = update.message.text
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE is_blocked=0")
    users = [r["user_id"] for r in cur.fetchall()]
    conn.close()
    ok = fail = 0
    for uid in users:
        try:
            await context.bot.send_message(uid, f"📢 {msg}")
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(
        f"Broadcast done. OK={ok} Fail={fail}",
        reply_markup=admin_kb(),
    )
    return ConversationHandler.END


async def payment_methods_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payment_methods ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    body = (
        "💳 <b>Payment Methods (ম্যানুয়াল)</b>\n\n"
        "<b>সেটআপ গাইড:</b>\n"
        "1) ➕ Add Method\n"
        "2) নাম: bKash / Nagad / Rocket / Upay / Binance Pay\n"
        "3) ইনফো উদাহরণ:\n"
        "<code>Number: 01XXXXXXXXX\n"
        "Type: Personal / Send Money\n"
        "Note: Payment এ User ID লিখুন</code>\n\n"
        "অটো গেটওয়ে → 🔑 Gateway Keys\n\n"
    )
    buttons = []
    if not rows:
        body += "⚠️ কোনো মেথড নেই — আগে Add করুন।\n"
    for m in rows:
        body += f"#{m['id']} <b>{m['name']}</b> [{'ON' if m['is_active'] else 'OFF'}] min={m['min_amount'] or 0}\n{m['info'][:70]}\n\n"
        buttons.append([
            InlineKeyboardButton(
                f"{'⏸' if m['is_active'] else '▶️'} {m['name']}",
                callback_data=f"pmtog_{m['id']}",
            ),
            InlineKeyboardButton("🗑", callback_data=f"pmdel_{m['id']}"),
            InlineKeyboardButton("Min৳", callback_data=f"pmmin_{m['id']}"),
        ])
    buttons.append([InlineKeyboardButton("➕ Add Method", callback_data="pm_add")])
    await update.message.reply_text(
        body, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def pmtog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    mid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payment_methods SET is_active = 1 - is_active WHERE id=?", (mid,)
    )
    conn.commit()
    conn.close()
    await q.answer("টগল OK", show_alert=False)
    await q.edit_message_text("✅ টগল হয়েছে। আবার 💳 Payment Methods খুলুন।")


async def pmmin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    mid = int(q.data.split("_")[1])
    context.user_data["set_key"] = f"__pmmin_{mid}"
    await q.edit_message_text("এই মেথডের minimum deposit লিখুন (যেমন 50 বা 140):")


async def pmdel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    mid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM payment_methods WHERE id=?", (mid,))
    row = cur.fetchone()
    cur.execute("DELETE FROM payment_methods WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    name = row["name"] if row else mid
    await q.edit_message_text(
        f"🗑 ডিলিট হয়েছে: <b>{name}</b>\nআবার Payment Methods খুলুন।",
        parse_mode=ParseMode.HTML,
    )


async def pm_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text(
        "মেথডের নাম লিখুন:\n"
        "উদাহরণ: bKash, Nagad, Rocket, Upay, Binance Pay"
    )
    return ADD_PAY_NAME


async def pm_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pm_name"] = update.message.text.strip()[:40]
    await update.message.reply_text(
        "ইনফো লিখুন — উদাহরণ:\n"
        "Number: 01XXXXXXXXX\n"
        "Type: Personal\n"
        "Note: User ID লিখুন"
    )
    return ADD_PAY_INFO


async def pm_add_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.user_data.get("pm_name", "Method")
    info = update.message.text.strip()[:500]
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payment_methods (name, info) VALUES (?, ?)", (name, info)
    )
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ যোগ হয়েছে।", reply_markup=admin_kb())
    return ConversationHandler.END


async def categories_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM categories ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    body = "📂 <b>Categories</b>\nইউজাররা এই নামের ভিতরে প্রোডাক্ট সেল/কিনতে পারবে।\n\n"
    buttons = []
    for c in rows:
        body += f"#{c['id']} {c['emoji']} <b>{c['name']}</b> [{'ON' if c['is_active'] else 'OFF'}]\n"
        buttons.append([
            InlineKeyboardButton(
                f"{'⏸' if c['is_active'] else '▶️'} {c['name']}",
                callback_data=f"cattog_{c['id']}",
            ),
            InlineKeyboardButton("🗑", callback_data=f"catdel_{c['id']}"),
        ])
    buttons.append([InlineKeyboardButton("➕ Add Category", callback_data="cat_add")])
    await update.message.reply_text(
        body, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def cattog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    cid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE categories SET is_active = 1 - is_active WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    await q.edit_message_text("✅ ক্যাটাগরি টগল। আবার 📂 Categories খুলুন।")


async def catdel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    cid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM categories WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    await q.edit_message_text("🗑 ক্যাটাগরি ডিলিট। আবার Categories খুলুন।")


async def cat_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await_cat_name"] = True
    await q.edit_message_text(
        "নতুন ক্যাটাগরি নাম লিখুন:\n"
        "উদাহরণ: Bot, Source Code, Website, Template, Course, Script"
    )


# ================== ROUTER ==================

async def lang_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = "bn" if q.data.endswith("bn") else "en"
    uid = q.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, uid))
    conn.commit()
    conn.close()
    msg = "ভাষা বাংলা করা হয়েছে।" if lang == "bn" else "Language set to English."
    await q.edit_message_text(msg)
    await context.bot.send_message(
        uid, msg, reply_markup=user_kb(is_admin(uid), lang)
    )


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM history WHERE user_id=? AND kind IN ('purchase','sale') ORDER BY id DESC LIMIT 30",
        (uid,),
    )
    rows = cur.fetchall()
    conn.close()
    buys = [r for r in rows if r["kind"] == "purchase"]
    sales = [r for r in rows if r["kind"] == "sale"]
    msg = "📜 <b>History</b>\n\n🛒 <b>কেনাকাটা</b>\n"
    if not buys:
        msg += "কিছু নেই\n"
    for r in buys[:15]:
        msg += f"• {r['amount']} — {r['note']} ({str(r['created_at'])[:16]})\n"
    msg += "\n📤 <b>বেচা</b>\n"
    if not sales:
        msg += "কিছু নেই\n"
    for r in sales[:15]:
        msg += f"• +{r['amount']} — {r['note']} ({str(r['created_at'])[:16]})\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Checking for updates...")
    import asyncio
    await asyncio.sleep(1.2)
    try:
        await msg.edit_text("⏳ Loading...")
        await asyncio.sleep(0.8)
    except Exception:
        pass
    text_u = get_setting(
        "update_text",
        "✅ Bot already up to date.\nকোনো নতুন আপডেট নেই।",
    )
    try:
        await msg.edit_text(text_u)
    except Exception:
        await update.message.reply_text(text_u)


async def developer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uname = (get_setting("developer_username") or "").strip().lstrip("@")
    prefill = get_setting(
        "developer_prefill", "আমি ওয়েবসাইট বা বট বানাতে চাই"
    )
    if not uname:
        await update.message.reply_text(
            "👨‍💻 Developer এখনো সেট করা হয়নি। Admin সেট করবে।"
        )
        return
    from urllib.parse import quote
    link = f"https://t.me/{uname}?text={quote(prefill)}"
    await update.message.reply_text(
        f"👨‍💻 <b>Developer</b>\n@{uname}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("✉️ Message Developer", url=link)]]
        ),
    )


async def admin_bal_start(update: Update, context: ContextTypes.DEFAULT_TYPE, mode="add"):
    if not is_admin(update.effective_user.id):
        return
    context.user_data["bal_mode"] = mode
    await update.message.reply_text("ইউজার ID লিখুন:")
    return BAL_USER


async def admin_bal_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["bal_uid"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("সঠিক User ID লিখুন।")
        return BAL_USER
    await update.message.reply_text("পরিমাণ লিখুন:")
    return BAL_AMT


async def admin_bal_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text.strip())
        if amt <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("সঠিক পরিমাণ।")
        return BAL_AMT
    uid = context.user_data.get("bal_uid")
    mode = context.user_data.get("bal_mode", "add")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        await update.message.reply_text("ইউজার নেই।", reply_markup=admin_kb())
        return ConversationHandler.END
    if mode == "add":
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    else:
        cur.execute(
            "UPDATE users SET balance = MAX(0, balance - ?) WHERE user_id=?", (amt, uid)
        )
    conn.commit()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    nb = cur.fetchone()["balance"]
    conn.close()
    await update.message.reply_text(
        f"✅ User {uid} balance = {nb:.2f}", reply_markup=admin_kb(is_main(update.effective_user.id))
    )
    return ConversationHandler.END


async def block_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE, block=True):
    if not is_admin(update.effective_user.id):
        return
    context.user_data["block_mode"] = 1 if block else 0
    await update.message.reply_text("ইউজার ID লিখুন:")
    return BLOCK_USER


async def block_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("সঠিক ID।")
        return BLOCK_USER
    mode = context.user_data.get("block_mode", 1)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_blocked=? WHERE user_id=?", (mode, uid))
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"{'🚫 Blocked' if mode else '✅ Unblocked'} {uid}",
        reply_markup=admin_kb(is_main(update.effective_user.id)),
    )
    return ConversationHandler.END


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    ensure_user(uid, update.effective_user.username, update.effective_user.full_name)
    u = get_user(uid)
    if u and u["is_blocked"]:
        await update.message.reply_text("ব্লকড।")
        return
    if get_setting("maintenance") == "1" and not is_admin(uid):
        await update.message.reply_text("🔧 Maintenance")
        return

    if context.user_data.get("await_cat_name") and is_admin(uid):
        context.user_data.pop("await_cat_name", None)
        name = text.strip()[:40]
        emoji = "📦"
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO categories (name, emoji) VALUES (?, ?)", (name, emoji)
            )
            conn.commit()
            await update.message.reply_text(
                "✅ Category added: " + name,
                reply_markup=admin_kb(is_main(uid)),
            )
        except Exception as e:
            await update.message.reply_text("Error: %s (নাম আগে থাকতে পারে)" % e)
        conn.close()
        return

    # generic setting value (referral bonus etc.)
    if context.user_data.get("set_key") and is_admin(uid):
        key = context.user_data.pop("set_key")
        if str(key).startswith("__pmmin_"):
            try:
                mid = int(str(key).split("_")[-1])
                val = float(text.strip())
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE payment_methods SET min_amount=? WHERE id=?", (val, mid))
                conn.commit()
                conn.close()
                await update.message.reply_text(f"✅ Method #{mid} min deposit = {val}", reply_markup=admin_kb(is_main(uid)))
            except Exception as e:
                await update.message.reply_text("Error: %s" % e)
            return
        set_setting(key, text)
        await update.message.reply_text("✅ %s = %s" % (key, text), reply_markup=admin_kb(is_main(uid)))
        return


    if context.user_data.get("await_add_admin") and is_main(uid):
        context.user_data.pop("await_add_admin", None)
        try:
            aid = int(text)
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO admins (user_id, role, added_at) VALUES (?,?,?)",
                        (aid, "admin", datetime.now().isoformat()))
            conn.commit(); conn.close()
            await update.message.reply_text("✅ Admin %s" % aid, reply_markup=admin_kb(True))
        except Exception as e:
            await update.message.reply_text("Error: %s" % e)
        return
    if context.user_data.get("await_rm_admin") and is_main(uid):
        context.user_data.pop("await_rm_admin", None)
        try:
            aid = int(text)
            if aid == MAIN_ADMIN_ID:
                await update.message.reply_text("Main সরানো যাবে না")
                return
            conn = get_db(); cur = conn.cursor()
            cur.execute("DELETE FROM admins WHERE user_id=? AND role!='main'", (aid,))
            conn.commit(); conn.close()
            await update.message.reply_text("Removed %s" % aid, reply_markup=admin_kb(True))
        except Exception as e:
            await update.message.reply_text(str(e))
        return
    if context.user_data.get("await_transfer") and is_main(uid):
        context.user_data.pop("await_transfer", None)
        try:
            new_id = int(text)
            old = uid
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO admins (user_id, role, added_at) VALUES (?,?,?)",
                        (new_id, "main", datetime.now().isoformat()))
            cur.execute("UPDATE admins SET role='admin' WHERE user_id=?", (old,))
            conn.commit(); conn.close()
            await update.message.reply_text("✅ Ownership -> %s" % new_id, reply_markup=admin_kb(False))
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if text == "👑 Add Admin" and is_main(uid):
        context.user_data["await_add_admin"] = True
        await update.message.reply_text("Admin User ID:")
        return
    if text == "🗑️ Remove Admin" and is_main(uid):
        context.user_data["await_rm_admin"] = True
        await update.message.reply_text("Remove Admin User ID:")
        return
    if text == "🔄 Ownership Transfer" and is_main(uid):
        context.user_data["await_transfer"] = True
        await update.message.reply_text("New Main Admin User ID:")
        return

    # force channel add text
    if context.user_data.get("await_ch") and is_admin(uid):
        raw = text.strip()
        context.user_data.pop("await_ch", None)
        title, link = raw, ""
        try:
            chat = await context.bot.get_chat(int(raw) if raw.lstrip("-").isdigit() else raw)
            title = chat.title or raw
            if getattr(chat, "username", None):
                link = "https://t.me/" + chat.username
        except Exception as e:
            await update.message.reply_text("⚠️ %s — saved with manual title" % e)
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO force_channels (chat_id, title, link) VALUES (?,?,?)",
            (raw, title, link),
        )
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ Channel: " + str(title), reply_markup=admin_kb(is_main(uid)))
        return

    if text == "💰 Wallet":
        await wallet(update, context)
    elif text == "👤 Profile":
        await profile_cmd(update, context)
    elif text == "📜 History":
        await history_cmd(update, context)
    elif text in ("🌐 Language", "Language"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("বাংলা", callback_data="lang_bn")],
            [InlineKeyboardButton("English", callback_data="lang_en")],
        ])
        await update.message.reply_text("ভাষা / Language:", reply_markup=kb)
    elif text == "🔄 Update":
        await update_cmd(update, context)
    elif text == "👨‍💻 Developer":
        await developer_cmd(update, context)
    elif text == "🛒 Market":
        await market(update, context)
    elif text == "👥 Referral":
        await referral_cmd(update, context)
    elif text == "📦 My Products":
        await my_products(update, context)
    elif text == "🧾 Orders":
        await orders_cmd(update, context)
    elif text == "💬 My Chats":
        await orders_cmd(update, context)
    elif text == "🆘 Support":
        await support_cmd(update, context)
    elif text == "ℹ️ FAQ":
        await faq_cmd(update, context)
    elif text == "🔧 Admin Panel" and is_admin(uid):
        await admin_panel(update, context)
    elif text == "🏠 User Panel":
        await update.message.reply_text("User Panel", reply_markup=user_kb(is_admin(uid)))
    elif text == "👥 Users" and is_admin(uid):
        await admin_users(update, context)
    elif text == "📊 Stats" and is_admin(uid):
        await admin_stats(update, context)
    elif text == "📥 Deposits" and is_admin(uid):
        await admin_deposits(update, context)
    elif text == "💸 Withdrawals" and is_admin(uid):
        await admin_withdrawals(update, context)
    elif text == "🛍️ All Products" and is_admin(uid):
        await admin_products(update, context)
    elif text == "📂 Categories" and is_admin(uid):
        await categories_admin(update, context)
    elif text == "💳 Payment Methods" and is_admin(uid):
        await payment_methods_admin(update, context)
    elif text == "💵 Add Balance" and is_admin(uid):
        return await admin_bal_start(update, context, "add")
    elif text == "💵 Remove Balance" and is_admin(uid):
        return await admin_bal_start(update, context, "remove")
    elif text == "🚫 Block User" and is_admin(uid):
        return await block_user_start(update, context, True)
    elif text == "✅ Unblock User" and is_admin(uid):
        return await block_user_start(update, context, False)
    elif text == "⚙️ Settings" and is_admin(uid):
        await admin_settings(update, context)
    elif text == "🔑 Gateway Keys" and is_admin(uid):
        await gateway_keys(update, context)
    elif text == "📄 Export Users" and is_admin(uid):
        await export_users(update, context)
    elif text == "📢 Force Channels" and is_admin(uid):
        await force_channels_menu(update, context)
    elif text == "🎁 Referral Bonus" and is_admin(uid):
        await ref_bonus_prompt(update, context)
    elif text == "🤖 Bot ON/OFF" and is_admin(uid):
        await toggle_bot(update, context)
    elif text == "💸 WD ON/OFF" and is_admin(uid):
        await toggle_wd(update, context)
    elif text == "➕ Admin Add Product" and is_admin(uid):
        await update.message.reply_text(
            "➕ Admin Product\nনিচের Sell ফ্লো শুরু হচ্ছে — ক্যাটাগরি বেছে নিন।"
        )
        return await sell_start(update, context)



def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("ERROR: BOT_TOKEN সেট করুন marketplace_bot.py এ")
        return
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()


    edit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(pedit_prompt_cb, pattern=r"^pedit(stock|price|title|dlv)_\d+$"),
        ],
        states={
            EDIT_STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_stock_val)],
            EDIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_price_val)],
            EDIT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_title_val)],
            EDIT_DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_delivery_val)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    bal_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^💵 Add Balance$"), lambda u,c: admin_bal_start(u,c,"add")),
            MessageHandler(filters.Regex("^💵 Remove Balance$"), lambda u,c: admin_bal_start(u,c,"remove")),
        ],
        states={
            BAL_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bal_user)],
            BAL_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bal_amt)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    block_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🚫 Block User$"), lambda u,c: block_user_start(u,c,True)),
            MessageHandler(filters.Regex("^✅ Unblock User$"), lambda u,c: block_user_start(u,c,False)),
        ],
        states={
            BLOCK_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, block_user_id)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )


    sell_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📤 Sell$"), sell_start),
            MessageHandler(filters.Regex("^➕ Admin Add Product$"), sell_start),
        ],
        states={
            SELL_CAT: [CallbackQueryHandler(sell_cat_cb, pattern=r"^scat_")],
            SELL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_title)],
            SELL_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_desc)],
            SELL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_price)],
            SELL_DURATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sell_duration)
            ],
            SELL_STOCK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sell_stock)
            ],
            SELL_PHOTO: [
                MessageHandler(filters.PHOTO, sell_photo),
                CommandHandler("skip", sell_photo_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sell_photo_skip),
            ],
            SELL_DELIVERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sell_delivery)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    dep_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💳 Deposit$"), deposit_start)],
        states={
            DEP_METHOD: [CallbackQueryHandler(dep_method_cb, pattern=r"^dep_")],
            DEP_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dep_amount)],
            DEP_PROOF: [MessageHandler(filters.PHOTO, dep_proof)],
            DEP_GW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dep_gw_amount)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    wd_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Withdraw$"), withdraw_start)],
        states={
            WD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, wd_amount)],
            WD_METHOD: [CallbackQueryHandler(wd_method_cb, pattern=r"^wdm_")],
            WD_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, wd_details)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    chat_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(chatord_cb, pattern=r"^chatord_"),
            CallbackQueryHandler(csell_cb, pattern=r"^csell_"),
        ],
        states={
            CHAT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_msg)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    bc_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📢 Broadcast$"), broadcast_start)
        ],
        states={
            BROADCAST_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    set_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                set_field_cb,
                pattern=r"^(set_min_deposit|set_min_deposit_binance|set_min_deposit_mobile|set_min_withdraw|set_support_username|set_faq_text|set_gateway_nagorik_api|set_gateway_nagorik_secret|set_admin_commission_percent|set_gateway_rupantor_api|set_gateway_rupantor_secret|set_gateway_daweblab_api|set_gateway_daweblab_secret|set_referral_shop_percent|set_developer_username|set_developer_prefill|set_update_text|set_gateway_api_key|set_gateway_secret|set_gateway_header_name|set_gateway_create_url|set_gateway_verify_url|set_gateway_name|set_gateway_min)$",
            )
        ],
        states={
            SET_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_value_recv)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    pm_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(pm_add_cb, pattern=r"^pm_add$")],
        states={
            ADD_PAY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pm_add_name)
            ],
            ADD_PAY_INFO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pm_add_info)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(edit_conv)
    app.add_handler(bal_conv)
    app.add_handler(block_conv)
    app.add_handler(sell_conv)
    app.add_handler(dep_conv)
    app.add_handler(wd_conv)
    app.add_handler(chat_conv)
    app.add_handler(bc_conv)
    app.add_handler(set_conv)
    app.add_handler(pm_conv)

    app.add_handler(CallbackQueryHandler(check_join_cb, pattern=r"^check_join$"))
    app.add_handler(CallbackQueryHandler(rmch_cb, pattern=r"^rmch_\d+$"))
    app.add_handler(CallbackQueryHandler(addch_cb, pattern=r"^addch$"))
    app.add_handler(CallbackQueryHandler(cat_cb, pattern=r"^cat_\d+$"))
    app.add_handler(CallbackQueryHandler(cat_cb, pattern=r"^cat_all$"))

    app.add_handler(CallbackQueryHandler(back_market_cb, pattern=r"^back_market$"))
    app.add_handler(CallbackQueryHandler(prod_cb, pattern=r"^prod_\d+$"))
    app.add_handler(CallbackQueryHandler(buy_cb, pattern=r"^buy_\d+$"))
    app.add_handler(CallbackQueryHandler(gw_verify_cb, pattern=r"^gwver_\d+$"))
    app.add_handler(CallbackQueryHandler(lang_cb, pattern=r"^lang_(bn|en)$"))
    app.add_handler(CallbackQueryHandler(delivery_cb, pattern=r"^dlv_\d+$"))
    app.add_handler(CallbackQueryHandler(myprod_cb, pattern=r"^myprod_\d+$"))
    app.add_handler(CallbackQueryHandler(ptog_cb, pattern=r"^ptog_\d+$"))
    app.add_handler(CallbackQueryHandler(pdel_cb, pattern=r"^pdel_\d+$"))
    app.add_handler(CallbackQueryHandler(depok_cb, pattern=r"^depok_\d+$"))
    app.add_handler(CallbackQueryHandler(deprj_cb, pattern=r"^deprj_\d+$"))
    app.add_handler(CallbackQueryHandler(wdok_cb, pattern=r"^wdok_\d+$"))
    app.add_handler(CallbackQueryHandler(wdrj_cb, pattern=r"^wdrj_\d+$"))
    app.add_handler(CallbackQueryHandler(pmtog_cb, pattern=r"^pmtog_\d+$"))
    app.add_handler(CallbackQueryHandler(pmdel_cb, pattern=r"^pmdel_\d+$"))
    app.add_handler(CallbackQueryHandler(pmmin_cb, pattern=r"^pmmin_\d+$"))
    app.add_handler(CallbackQueryHandler(cattog_cb, pattern=r"^cattog_\d+$"))
    app.add_handler(CallbackQueryHandler(catdel_cb, pattern=r"^catdel_\d+$"))
    app.add_handler(CallbackQueryHandler(cat_add_cb, pattern=r"^cat_add$"))
    app.add_handler(CallbackQueryHandler(tog_gw_cb, pattern=r"^tog_gw$"))
    app.add_handler(CallbackQueryHandler(set_field_cb, pattern=r"^tog_maint$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Marketplace bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
