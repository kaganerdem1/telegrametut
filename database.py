import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import DATABASE_PATH


def connect():
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    return db


@contextmanager
def transaction():
    db = connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ensure_column(db, table, column, col_type):
    cols = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def init_db():
    with transaction() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            private_started INTEGER DEFAULT 0,
            joined_at TEXT
        );

        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT
        );

        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER,
            activity_type TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            duration INTEGER NOT NULL,
            completed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS timers (
            timer_id TEXT PRIMARY KEY,
            timer_type TEXT NOT NULL,
            user_id INTEGER,
            chat_id INTEGER,
            phase TEXT NOT NULL,
            session_number INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            message_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS timer_participants (
            timer_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT,
            PRIMARY KEY(timer_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS daily_reports (
            user_id INTEGER NOT NULL,
            report_date TEXT NOT NULL,
            sent INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, report_date)
        );

        CREATE INDEX IF NOT EXISTS idx_activities_user
        ON activities(user_id, start_time);
        """)

        _ensure_column(db, "timers", "message_id", "INTEGER")
        _ensure_column(db, "timer_participants", "joined_at", "TEXT")

        db.execute("""
        UPDATE timers SET active=0
        WHERE active=1 AND (timer_type='personal' OR message_id IS NULL)
        """)


def register_user(user):
    with transaction() as db:
        db.execute("""
        INSERT INTO users (user_id, username, first_name, joined_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name
        """, (user.id, user.username, user.first_name,
              datetime.now().isoformat()))


def get_user(user_id):
    with transaction() as db:
        return db.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()


def activate_private(user_id):
    with transaction() as db:
        db.execute(
            "UPDATE users SET private_started=1 WHERE user_id=?",
            (user_id,),
        )


def register_group(chat_id, title):
    with transaction() as db:
        db.execute("""
        INSERT INTO groups (chat_id, title) VALUES (?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title
        """, (chat_id, title))


def get_groups():
    with transaction() as db:
        return db.execute("SELECT * FROM groups").fetchall()


def get_all_users():
    with transaction() as db:
        return db.execute(
            "SELECT * FROM users WHERE private_started=1"
        ).fetchall()


def add_activity(user_id, chat_id, activity_type,
                 start_time, end_time, duration, completed=0):
    with transaction() as db:
        db.execute("""
        INSERT INTO activities
        (user_id, chat_id, activity_type, start_time,
         end_time, duration, completed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, chat_id, activity_type,
              start_time, end_time, duration, completed))


def create_timer(timer_id, chat_id, phase, session_number,
                 start_time, end_time):
    with transaction() as db:
        db.execute(
            "DELETE FROM timer_participants WHERE timer_id=?",
            (timer_id,),
        )
        db.execute("""
        INSERT OR REPLACE INTO timers
        (timer_id, timer_type, user_id, chat_id, phase,
         session_number, start_time, end_time, active, message_id)
        VALUES (?, 'group', NULL, ?, ?, ?, ?, ?, 1, NULL)
        """, (timer_id, chat_id, phase, session_number,
              start_time, end_time))


def set_timer_message(timer_id, message_id):
    with transaction() as db:
        db.execute(
            "UPDATE timers SET message_id=? WHERE timer_id=?",
            (message_id, timer_id),
        )


def update_timer(timer_id, phase, session_number,
                 start_time, end_time):
    with transaction() as db:
        db.execute("""
        UPDATE timers
        SET phase=?, session_number=?, start_time=?, end_time=?
        WHERE timer_id=?
        """, (phase, session_number, start_time, end_time, timer_id))


def stop_timer(timer_id):
    with transaction() as db:
        db.execute(
            "UPDATE timers SET active=0 WHERE timer_id=?",
            (timer_id,),
        )


def get_timer(timer_id):
    with transaction() as db:
        return db.execute(
            "SELECT * FROM timers WHERE timer_id=?", (timer_id,)
        ).fetchone()


def get_active_timers():
    with transaction() as db:
        return db.execute(
            "SELECT * FROM timers WHERE active=1"
        ).fetchall()


def add_participant(timer_id, user_id, joined_at):
    with transaction() as db:
        db.execute("""
        INSERT OR IGNORE INTO timer_participants
        (timer_id, user_id, joined_at)
        VALUES (?, ?, ?)
        """, (timer_id, user_id, joined_at))


def get_participants(timer_id):
    with transaction() as db:
        return db.execute("""
        SELECT user_id, joined_at FROM timer_participants
        WHERE timer_id=?
        """, (timer_id,)).fetchall()


def get_daily_stats(user_id, day):
    with transaction() as db:
        return db.execute("""
        SELECT
            SUM(CASE WHEN activity_type='study'
                THEN duration ELSE 0 END) AS study,
            SUM(CASE WHEN activity_type='break'
                THEN duration ELSE 0 END) AS breaks,
            COUNT(CASE WHEN activity_type='study'
                AND completed=1 THEN 1 END) AS sessions
        FROM activities
        WHERE user_id=? AND substr(start_time, 1, 10)=?
        """, (user_id, day)).fetchone()


def get_group_leaderboard(chat_id, day):
    with transaction() as db:
        return db.execute("""
        SELECT u.user_id, u.first_name, SUM(a.duration) AS total
        FROM activities a
        JOIN users u ON u.user_id = a.user_id
        WHERE a.chat_id=?
          AND a.activity_type='study'
          AND substr(a.start_time, 1, 10)=?
        GROUP BY u.user_id
        ORDER BY total DESC
        LIMIT 10
        """, (chat_id, day)).fetchall()


def mark_report_sent(key_id, day):
    with transaction() as db:
        db.execute("""
        INSERT OR REPLACE INTO daily_reports
        (user_id, report_date, sent) VALUES (?, ?, 1)
        """, (key_id, day))


def report_was_sent(key_id, day):
    with transaction() as db:
        row = db.execute("""
        SELECT sent FROM daily_reports
        WHERE user_id=? AND report_date=?
        """, (key_id, day)).fetchone()
        return bool(row and row["sent"])