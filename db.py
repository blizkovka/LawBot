import sqlite3



def init_db():
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        user_id INTEGER,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp DATETIME,
        PRIMARY KEY (user_id, timestamp)
    )
    ''')

    conn.commit()
    conn.close()


