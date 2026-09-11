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
    SELL_PHOTO,
    SELL_DELIVERY,
    CHAT_MSG,
    BROADCAST_MSG,
    SET_VALUE,
    ADD_PAY_NAME,
    ADD_PAY_INFO,
) = range(18)


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
        "min_withdraw": "100",
        "bot_enabled": "1",
        "withdraw_enabled": "1",
        "referral_bonus": "10",
        "support_username": "",
        "faq_text": (
            "ℹ️ <b>FAQ</b>\n\n"
            "• 💰 Wallet — ব্যালেন্স দেখুন\n"
            "• 🛒 Market — প্রোডাক্ট কিনুন\n"
            "• 📤 Sell — প্রোডাক্ট সেল করুন\n"
            "• 📦 My Products — আপনার লিস্টিং\n"
            "• 🧾 Orders — কেনা/বেচার অর্ডার\n"
            "• 💳 Deposit — ব্যালেন্স যোগ\n"
            "• 💸 Withdraw — উইথড্র রিকোয়েস্ট\n"
            "• 🆘 Support — সাপোর্ট\n\n"
            "শুধু বৈধ ডিজিটাল প্রোডাক্ট সেল করুন।"
        ),
        "welcome_text": "🛒 <b>Digital Marketplace</b>\nবৈধ ডিজিটাল প্রোডাক্ট কিনুন ও বিক্রি করুন।",
        "gateway_nagorik_api": "",
        "gateway_nagorik_secret": "",
        "gateway_enabled": "0",
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

    cur.execute("SELECT COUNT(*) c FROM payment_methods")
    if cur.fetchone()["c"] == 0:
        for name, info in [
            ("bKash", "Personal: 01XXXXXXXXX\nReference: your user id"),
            ("Nagad", "Personal: 01XXXXXXXXX\nReference: your user id"),
            ("Rocket", "Personal: 01XXXXXXXXX"),
        ]:
            cur.execute(
                "INSERT INTO payment_methods (name, info) VALUES (?, ?)", (name, info)
            )

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


