"""
Projects -- database helpers & schema
"""
import sqlite3
from config import DB_PATH


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT,
            display_name TEXT,
            role TEXT DEFAULT 'member',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            color TEXT DEFAULT '#95A3B3',
            owner_id TEXT,
            owner_name TEXT,
            start_date TEXT,
            deadline TEXT,
            visible_to TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            assignee_id TEXT DEFAULT '',
            assignee_name TEXT DEFAULT '',
            phase TEXT DEFAULT 'concept',
            priority TEXT DEFAULT 'medium',
            start_date TEXT,
            end_date TEXT,
            progress INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            depends_on TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            is_done INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS task_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            uploaded_by TEXT,
            uploaded_by_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            event_date TEXT NOT NULL,
            start_time TEXT DEFAULT '',
            end_time TEXT DEFAULT '',
            event_type TEXT DEFAULT 'meeting',
            color TEXT DEFAULT '#95A3B3',
            related_project_id INTEGER,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            user_id TEXT,
            user_name TEXT DEFAULT '',
            content TEXT NOT NULL,
            created_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS project_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            uploaded_by TEXT,
            uploaded_by_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            alert_type TEXT DEFAULT 'info',
            title TEXT NOT NULL,
            message TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0,
            related_task_id INTEGER,
            related_project_id INTEGER,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS meeting_minutes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            meeting_date TEXT,
            content TEXT NOT NULL,
            related_projects TEXT DEFAULT '',
            imported_by TEXT,
            imported_by_name TEXT DEFAULT '',
            status TEXT DEFAULT 'imported',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS meeting_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            change_type TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER,
            description TEXT DEFAULT '',
            old_value TEXT DEFAULT '',
            new_value TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            confirmed_by TEXT,
            confirmed_at TEXT,
            result_id INTEGER,
            FOREIGN KEY (meeting_id) REFERENCES meeting_minutes(id)
        );
    """)
    conn.commit()
    conn.close()


def run_migrations():
    # Migrate: add description column if missing
    try:
        c = get_db()
        cols = [r[1] for r in c.execute("PRAGMA table_info(task_files)").fetchall()]
        if "description" not in cols:
            c.execute("ALTER TABLE task_files ADD COLUMN description TEXT DEFAULT ''")
            c.commit()
        c.close()
    except Exception:
        pass

    # Migrate: add visible_to column to projects
    try:
        c = get_db()
        cols = [r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()]
        if "visible_to" not in cols:
            c.execute("ALTER TABLE projects ADD COLUMN visible_to TEXT DEFAULT ''")
            c.commit()
        c.close()
    except Exception:
        pass

    # Migrate: add collaborator_ids column to tasks (comma-separated user IDs)
    try:
        c = get_db()
        cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
        if "collaborator_ids" not in cols:
            c.execute("ALTER TABLE tasks ADD COLUMN collaborator_ids TEXT DEFAULT ''")
            c.commit()
        c.close()
    except Exception:
        pass

    # Migrate: add result_id column to meeting_changes (records DB id created by a confirmed change)
    try:
        c = get_db()
        cols = [r[1] for r in c.execute("PRAGMA table_info(meeting_changes)").fetchall()]
        if "result_id" not in cols:
            c.execute("ALTER TABLE meeting_changes ADD COLUMN result_id INTEGER")
            c.commit()
        c.close()
    except Exception:
        pass

    # Migrate: add completed_at column to tasks; backfill from updated_at where progress=100
    try:
        c = get_db()
        cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
        if "completed_at" not in cols:
            c.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
            c.execute("UPDATE tasks SET completed_at=updated_at WHERE progress=100 AND completed_at IS NULL")
            c.commit()
        c.close()
    except Exception:
        pass

    # Migrate: add start_time/end_time (HH:MM) to tasks for timed events
    try:
        c = get_db()
        cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
        if "start_time" not in cols:
            c.execute("ALTER TABLE tasks ADD COLUMN start_time TEXT")
        if "end_time" not in cols:
            c.execute("ALTER TABLE tasks ADD COLUMN end_time TEXT")
        c.commit()
        c.close()
    except Exception:
        pass
