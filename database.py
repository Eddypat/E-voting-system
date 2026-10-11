"""
database.py
E-Voting System for Student Elections - Captain Elechi Amadi Polytechnic
--------------------------------------------------------------------------
Handles all SQLite database connections, schema creation, and seeding.
"""

import sqlite3
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "evoting.db")


def get_db_connection():
    """Return a SQLite connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    """Simple salted SHA-256 hash used for admin password storage."""
    salt = "ceap_evoting_salt"
    return hashlib.sha256((salt + password).encode()).hexdigest()


def init_db(reset: bool = False, seed_samples: bool = True):
    """Create all tables. If reset=True, drop existing tables first.

    seed_samples controls whether the built-in demo students/candidates are
    inserted. Set seed_samples=False when the caller (e.g. load_data.py) is
    about to load its own voter/candidate list from data.yaml, so the two
    sources of data are never mixed in the same database.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    if reset:
        cur.executescript(
            """
            DROP TABLE IF EXISTS votes;
            DROP TABLE IF EXISTS candidates;
            DROP TABLE IF EXISTS students;
            DROP TABLE IF EXISTS election_settings;
            DROP TABLE IF EXISTS admins;
            DROP TABLE IF EXISTS audit_log;
            """
        )

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            student_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            matric_no    TEXT UNIQUE NOT NULL,
            full_name    TEXT NOT NULL,
            email        TEXT UNIQUE NOT NULL,
            department   TEXT NOT NULL,
            has_voted    INTEGER DEFAULT 0,
            otp_code     TEXT,
            otp_expiry   TEXT,
            otp_attempts INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matric_no    TEXT NOT NULL,
            full_name    TEXT NOT NULL,
            position     TEXT NOT NULL,
            department   TEXT NOT NULL,
            photo        TEXT,
            manifesto    TEXT
        );

        CREATE TABLE IF NOT EXISTS votes (
            vote_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            voter_token  TEXT NOT NULL,
            candidate_id INTEGER NOT NULL,
            position     TEXT NOT NULL,
            timestamp    TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id)
        );

        CREATE TABLE IF NOT EXISTS election_settings (
            setting_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            election_name  TEXT NOT NULL,
            is_active      INTEGER DEFAULT 0,
            start_time     TEXT,
            end_time       TEXT
        );

        CREATE TABLE IF NOT EXISTS admins (
            admin_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username       TEXT UNIQUE NOT NULL,
            password_hash  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            description TEXT,
            timestamp   TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    # Upgrade databases created before otp_attempts existed.
    cols = [r[1] for r in cur.execute("PRAGMA table_info(students)").fetchall()]
    if "otp_attempts" not in cols:
        cur.execute("ALTER TABLE students ADD COLUMN otp_attempts INTEGER DEFAULT 0")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM admins")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
            ("admin", hash_password(os.environ.get("ADMIN_PASSWORD", "admin123"))),
        )

    cur.execute("SELECT COUNT(*) FROM election_settings")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO election_settings (election_name, is_active) VALUES (?, ?)",
            ("2025/2026 SUG Presidential & Officer Election", 1),
        )

    cur.execute("SELECT COUNT(*) FROM students")
    if seed_samples and cur.fetchone()[0] == 0:
        sample_students = [
            ("CEAP/N-COM/2024/3226", "Nwaobasi Mercy Chinenye", "mercy.n@ceap.edu.ng", "Computer Science"),
            ("CEAP/N-COM/2024/3101", "Chidi Okafor", "chidi.o@ceap.edu.ng", "Computer Science"),
            ("CEAP/N-ACC/2024/2210", "Blessing Eze", "blessing.e@ceap.edu.ng", "Accountancy"),
            ("CEAP/N-MKT/2024/1187", "Samuel Ibe", "samuel.i@ceap.edu.ng", "Marketing"),
            ("CEAP/N-COM/2023/2987", "Faith Amadi", "faith.a@ceap.edu.ng", "Computer Science"),
        ]
        cur.executemany(
            "INSERT INTO students (matric_no, full_name, email, department) VALUES (?, ?, ?, ?)",
            sample_students,
        )

    cur.execute("SELECT COUNT(*) FROM candidates")
    if seed_samples and cur.fetchone()[0] == 0:
        sample_candidates = [
            ("CEAP/N-COM/2023/1002", "Emeka Johnson", "President", "Computer Science", None,
             "Committed to improved welfare, digital ID cards and a functioning students' clinic."),
            ("CEAP/N-ACC/2023/1450", "Grace Peterside", "President", "Accountancy", None,
             "Advocate for transparent SUG budgeting and expanded shuttle services."),
            ("CEAP/N-MSC/2023/0876", "David Wokoma", "Vice President", "Mass Communication", None,
             "Focused on sports development and inter-departmental unity."),
            ("CEAP/N-COM/2023/1290", "Miracle Sotonye", "Vice President", "Computer Science", None,
             "Champion of ICT infrastructure upgrades across campus."),
            ("CEAP/N-BAN/2023/0654", "Victory Nwachukwu", "Financial Secretary", "Banking & Finance", None,
             "Pledges monthly public financial statements for the union."),
        ]
        cur.executemany(
            """INSERT INTO candidates (matric_no, full_name, position, department, photo, manifesto)
               VALUES (?, ?, ?, ?, ?, ?)""",
            sample_candidates,
        )

    conn.commit()
    conn.close()


def sync_admin_password():
    """Keep the 'admin' account's password equal to the ADMIN_PASSWORD
    environment variable, every time the app starts.

    Without this, the password is only set when the database is first built,
    so changing ADMIN_PASSWORD later (e.g. in Render) would have no effect
    until the next full rebuild. Does nothing if ADMIN_PASSWORD is not set.
    """
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        return
    new_hash = hash_password(password)
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT password_hash FROM admins WHERE username = 'admin'").fetchone()
        if row is None:
            conn.execute("INSERT INTO admins (username, password_hash) VALUES ('admin', ?)", (new_hash,))
        elif row["password_hash"] != new_hash:
            conn.execute("UPDATE admins SET password_hash = ? WHERE username = 'admin'", (new_hash,))
        conn.commit()
    except sqlite3.OperationalError:
        pass  # tables not created yet; init_db() will seed using ADMIN_PASSWORD
    finally:
        conn.close()


def log_event(event_type: str, description: str = ""):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO audit_log (event_type, description) VALUES (?, ?)",
        (event_type, description),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db(reset=True)
    print("Database initialised at", DB_PATH)