def user_kb(show_admin=False):
    rows = [
        ["💰 Wallet", "🛒 Market"],
        ["📤 Sell", "📦 My Products"],
        ["🧾 Orders", "👥 Referral"],
        ["💳 Deposit", "💸 Withdraw"],
        ["🆘 Support", "ℹ️ FAQ"],
    ]
    if show_admin:
        rows.append(["🔧 Admin Panel"])
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
        reply_markup=user_kb(is_admin(user.id)),
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
    text = (
        f"📦 <b>{p['title']}</b>\n"
        f"ক্যাটাগরি: {p['cname']}\n"
        f"দাম: <b>{p['price']:.2f} BDT</b>\n"
        f"মেয়াদ: {p['duration']}\n"
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
    await q.answer()
    pid = int(q.data.split("_")[1])
    uid = q.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=? AND is_active=1", (pid,))
    p = cur.fetchone()
    if not p:
        conn.close()
        await q.edit_message_text("প্রোডাক্ট নেই।")
        return
    if p["seller_id"] == uid:
        conn.close()
        await q.answer("নিজের প্রোডাক্ট কিনতে পারবেন না।", show_alert=True)
        return
    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    u = cur.fetchone()
    bal = u["balance"] if u else 0
    if bal < p["price"]:
        conn.close()
        await q.answer(
            f"ব্যালেন্স কম। দরকার {p['price']:.0f}, আছে {bal:.0f}",
            show_alert=True,
        )
        return
    # deduct buyer, credit seller
    cur.execute(
        "UPDATE users SET balance = balance - ? WHERE user_id=?", (p["price"], uid)
    )
    cur.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id=?",
        (p["price"], p["seller_id"]),
    )
    cur.execute(
        """INSERT INTO orders (buyer_id, seller_id, product_id, amount, status, created_at)
           VALUES (?,?,?,?, 'paid', ?)""",
        (uid, p["seller_id"], pid, p["price"], datetime.now().isoformat()),
    )
    order_id = cur.lastrowid
    conn.commit()
    conn.close()

    delivery = p["delivery_info"] or "(সেলার ডেলিভারি দিবেন)"
    await q.edit_message_text(
        f"✅ <b>কিনা সম্পন্ন!</b>\nOrder #{order_id}\n"
        f"প্রোডাক্ট: {p['title']}\nদাম: {p['price']:.2f}\n\n"
        f"📦 <b>Delivery:</b>\n{delivery}\n\n"
        f"সেলারের সাথে চ্যাট: Orders → Contact",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("💬 Chat Seller", callback_data=f"chatord_{order_id}")]]
        ),
    )
    try:
        await context.bot.send_message(
            p["seller_id"],
            f"🎉 নতুন সেল!\nOrder #{order_id}\n"
            f"প্রোডাক্ট: {p['title']}\n"
            f"বায়ার: `{uid}`\nAmount: {p['price']:.2f}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


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
        "প্রোডাক্টের ছবি পাঠান (অথবা /skip):"
    )
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
         photo_file_id, delivery_info, is_active, created_at)
        VALUES (?,?,?,?,?,?,?,?,1,?)""",
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
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{st} {p['title'][:24]} ({p['price']:.0f})",
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
        [InlineKeyboardButton("🗑 Delete", callback_data=f"pdel_{pid}")],
    ]
    await q.edit_message_text(
        f"#{p['id']} <b>{p['title']}</b>\n"
        f"Price: {p['price']}\nActive: {p['is_active']}\n{p['description'][:200]}",
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
    buttons = [
        [InlineKeyboardButton(m["name"], callback_data=f"dep_{m['id']}")]
        for m in methods
    ]
    # gateway note
    if get_setting("gateway_enabled") == "1":
        buttons.append(
            [InlineKeyboardButton("⚡ Auto Gateway (NagorikPay)", callback_data="dep_gw")]
        )
    await update.message.reply_text(
        f"💳 <b>Deposit</b>\nMin: {get_setting('min_deposit')} BDT\nমেথড বেছে নিন:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return DEP_METHOD


async def dep_method_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "dep_gw":
        api = get_setting("gateway_nagorik_api")
        if not api:
            await q.edit_message_text(
                "⚠️ Auto gateway API এখনো সেট হয়নি।\n"
                "Admin → Gateway Keys এ API Key দিন।\n"
                "এখন ম্যানুয়াল মেথড ব্যবহার করুন।"
            )
            return ConversationHandler.END
        await q.edit_message_text(
            "⚡ Auto gateway কনফিগারড।\n"
            "পূর্ণ অটো পেমেন্ট চালু করতে NagorikPay মার্চেন্ট API ডক অনুযায়ী "
            "ইন্টিগ্রেশন সম্পন্ন করতে হবে।\n"
            "এখন ম্যানুয়াল ডিপোজিট ব্যবহার করুন।"
        )
        return ConversationHandler.END
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
    await q.edit_message_text(
        f"মেথড: <b>{m['name']}</b>\n\n{m['info']}\n\n"
        f"পরিমাণ লিখুন (min {get_setting('min_deposit')}):",
        parse_mode=ParseMode.HTML,
    )
    return DEP_AMOUNT


async def dep_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text.strip())
        mn = float(get_setting("min_deposit", "50"))
        if amt < mn:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"সঠিক পরিমাণ (min {get_setting('min_deposit')})")
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
        f"Support: @{get_setting('support_username') or '-'}\n"
        f"Gateway: {get_setting('gateway_enabled')}\n"
        f"Maintenance: {get_setting('maintenance')}\n\n"
        f"বাটন দিয়ে এডিট করুন:"
    )
    buttons = [
        [InlineKeyboardButton("Min Deposit", callback_data="set_min_deposit")],
        [InlineKeyboardButton("Min Withdraw", callback_data="set_min_withdraw")],
        [InlineKeyboardButton("Support Username", callback_data="set_support_username")],
        [InlineKeyboardButton("FAQ Text", callback_data="set_faq_text")],
        [InlineKeyboardButton("Toggle Maintenance", callback_data="tog_maint")],
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
        await q.edit_message_text(f"Maintenance = {get_setting('maintenance')}")
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
    text = (
        "🔑 <b>Payment Gateway</b>\n\n"
        "NagorikPay (উদাহরণ):\n"
        f"API Key: <code>{get_setting('gateway_nagorik_api') or '(empty)'}</code>\n"
        f"Secret: <code>{(get_setting('gateway_nagorik_secret') or '(empty)')[:8]}...</code>\n"
        f"Enabled: {get_setting('gateway_enabled')}\n\n"
        "Affiliate লিংক দিয়ে অটো পেমেন্ট হয় না — মার্চেন্ট API Key লাগে।\n"
        "কী সেট করতে বাটন চাপুন:"
    )
    buttons = [
        [InlineKeyboardButton("Set API Key", callback_data="set_gateway_nagorik_api")],
        [InlineKeyboardButton("Set Secret", callback_data="set_gateway_nagorik_secret")],
        [InlineKeyboardButton("Toggle Gateway ON/OFF", callback_data="tog_gw")],
    ]
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
    )


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
    cur.execute("SELECT * FROM payment_methods")
    rows = cur.fetchall()
    conn.close()
    text = "💳 Payment Methods\n\n"
    buttons = []
    for m in rows:
        text += f"#{m['id']} {m['name']} active={m['is_active']}\n{m['info'][:80]}\n\n"
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{'⏸' if m['is_active'] else '▶️'} {m['name']}",
                    callback_data=f"pmtog_{m['id']}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton("➕ Add Method", callback_data="pm_add")])
    await update.message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(buttons)
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
    await q.edit_message_text("✅ টগল হয়েছে। আবার Payment Methods খুলুন।")


async def pm_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text("মেথডের নাম (যেমন bKash):")
    return ADD_PAY_NAME


async def pm_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pm_name"] = update.message.text.strip()[:40]
    await update.message.reply_text("ইনফো / নম্বর লিখুন:")
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
    cur.execute("SELECT * FROM categories")
    rows = cur.fetchall()
    conn.close()
    text = "📂 Categories\n\n"
    for c in rows:
        text += f"#{c['id']} {c['emoji']} {c['name']} active={c['is_active']}\n"
    await update.message.reply_text(text)


# ================== ROUTER ==================
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

    # generic setting value (referral bonus etc.)
    if context.user_data.get("set_key") and is_admin(uid):
        key = context.user_data.pop("set_key")
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
        await update.message.reply_text("Admin product: use 📤 Sell flow as admin (same), or list via Sell.")



def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("ERROR: BOT_TOKEN সেট করুন marketplace_bot.py এ")
        return
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    sell_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📤 Sell$"), sell_start)],
        states={
            SELL_CAT: [CallbackQueryHandler(sell_cat_cb, pattern=r"^scat_")],
            SELL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_title)],
            SELL_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_desc)],
            SELL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_price)],
            SELL_DURATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sell_duration)
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
                pattern=r"^(set_min_deposit|set_min_withdraw|set_support_username|set_faq_text|set_gateway_nagorik_api|set_gateway_nagorik_secret)$",
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
    app.add_handler(CallbackQueryHandler(myprod_cb, pattern=r"^myprod_\d+$"))
    app.add_handler(CallbackQueryHandler(ptog_cb, pattern=r"^ptog_\d+$"))
    app.add_handler(CallbackQueryHandler(pdel_cb, pattern=r"^pdel_\d+$"))
    app.add_handler(CallbackQueryHandler(depok_cb, pattern=r"^depok_\d+$"))
    app.add_handler(CallbackQueryHandler(deprj_cb, pattern=r"^deprj_\d+$"))
    app.add_handler(CallbackQueryHandler(wdok_cb, pattern=r"^wdok_\d+$"))
    app.add_handler(CallbackQueryHandler(wdrj_cb, pattern=r"^wdrj_\d+$"))
    app.add_handler(CallbackQueryHandler(pmtog_cb, pattern=r"^pmtog_\d+$"))
    app.add_handler(CallbackQueryHandler(tog_gw_cb, pattern=r"^tog_gw$"))
    app.add_handler(CallbackQueryHandler(set_field_cb, pattern=r"^tog_maint$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Marketplace bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
