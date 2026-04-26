import sqlite3

def setup_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    
    # جدول المستخدمين (الرصيد)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0.0
    )
    ''')
    
    # جدول المنتجات
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        content TEXT NOT NULL,
        stock INTEGER DEFAULT 1
    )
    ''')
    
    # جدول العمليات (تاريخ الشراء والشحن)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        type TEXT, -- 'deposit' or 'purchase'
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # جدول فواتير Cryptomus
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS invoices (
        uuid TEXT PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        status TEXT DEFAULT 'pending'
    )
    ''')
    
    conn.commit()
    conn.close()
    print("Database setup completed.")

if __name__ == "__main__":
    setup_db()
