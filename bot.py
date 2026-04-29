import logging
import sqlite3
import requests
import hashlib
import json
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from config import BOT_TOKEN, OWNER_ID, CRYPTOMUS_MERCHANT_ID, CRYPTOMUS_PAYMENT_KEY

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# States
ADD_PRODUCT_NAME, ADD_PRODUCT_PRICE, ADD_PRODUCT_CONTENT = range(3)
MANUAL_DEPOSIT_USER, MANUAL_DEPOSIT_AMOUNT = range(3, 5)
CRYPTO_AMOUNT = 5

# DB Helper Functions
def get_db_connection():
    conn = sqlite3.connect('store.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_user_balance(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if not user:
        conn.execute('INSERT INTO users (user_id, balance) VALUES (?, ?)', (user_id, 0.0))
        conn.commit()
        balance = 0.0
    else:
        balance = user['balance']
    conn.close()
    return balance

def update_user_balance(user_id, amount):
    conn = get_db_connection()
    conn.execute('INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)', (user_id,))
    conn.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.execute('INSERT INTO transactions (user_id, amount, type) VALUES (?, ?, ?)', (user_id, amount, 'deposit' if amount > 0 else 'purchase'))
    conn.commit()
    conn.close()

# Cryptomus Helper
def create_invoice(amount, user_id):
    url = "https://api.cryptomus.com/v1/payment"
    order_id = f"{user_id}_{int(hashlib.md5(str(amount).encode()).hexdigest(), 16) % 1000000}"
    data = {
        "amount": str(amount),
        "currency": "USD",
        "order_id": order_id,
        "lifetime": 3600
    }
    json_data = json.dumps(data)
    sign = hashlib.md5(base64.b64encode(json_data.encode()) + CRYPTOMUS_PAYMENT_KEY.encode()).hexdigest()
    headers = {
        "merchant": CRYPTOMUS_MERCHANT_ID,
        "sign": sign,
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, headers=headers, data=json_data)
        return response.json()
    except Exception as e:
        logger.error(f"Cryptomus Error: {e}")
        return None

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_user_balance(user_id)
    text = f"🛒 *مرحباً بك في متجر Zstore*\n\n💰 رصيدك الحالي: `{balance:.2f}$`"
    keyboard = [
        [InlineKeyboardButton("🛍️ تصفح المنتجات", callback_data='view_products')],
        [InlineKeyboardButton("💳 شحن الرصيد", callback_data='deposit_menu')],
        [InlineKeyboardButton("👤 حسابي", callback_data='my_account')]
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("➕ إضافة منتج", callback_data='add_product')],
        [InlineKeyboardButton("💵 شحن يدوي", callback_data='manual_deposit')],
        [InlineKeyboardButton("🔙 العودة", callback_data='main_menu')]
    ]
    await query.edit_message_text("🛠️ لوحة تحكم الأدمن:", reply_markup=InlineKeyboardMarkup(keyboard))

async def view_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products').fetchall()
    conn.close()
    if not products:
        await query.edit_message_text("❌ لا توجد منتجات حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة", callback_data='main_menu')]]))
        return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - {p['price']}$", callback_data=f"prod_{p['id']}")] for p in products]
    keyboard.append([InlineKeyboardButton("🔙 العودة", callback_data='main_menu')])
    await query.edit_message_text("📦 المنتجات المتوفرة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def product_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = query.data.split('_')[1]
    conn = get_db_connection()
    p = conn.execute('SELECT * FROM products WHERE id = ?', (prod_id,)).fetchone()
    conn.close()
    text = f"📦 *المنتج:* {p['name']}\n💰 *السعر:* {p['price']}$"
    keyboard = [
        [InlineKeyboardButton("✅ شراء", callback_data=f"buy_{p['id']}")],
        [InlineKeyboardButton("🔙 العودة", callback_data='view_products')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    prod_id = query.data.split('_')[1]
    conn = get_db_connection()
    p = conn.execute('SELECT * FROM products WHERE id = ?', (prod_id,)).fetchone()
    balance = get_user_balance(user_id)
    if balance < p['price']:
        await query.edit_message_text("❌ رصيدك غير كافٍ!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 شحن", callback_data='deposit_menu')]]))
        return
    update_user_balance(user_id, -p['price'])
    await query.edit_message_text(f"✅ تم الشراء!\n\n📦 *{p['name']}*\n🔑 *المحتوى:* `{p['content']}`", parse_mode='Markdown')

async def deposit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⚡ شحن تلقائي (Cryptomus)", callback_data='crypto_dep')],
        [InlineKeyboardButton("👤 شحن يدوي (أدمن)", url=f"tg://user?id={OWNER_ID}")],
        [InlineKeyboardButton("🔙 العودة", callback_data='main_menu')]
    ]
    await query.edit_message_text("💰 اختر طريقة الشحن:", reply_markup=InlineKeyboardMarkup(keyboard))

# Conversation Handlers
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("أرسل اسم المنتج:")
    return ADD_PRODUCT_NAME

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("أرسل السعر:")
    return ADD_PRODUCT_PRICE

async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['price'] = float(update.message.text)
    await update.message.reply_text("أرسل المحتوى (كود/رابط):")
    return ADD_PRODUCT_CONTENT

async def add_product_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text
    conn = get_db_connection()
    conn.execute('INSERT INTO products (name, price, content) VALUES (?, ?, ?)', (context.user_data['name'], context.user_data['price'], content))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ تم الإضافة!")
    return ConversationHandler.END

async def crypto_dep_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("أرسل المبلغ بالدولار:")
    return CRYPTO_AMOUNT

async def crypto_dep_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = float(update.message.text)
    res = create_invoice(amount, update.effective_user.id)
    if res and res.get('result'):
        pay_url = res['result']['url']
        await update.message.reply_text(f"🔗 رابط الدفع: {pay_url}\nسيتم إضافة الرصيد بعد الدفع.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة", callback_data='main_menu')]]))
    else:
        await update.message.reply_text("❌ فشل إنشاء الفاتورة.")
    return ConversationHandler.END

async def manual_dep_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("أرسل ID المستخدم:")
    return MANUAL_DEPOSIT_USER

async def manual_dep_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['target'] = int(update.message.text)
    await update.message.reply_text("أرسل المبلغ:")
    return MANUAL_DEPOSIT_AMOUNT

async def manual_dep_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = float(update.message.text)
    update_user_balance(context.user_data['target'], amount)
    await update.message.reply_text("✅ تم الشحن!")
    return ConversationHandler.END

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_product_start, pattern='^add_product$')],
        states={
            ADD_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            ADD_PRODUCT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
            ADD_PRODUCT_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_content)],
        }, fallbacks=[]
    )
    
    crypto_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(crypto_dep_start, pattern='^crypto_dep$')],
        states={CRYPTO_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, crypto_dep_amount)]}, fallbacks=[]
    )

    manual_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(manual_dep_start, pattern='^manual_deposit$')],
        states={
            MANUAL_DEPOSIT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_dep_user)],
            MANUAL_DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_dep_amount)],
        }, fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(add_conv)
    app.add_handler(crypto_conv)
    app.add_handler(manual_conv)
    app.add_handler(CallbackQueryHandler(start, pattern='^main_menu$'))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel$'))
    app.add_handler(CallbackQueryHandler(view_products, pattern='^view_products$'))
    app.add_handler(CallbackQueryHandler(product_details, pattern='^prod_'))
    app.add_handler(CallbackQueryHandler(buy_product, pattern='^buy_'))
    app.add_handler(CallbackQueryHandler(deposit_menu, pattern='^deposit_menu$'))
    
    print("Bot is starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
