"""
数据库操作模块
支持本地 SQLite 和 Turso 云数据库双模式。
"""

import os
from datetime import datetime

# 本地 SQLite 路径（Turso 未配置时使用）
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "exam.db")

# Turso 配置（从环境变量读取，Streamlit Cloud 通过 secrets 设置）
TURSO_URL = os.environ.get("TURSO_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")


def _get_sqlite_conn():
    """获取本地 SQLite 连接"""
    import sqlite3
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _get_turso_conn():
    """获取 Turso 云数据库连接"""
    import turso_adapter
    conn = turso_adapter.TursoConnection(TURSO_URL, TURSO_TOKEN)
    conn.row_factory = turso_adapter.TursoRow
    return conn


def get_conn():
    """获取数据库连接（自动选择 Turso 或本地 SQLite）"""
    if TURSO_URL and TURSO_TOKEN:
        return _get_turso_conn()
    return _get_sqlite_conn()


def init_db():
    """初始化数据库，创建所有表（如果不存在）"""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS question_banks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            level TEXT NOT NULL,
            year TEXT NOT NULL,
            uploader_id INTEGER,
            campus_id INTEGER,
            created_at TEXT NOT NULL,
            delete_requested INTEGER DEFAULT 0,
            UNIQUE(level, year),
            FOREIGN KEY (uploader_id) REFERENCES users(id),
            FOREIGN KEY (campus_id) REFERENCES campuses(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_id INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            qtype TEXT NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT DEFAULT '',
            option_b TEXT DEFAULT '',
            option_c TEXT DEFAULT '',
            option_d TEXT DEFAULT '',
            answer TEXT NOT NULL,
            explanation TEXT DEFAULT '',
            FOREIGN KEY (bank_id) REFERENCES question_banks(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            display_name TEXT NOT NULL,
            campus_id INTEGER,
            agreed_terms_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (campus_id) REFERENCES campuses(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exam_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bank_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            submitted_at TEXT,
            score INTEGER,
            total INTEGER NOT NULL,
            time_sec INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (bank_id) REFERENCES question_banks(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            given_answer TEXT,
            is_correct INTEGER DEFAULT 0,
            phase TEXT DEFAULT 'first',
            review_answer TEXT,
            error_reason TEXT,
            FOREIGN KEY (attempt_id) REFERENCES exam_attempts(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions(id)
        )
    """)

    # ---- 数据库迁移：兼容旧版本 ----
    # 检查 answers 表是否有新列
    cols_a = [c[1] for c in cursor.execute("PRAGMA table_info(answers)").fetchall()]
    if 'phase' not in cols_a:
        cursor.execute("ALTER TABLE answers ADD COLUMN phase TEXT DEFAULT 'first'")
    if 'review_answer' not in cols_a:
        cursor.execute("ALTER TABLE answers ADD COLUMN review_answer TEXT")
    if 'error_reason' not in cols_a:
        cursor.execute("ALTER TABLE answers ADD COLUMN error_reason TEXT")

    # 检查 users 表是否有 campus_id 列
    cols = [c[1] for c in cursor.execute("PRAGMA table_info(users)").fetchall()]
    if 'campus_id' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN campus_id INTEGER REFERENCES campuses(id)")
    if 'agreed_terms_at' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN agreed_terms_at TEXT")
    # 检查 exam_attempts 表是否有 user_id 列
    cols2 = [c[1] for c in cursor.execute("PRAGMA table_info(exam_attempts)").fetchall()]
    if 'user_id' not in cols2:
        cursor.execute("ALTER TABLE exam_attempts ADD COLUMN user_id INTEGER REFERENCES users(id)")

    # 检查 question_banks 是否有新列
    cols3 = [c[1] for c in cursor.execute("PRAGMA table_info(question_banks)").fetchall()]
    if 'uploader_id' not in cols3:
        cursor.execute("ALTER TABLE question_banks ADD COLUMN uploader_id INTEGER REFERENCES users(id)")
    if 'campus_id' not in cols3:
        cursor.execute("ALTER TABLE question_banks ADD COLUMN campus_id INTEGER REFERENCES campuses(id)")
    if 'delete_requested' not in cols3:
        cursor.execute("ALTER TABLE question_banks ADD COLUMN delete_requested INTEGER DEFAULT 0")
    if 'duration_minutes' not in cols3:
        cursor.execute("ALTER TABLE question_banks ADD COLUMN duration_minutes INTEGER DEFAULT 60")
    if 'allow_practice_mode' not in cols3:
        cursor.execute("ALTER TABLE question_banks ADD COLUMN allow_practice_mode INTEGER DEFAULT 0")
    if 'allow_random_order' not in cols3:
        cursor.execute("ALTER TABLE question_banks ADD COLUMN allow_random_order INTEGER DEFAULT 0")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            campus_id INTEGER,
            filename TEXT NOT NULL,
            file_size INTEGER,
            question_count INTEGER,
            bank_name TEXT,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            target TEXT,
            detail TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# ==================== 上传日志 ====================

def create_upload_log(user_id, campus_id, filename, file_size, question_count, bank_name):
    """记录上传日志"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO upload_logs (user_id, campus_id, filename, file_size, question_count, bank_name, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, campus_id, filename, file_size, question_count, bank_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def get_upload_logs(campus_id=None, limit=None, offset=0):
    """获取上传日志（超管可看全部，校区管理员只看本校）。支持分页。"""
    conn = get_conn()
    params = []
    if campus_id:
        sql = """SELECT ul.*, u.display_name as uploader_name, u.username
               FROM upload_logs ul
               JOIN users u ON ul.user_id = u.id
               WHERE ul.campus_id = ?
               ORDER BY ul.uploaded_at DESC"""
        params = [campus_id]
    else:
        sql = """SELECT ul.*, u.display_name as uploader_name, u.username, c.name as campus_name
               FROM upload_logs ul
               JOIN users u ON ul.user_id = u.id
               LEFT JOIN campuses c ON ul.campus_id = c.id
               ORDER BY ul.uploaded_at DESC"""
        params = []
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_upload_logs_count(campus_id=None):
    """获取上传日志总数（用于分页）"""
    conn = get_conn()
    if campus_id:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM upload_logs WHERE campus_id = ?", (campus_id,)
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) as cnt FROM upload_logs").fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0


# ==================== 操作日志 ====================

def create_operation_log(user_id, username, action, target="", detail=""):
    """记录管理操作日志"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO operation_logs (user_id, username, action, target, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, action, target, detail, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def get_operation_logs(limit=None, offset=0):
    """获取操作日志（仅超管可见），支持分页"""
    conn = get_conn()
    sql = "SELECT * FROM operation_logs ORDER BY created_at DESC"
    params = []
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [limit, offset]
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_operation_logs_count():
    """获取操作日志总数"""
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM operation_logs").fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0


# ==================== 用户操作 ====================

def create_user(username, password_hash, salt, role, display_name, campus_id=None, agreed_terms_at=None):
    """创建用户，返回 user_id"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password_hash, salt, role, display_name, campus_id, agreed_terms_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (username, password_hash, salt, role, display_name, campus_id, agreed_terms_at, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    uid = cursor.lastrowid
    conn.close()
    return uid


def get_user_by_username(username):
    """根据用户名查找用户"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def reset_user_password(username, password_hash, salt):
    """重置用户密码"""
    conn = get_conn()
    conn.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
        (password_hash, salt, username)
    )
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def get_user_by_id(user_id):
    """根据 ID 查找用户"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ==================== 校区操作 ====================

def create_campus(name):
    """创建校区"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO campuses (name, created_at) VALUES (?, ?)",
            (name.strip(), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        cid = cursor.lastrowid
        conn.close()
        return cid
    except sqlite3.IntegrityError:
        conn.close()
        return None


def get_all_campuses():
    """获取所有校区"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM campuses ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_campus_by_id(campus_id):
    """获取单个校区"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM campuses WHERE id = ?", (campus_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_campus(campus_id):
    """删除校区及其下的所有用户（管理员和学生）"""
    conn = get_conn()
    # 删除该校区用户的考试记录和答案
    conn.execute("""
        DELETE FROM answers WHERE attempt_id IN (
            SELECT id FROM exam_attempts WHERE user_id IN (
                SELECT id FROM users WHERE campus_id = ?
            )
        )
    """, (campus_id,))
    conn.execute("DELETE FROM exam_attempts WHERE user_id IN (SELECT id FROM users WHERE campus_id = ?)", (campus_id,))
    conn.execute("DELETE FROM users WHERE campus_id = ?", (campus_id,))
    conn.execute("DELETE FROM campuses WHERE id = ?", (campus_id,))
    conn.commit()
    conn.close()


def get_all_students(campus_id=None, limit=None, offset=0, search=None):
    """获取学生用户。campus_id=None 返回全部。
    支持分页(limit/offset)和模糊搜索(search)。"""
    conn = get_conn()
    conditions = ["role = 'student'"]
    params = []
    if campus_id:
        conditions.append("campus_id = ?")
        params.append(campus_id)
    if search:
        conditions.append("(display_name LIKE ? OR username LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)
    sql = f"SELECT * FROM users WHERE {where} ORDER BY created_at DESC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_students_count(campus_id=None, search=None):
    """获取学生总数（用于分页）"""
    conn = get_conn()
    conditions = ["role = 'student'"]
    params = []
    if campus_id:
        conditions.append("campus_id = ?")
        params.append(campus_id)
    if search:
        conditions.append("(display_name LIKE ? OR username LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = " AND ".join(conditions)
    row = conn.execute(f"SELECT COUNT(*) as cnt FROM users WHERE {where}", params).fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0


def get_all_users(campus_id=None):
    """获取所有用户，可按校区过滤"""
    conn = get_conn()
    if campus_id:
        rows = conn.execute(
            "SELECT * FROM users WHERE campus_id = ? ORDER BY role, created_at DESC",
            (campus_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY role, created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 题库操作 ====================

def create_bank(name, level, year, uploader_id=None, campus_id=None, duration_minutes=60,
                 allow_practice_mode=0, allow_random_order=0):
    """创建题库，返回 bank_id。如果已存在同 level+year 的题库则返回 None"""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO question_banks (name, level, year, uploader_id, campus_id, duration_minutes, allow_practice_mode, allow_random_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, level, year, uploader_id, campus_id, duration_minutes, allow_practice_mode, allow_random_order, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_bank_by_level_year(level, year):
    """根据级别和年份查找题库"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM question_banks WHERE level = ? AND year = ?",
        (level, year)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_bank_by_id(bank_id):
    """根据 ID 查找题库"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM question_banks WHERE id = ?", (bank_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_levels(campus_id=None):
    """获取所有级别列表，可按校区过滤"""
    conn = get_conn()
    if campus_id:
        rows = conn.execute(
            "SELECT DISTINCT level FROM question_banks WHERE campus_id = ? AND delete_requested < 2 ORDER BY level",
            (campus_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT level FROM question_banks WHERE delete_requested < 2 ORDER BY level"
        ).fetchall()
    conn.close()
    return [r["level"] for r in rows]


def get_years_for_level(level, campus_id=None):
    """获取某个级别下的年份，可按校区过滤"""
    conn = get_conn()
    if campus_id:
        rows = conn.execute(
            "SELECT DISTINCT year FROM question_banks WHERE level = ? AND campus_id = ? AND delete_requested < 2 ORDER BY year DESC",
            (level, campus_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT year FROM question_banks WHERE level = ? AND delete_requested < 2 ORDER BY year DESC",
            (level,)
        ).fetchall()
    conn.close()
    return [r["year"] for r in rows]


def get_all_years():
    """获取所有不重复的年份列表"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT year FROM question_banks ORDER BY year DESC"
    ).fetchall()
    conn.close()
    return [r["year"] for r in rows]


def delete_bank(bank_id):
    """删除题库及其所有关联数据（题目、考试记录、答案）"""
    conn = get_conn()
    # 手动按顺序删除（兼容 SQLite 未启用 CASCADE 的情况）
    # 1. 删除该题库所有考试记录的答案
    conn.execute("""
        DELETE FROM answers WHERE attempt_id IN (
            SELECT id FROM exam_attempts WHERE bank_id = ?
        )
    """, (bank_id,))
    # 2. 删除该题库的考试记录
    conn.execute("DELETE FROM exam_attempts WHERE bank_id = ?", (bank_id,))
    # 3. 删除题目（CASCADE 通常处理，手动也删一次）
    conn.execute("DELETE FROM questions WHERE bank_id = ?", (bank_id,))
    # 4. 删除题库
    conn.execute("DELETE FROM question_banks WHERE id = ?", (bank_id,))
    conn.commit()
    conn.close()


def replace_bank(bank_id, name, level, year, uploader_id=None, campus_id=None, duration_minutes=60,
                  allow_practice_mode=0, allow_random_order=0):
    """替换题库：删除旧题目数据，更新基本信息"""
    conn = get_conn()
    conn.execute("DELETE FROM questions WHERE bank_id = ?", (bank_id,))
    conn.execute(
        "UPDATE question_banks SET name=?, level=?, year=?, uploader_id=?, campus_id=?, duration_minutes=?, allow_practice_mode=?, allow_random_order=?, created_at=?, delete_requested=0 WHERE id=?",
        (name, level, year, uploader_id, campus_id, duration_minutes, allow_practice_mode, allow_random_order, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bank_id)
    )
    conn.commit()
    conn.close()
    return bank_id


def request_delete_bank(bank_id):
    """校区管理员申请删除题库"""
    conn = get_conn()
    conn.execute("UPDATE question_banks SET delete_requested = 1 WHERE id = ?", (bank_id,))
    conn.commit()
    conn.close()


def approve_delete_bank(bank_id):
    """超级管理员确认删除题库"""
    delete_bank(bank_id)


def reject_delete_bank(bank_id):
    """超级管理员拒绝删除申请"""
    conn = get_conn()
    conn.execute("UPDATE question_banks SET delete_requested = 0 WHERE id = ?", (bank_id,))
    conn.commit()
    conn.close()


def get_delete_requests():
    """获取待审批的删除申请"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT qb.*, u.display_name as uploader_name, c.name as campus_name
           FROM question_banks qb
           LEFT JOIN users u ON qb.uploader_id = u.id
           LEFT JOIN campuses c ON qb.campus_id = c.id
           WHERE qb.delete_requested = 1
           ORDER BY qb.created_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_banks(campus_id=None):
    """获取题库列表，可按校区过滤。campus_id=None 返回全部（仅超管）"""
    conn = get_conn()
    if campus_id:
        rows = conn.execute(
            """SELECT qb.*, u.display_name as uploader_name, c.name as campus_name
               FROM question_banks qb
               LEFT JOIN users u ON qb.uploader_id = u.id
               LEFT JOIN campuses c ON qb.campus_id = c.id
               WHERE qb.delete_requested < 2 AND qb.campus_id = ?
               ORDER BY qb.level, qb.year DESC""",
            (campus_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT qb.*, u.display_name as uploader_name, c.name as campus_name
               FROM question_banks qb
               LEFT JOIN users u ON qb.uploader_id = u.id
               LEFT JOIN campuses c ON qb.campus_id = c.id
               WHERE qb.delete_requested < 2
               ORDER BY qb.level, qb.year DESC"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 题目操作 ====================

def insert_question(bank_id, seq, qtype, question, option_a, option_b,
                    option_c, option_d, answer, explanation):
    """插入一道题目"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO questions
           (bank_id, seq, qtype, question, option_a, option_b, option_c, option_d, answer, explanation)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (bank_id, seq, qtype, question, option_a or "", option_b or "",
         option_c or "", option_d or "", answer, explanation or "")
    )
    conn.commit()
    conn.close()
    return cursor.lastrowid


def insert_questions_batch(bank_id, questions_list):
    """批量插入题目。questions_list 每个元素是 (seq, qtype, question, option_a, option_b, option_c, option_d, answer, explanation)"""
    conn = get_conn()
    conn.executemany(
        """INSERT INTO questions
           (bank_id, seq, qtype, question, option_a, option_b, option_c, option_d, answer, explanation)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(bank_id, *q) for q in questions_list]
    )
    conn.commit()
    conn.close()


def update_question(question_id, **fields):
    """更新单道题目。fields 可包含 question, option_a, option_b, option_c, option_d, answer, explanation。"""
    allowed = ['question', 'option_a', 'option_b', 'option_c', 'option_d', 'answer', 'explanation']
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ', '.join([f"{k} = ?" for k in updates])
    values = list(updates.values()) + [question_id]
    conn = get_conn()
    conn.execute(f"UPDATE questions SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_questions(bank_id):
    """获取某个题库的所有题目，按序号排序"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM questions WHERE bank_id = ? ORDER BY seq",
        (bank_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_question_count(bank_id):
    """获取题库的题目数量"""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM questions WHERE bank_id = ?", (bank_id,)
    ).fetchone()
    conn.close()
    return row["cnt"]


# ==================== 考试记录操作 ====================

def create_attempt(user_id, bank_id, total):
    """创建一次考试记录，返回 attempt_id"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO exam_attempts (user_id, bank_id, started_at, total) VALUES (?, ?, ?, ?)",
        (user_id, bank_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total)
    )
    conn.commit()
    attempt_id = cursor.lastrowid
    conn.close()
    return attempt_id


def submit_attempt(attempt_id, score, time_sec):
    """提交考试：记录提交时间、分数和耗时"""
    conn = get_conn()
    conn.execute(
        """UPDATE exam_attempts
           SET submitted_at = ?, score = ?, time_sec = ?
           WHERE id = ?""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), score, time_sec, attempt_id)
    )
    conn.commit()
    conn.close()


def get_unsubmitted_attempt(user_id):
    """获取某用户未提交的考试"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM exam_attempts WHERE user_id = ? AND submitted_at IS NULL ORDER BY id DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def abandon_attempt(attempt_id):
    """放弃未提交的考试"""
    conn = get_conn()
    conn.execute("DELETE FROM exam_attempts WHERE id = ?", (attempt_id,))
    conn.commit()
    conn.close()


def get_attempts(user_id=None, campus_id=None, limit=None, offset=0):
    """获取考试记录。支持按用户或校区过滤，支持分页。"""
    conn = get_conn()
    params = []
    if user_id:
        sql = """SELECT ea.*, qb.name as bank_name, qb.level, qb.year
               FROM exam_attempts ea
               JOIN question_banks qb ON ea.bank_id = qb.id
               WHERE ea.submitted_at IS NOT NULL AND ea.user_id = ?
               ORDER BY ea.submitted_at DESC"""
        params = [user_id]
    elif campus_id:
        sql = """SELECT ea.*, qb.name as bank_name, qb.level, qb.year, u.display_name as user_name
               FROM exam_attempts ea
               JOIN question_banks qb ON ea.bank_id = qb.id
               JOIN users u ON ea.user_id = u.id
               WHERE ea.submitted_at IS NOT NULL AND u.campus_id = ?
               ORDER BY ea.submitted_at DESC"""
        params = [campus_id]
    else:
        sql = """SELECT ea.*, qb.name as bank_name, qb.level, qb.year, u.display_name as user_name
               FROM exam_attempts ea
               JOIN question_banks qb ON ea.bank_id = qb.id
               JOIN users u ON ea.user_id = u.id
               WHERE ea.submitted_at IS NOT NULL
               ORDER BY ea.submitted_at DESC"""
        params = []
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_attempts_count(user_id=None, campus_id=None):
    """获取考试记录总数（用于分页）"""
    conn = get_conn()
    if user_id:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM exam_attempts WHERE submitted_at IS NOT NULL AND user_id = ?",
            (user_id,)
        ).fetchone()
    elif campus_id:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM exam_attempts ea
               JOIN users u ON ea.user_id = u.id
               WHERE ea.submitted_at IS NOT NULL AND u.campus_id = ?""",
            (campus_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM exam_attempts WHERE submitted_at IS NOT NULL"
        ).fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0


def get_attempt_review_stats(attempt_id):
    """获取单次考试的订正统计。
    返回 {total_answers, wrong_count, corrected_count, uncorrected_count,
          original_score, current_score, error_reasons: [{reason, cnt}]}"""
    conn = get_conn()

    # 基本统计：从 answers JOIN questions 聚合
    row = conn.execute("""
        SELECT
            COUNT(*) as total_answers,
            COUNT(CASE WHEN q.qtype != '编程' AND (a.phase = 'review' OR (a.phase = 'first' AND a.is_correct = 0)) THEN 1 END) as wrong_count,
            COUNT(CASE WHEN a.phase = 'review' AND a.is_correct = 1 AND q.qtype != '编程' THEN 1 END) as corrected_count,
            COUNT(CASE WHEN a.is_correct = 0 AND q.qtype != '编程' THEN 1 END) as uncorrected_count,
            COUNT(CASE WHEN a.phase = 'first' AND a.is_correct = 1 AND q.qtype != '编程' THEN 1 END) as original_score
        FROM answers a
        JOIN questions q ON a.question_id = q.id
        WHERE a.attempt_id = ?
    """, (attempt_id,)).fetchone()

    if not row:
        conn.close()
        return None

    # 当前得分从 exam_attempts 读取
    current = conn.execute(
        "SELECT score FROM exam_attempts WHERE id = ?", (attempt_id,)
    ).fetchone()
    current_score = int(current["score"]) if current and current["score"] is not None else 0

    # 错因分布
    reasons = conn.execute("""
        SELECT a.error_reason, COUNT(*) as cnt
        FROM answers a
        JOIN questions q ON a.question_id = q.id
        WHERE a.attempt_id = ? AND a.error_reason IS NOT NULL AND a.error_reason != ''
        GROUP BY a.error_reason
        ORDER BY cnt DESC
    """, (attempt_id,)).fetchall()

    conn.close()
    return {
        "total_answers": int(row["total_answers"]) if row["total_answers"] else 0,
        "wrong_count": int(row["wrong_count"] or 0),
        "corrected_count": int(row["corrected_count"] or 0),
        "uncorrected_count": int(row["uncorrected_count"] or 0),
        "original_score": int(row["original_score"] or 0),
        "current_score": current_score,
        "error_reasons": [{"reason": r["error_reason"], "cnt": int(r["cnt"])} for r in reasons],
    }


def get_attempts_with_review_stats(user_id, limit=None, offset=0):
    """批量获取用户的考试记录及订正统计（避免 N+1 查询）。
    返回每条 attempt 包含 wrong_count / corrected_count / uncorrected_count / original_score。"""
    conn = get_conn()
    sql = """SELECT ea.*, qb.name as bank_name, qb.level, qb.year,
                    COUNT(CASE WHEN q.qtype != '编程' AND (a.phase = 'review' OR (a.phase = 'first' AND a.is_correct = 0)) THEN 1 END) as wrong_count,
                    COUNT(CASE WHEN a.phase = 'review' AND a.is_correct = 1 AND q.qtype != '编程' THEN 1 END) as corrected_count,
                    SUM(CASE WHEN a.is_correct = 0 AND q.qtype != '编程' THEN 1 ELSE 0 END) as uncorrected_count,
                    COUNT(CASE WHEN a.phase = 'first' AND a.is_correct = 1 AND q.qtype != '编程' THEN 1 END) as original_score
             FROM exam_attempts ea
             JOIN question_banks qb ON ea.bank_id = qb.id
             LEFT JOIN answers a ON a.attempt_id = ea.id
             LEFT JOIN questions q ON a.question_id = q.id
             WHERE ea.user_id = ? AND ea.submitted_at IS NOT NULL
             GROUP BY ea.id
             ORDER BY ea.submitted_at DESC"""
    params = [user_id]
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_wrong_questions(user_id, limit=None, offset=0):
    """获取某用户的错题列表（含订正状态）。支持分页。
    返回每道题的最新状态：曾做错过的题目，包含是否已订正正确的标记。"""
    conn = get_conn()
    sql = """SELECT q.*, a.given_answer, a.is_correct, a.error_reason, a.phase, a.review_answer,
                    ea.submitted_at, ea.id as attempt_id,
                    CASE WHEN a.phase = 'review' AND a.is_correct = 1 THEN 1 ELSE 0 END as was_corrected
             FROM answers a
             JOIN questions q ON a.question_id = q.id
             JOIN exam_attempts ea ON a.attempt_id = ea.id
             WHERE a.id IN (
                 SELECT MAX(a2.id) FROM answers a2
                 JOIN exam_attempts ea2 ON a2.attempt_id = ea2.id
                 WHERE ea2.user_id = ?
                 GROUP BY a2.question_id
             )
             AND q.id IN (
                 SELECT DISTINCT a3.question_id FROM answers a3
                 JOIN exam_attempts ea3 ON a3.attempt_id = ea3.id
                 WHERE ea3.user_id = ? AND a3.is_correct = 0
             )
             ORDER BY ea.submitted_at DESC"""
    params = [user_id, user_id]
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_wrong_questions_count(user_id):
    """获取错题总数（用户曾做错过的所有题目，去重）"""
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(DISTINCT a.question_id) as cnt
           FROM answers a
           JOIN exam_attempts ea ON a.attempt_id = ea.id
           WHERE ea.user_id = ? AND a.is_correct = 0""",
        (user_id,)
    ).fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0


def get_error_reason_stats(campus_id=None):
    """获取错因统计"""
    conn = get_conn()
    if campus_id:
        rows = conn.execute(
            """SELECT a.error_reason, COUNT(*) as cnt
               FROM answers a
               JOIN exam_attempts ea ON a.attempt_id = ea.id
               JOIN users u ON ea.user_id = u.id
               WHERE a.error_reason IS NOT NULL AND a.error_reason != '' AND u.campus_id = ?
               GROUP BY a.error_reason
               ORDER BY cnt DESC""",
            (campus_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT a.error_reason, COUNT(*) as cnt
               FROM answers a
               WHERE a.error_reason IS NOT NULL AND a.error_reason != ''
               GROUP BY a.error_reason
               ORDER BY cnt DESC"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_admin_stats(campus_id=None):
    """获取管理员仪表盘统计数据，可按校区过滤"""
    conn = get_conn()

    if campus_id:
        r = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'student' AND campus_id = ?", (campus_id,)).fetchone()
        total_students = int(r['cnt'] or 0) if r else 0
        r = conn.execute("""SELECT COUNT(*) as cnt FROM exam_attempts ea
               JOIN users u ON ea.user_id = u.id
               WHERE ea.submitted_at IS NOT NULL AND u.campus_id = ?""", (campus_id,)).fetchone()
        total_exams = int(r['cnt'] or 0) if r else 0
        r = conn.execute("""SELECT AVG(CAST(ea.score AS FLOAT)/ea.total*100) as avg_pct
               FROM exam_attempts ea JOIN users u ON ea.user_id = u.id
               WHERE ea.submitted_at IS NOT NULL AND u.campus_id = ?""", (campus_id,)).fetchone()
        avg_score = round(float(r['avg_pct']), 1) if r and r['avg_pct'] else 0
        student_stats = conn.execute(
            """SELECT u.id, u.display_name, u.username,
                      COUNT(ea.id) as exam_count,
                      AVG(CAST(ea.score AS FLOAT)/ea.total*100) as avg_score,
                      MAX(ea.submitted_at) as last_exam
               FROM users u
               LEFT JOIN exam_attempts ea ON u.id = ea.user_id AND ea.submitted_at IS NOT NULL
               WHERE u.role = 'student' AND u.campus_id = ?
               GROUP BY u.id
               ORDER BY exam_count DESC""",
            (campus_id,)
        ).fetchall()
        exam_stats = conn.execute(
            """SELECT qb.name as bank_name, qb.level, qb.year,
                      COUNT(ea.id) as attempt_count,
                      AVG(CAST(ea.score AS FLOAT)/ea.total*100) as avg_score,
                      MAX(ea.score*1.0/ea.total*100) as best_score,
                      MIN(ea.score*1.0/ea.total*100) as worst_score
               FROM exam_attempts ea
               JOIN question_banks qb ON ea.bank_id = qb.id
               JOIN users u ON ea.user_id = u.id
               WHERE ea.submitted_at IS NOT NULL AND u.campus_id = ?
               GROUP BY qb.id
               ORDER BY qb.level, qb.year DESC""",
            (campus_id,)
        ).fetchall()
    else:
        r = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'student'").fetchone()
        total_students = int(r['cnt'] or 0) if r else 0
        r = conn.execute("SELECT COUNT(*) as cnt FROM exam_attempts WHERE submitted_at IS NOT NULL").fetchone()
        total_exams = int(r['cnt'] or 0) if r else 0
        r = conn.execute("SELECT AVG(CAST(score AS FLOAT)/total*100) as avg_pct FROM exam_attempts WHERE submitted_at IS NOT NULL").fetchone()
        avg_score = round(float(r['avg_pct']), 1) if r and r['avg_pct'] else 0
        student_stats = conn.execute(
            """SELECT u.id, u.display_name, u.username,
                      COUNT(ea.id) as exam_count,
                      AVG(CAST(ea.score AS FLOAT)/ea.total*100) as avg_score,
                      MAX(ea.submitted_at) as last_exam
               FROM users u
               LEFT JOIN exam_attempts ea ON u.id = ea.user_id AND ea.submitted_at IS NOT NULL
               WHERE u.role = 'student'
               GROUP BY u.id
               ORDER BY exam_count DESC"""
        ).fetchall()
        exam_stats = conn.execute(
            """SELECT qb.name as bank_name, qb.level, qb.year,
                      COUNT(ea.id) as attempt_count,
                      AVG(CAST(ea.score AS FLOAT)/ea.total*100) as avg_score,
                      MAX(ea.score*1.0/ea.total*100) as best_score,
                      MIN(ea.score*1.0/ea.total*100) as worst_score
               FROM exam_attempts ea
               JOIN question_banks qb ON ea.bank_id = qb.id
               WHERE ea.submitted_at IS NOT NULL
               GROUP BY qb.id
               ORDER BY qb.level, qb.year DESC"""
        ).fetchall()

    conn.close()
    return {
        'total_students': total_students,
        'total_exams': total_exams,
        'avg_score': avg_score,
        'student_stats': [dict(r) for r in student_stats],
        'exam_stats': [dict(r) for r in exam_stats],
    }


def get_student_detail(student_id):
    """获取某个学生的详细考试记录"""
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (student_id,)).fetchone()
    attempts = conn.execute(
        """SELECT ea.*, qb.name as bank_name, qb.level, qb.year
           FROM exam_attempts ea
           JOIN question_banks qb ON ea.bank_id = qb.id
           WHERE ea.user_id = ? AND ea.submitted_at IS NOT NULL
           ORDER BY ea.submitted_at DESC""",
        (student_id,)
    ).fetchall()
    conn.close()
    return {
        'user': dict(user) if user else None,
        'attempts': [dict(a) for a in attempts],
    }


def get_attempt_detail(attempt_id):
    """获取某次考试的详细信息（含所有答案）"""
    conn = get_conn()
    attempt = conn.execute(
        """SELECT ea.*, qb.name as bank_name, qb.level, qb.year
           FROM exam_attempts ea
           JOIN question_banks qb ON ea.bank_id = qb.id
           WHERE ea.id = ?""",
        (attempt_id,)
    ).fetchone()
    if not attempt:
        conn.close()
        return None

    answers_rows = conn.execute(
        """SELECT a.*, q.seq, q.qtype, q.question, q.option_a, q.option_b,
                  q.option_c, q.option_d, q.answer, q.explanation, a.phase, a.review_answer, a.error_reason
           FROM answers a
           JOIN questions q ON a.question_id = q.id
           WHERE a.attempt_id = ?
           ORDER BY q.seq""",
        (attempt_id,)
    ).fetchall()
    conn.close()

    result = dict(attempt)
    result["answers"] = [dict(a) for a in answers_rows]
    return result


def save_answers_batch(answers_list):
    """批量保存答案。answers_list 每个元素是 (attempt_id, question_id, given_answer, is_correct)"""
    conn = get_conn()
    conn.executemany(
        "INSERT INTO answers (attempt_id, question_id, given_answer, is_correct, phase) VALUES (?, ?, ?, ?, 'first')",
        answers_list
    )
    conn.commit()
    conn.close()


def save_review_answers(review_list):
    """保存订正答案。review_list 每个元素是 (attempt_id, question_id, review_answer, is_correct, error_reason)"""
    conn = get_conn()
    conn.executemany(
        "UPDATE answers SET review_answer=?, is_correct=?, error_reason=?, phase='review' WHERE attempt_id=? AND question_id=?",
        [(r[2], r[3], r[4], r[0], r[1]) for r in review_list]
    )
    conn.commit()
    conn.close()


# ==================== 备份与恢复 ====================

def _is_turso():
    """检查是否使用 Turso 云数据库"""
    return bool(TURSO_URL and TURSO_TOKEN)


def get_answers_by_attempt(attempt_id):
    """获取某次考试的所有答案（用于恢复考试）。
    返回 dict {question_id: given_answer}"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT question_id, given_answer FROM answers WHERE attempt_id = ? AND phase = 'first'",
        (attempt_id,)
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        qid = r["question_id"] if isinstance(r, dict) else r[0]
        ans = r["given_answer"] if isinstance(r, dict) else r[1]
        result[qid] = ans or ""
    return result


def ensure_local_backup(campus_id=None):
    """确保本地存在 SQLite 备份文件。
    如果使用 Turso 云数据库，将所有数据导出到本地 SQLite。
    如果使用本地 SQLite，直接返回已有文件路径。
    campus_id: 非 None 时只导出该校区数据（校区管理员用）。
    返回本地 SQLite 文件的路径。"""
    import sqlite3

    # 本地 SQLite 模式：文件已存在，直接返回（校区过滤不适用于本地文件）
    if os.path.exists(DB_PATH):
        return DB_PATH

    # Turso 模式：需要从云数据库导出到本地
    os.makedirs(DB_DIR, exist_ok=True)
    src = get_conn()  # Turso 连接
    dst = sqlite3.connect(DB_PATH)
    dst.execute("PRAGMA foreign_keys = ON")

    # 创建本地表结构
    dst.executescript("""
        CREATE TABLE IF NOT EXISTS campuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS question_banks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            level TEXT NOT NULL,
            year TEXT NOT NULL,
            uploader_id INTEGER,
            campus_id INTEGER,
            created_at TEXT NOT NULL,
            delete_requested INTEGER DEFAULT 0,
            duration_minutes INTEGER DEFAULT 60
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_id INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            qtype TEXT NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT DEFAULT '',
            option_b TEXT DEFAULT '',
            option_c TEXT DEFAULT '',
            option_d TEXT DEFAULT '',
            answer TEXT NOT NULL,
            explanation TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            display_name TEXT NOT NULL,
            campus_id INTEGER,
            agreed_terms_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS exam_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bank_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            submitted_at TEXT,
            score INTEGER,
            total INTEGER NOT NULL,
            time_sec INTEGER
        );
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            given_answer TEXT,
            is_correct INTEGER DEFAULT 0,
            phase TEXT DEFAULT 'first',
            review_answer TEXT,
            error_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS upload_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            campus_id INTEGER,
            filename TEXT NOT NULL,
            file_size INTEGER,
            question_count INTEGER,
            bank_name TEXT,
            uploaded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            target TEXT,
            detail TEXT,
            created_at TEXT NOT NULL
        );
    """)

    # 按依赖顺序导出数据（校区管理员只导出本校数据）
    tables = [
        ('campuses', f"SELECT * FROM campuses{' WHERE id = ' + str(campus_id) if campus_id else ''}"),
        ('users', f"SELECT * FROM users{' WHERE campus_id = ' + str(campus_id) if campus_id else ''}"),
        ('question_banks', f"SELECT * FROM question_banks{' WHERE campus_id = ' + str(campus_id) if campus_id else ''}"),
        ('questions',
         f"SELECT q.* FROM questions q JOIN question_banks qb ON q.bank_id = qb.id"
         f"{' WHERE qb.campus_id = ' + str(campus_id) if campus_id else ''}"),
        ('exam_attempts',
         f"SELECT ea.* FROM exam_attempts ea JOIN users u ON ea.user_id = u.id"
         f"{' WHERE u.campus_id = ' + str(campus_id) if campus_id else ''}"),
        ('answers',
         f"SELECT a.* FROM answers a JOIN exam_attempts ea ON a.attempt_id = ea.id JOIN users u ON ea.user_id = u.id"
         f"{' WHERE u.campus_id = ' + str(campus_id) if campus_id else ''}"),
        ('upload_logs', f"SELECT * FROM upload_logs{' WHERE campus_id = ' + str(campus_id) if campus_id else ''}"),
        ('operation_logs', "SELECT * FROM operation_logs"),
    ]
    for table, query in tables:
        try:
            rows = src.execute(query).fetchall()
            if rows:
                cols = list(rows[0].keys())
                placeholders = ','.join(['?' for _ in cols])
                col_names = ','.join(cols)
                for row in rows:
                    values = [row[c] for c in cols]
                    dst.execute(
                        f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
                        values
                    )
        except Exception:
            pass  # 表可能为空或不存在

    dst.commit()
    dst.close()
    src.close()
    return DB_PATH


def restore_from_sqlite(file_path):
    """从本地 SQLite 备份文件恢复到当前数据库。
    适用于 Turso 云数据库和本地 SQLite 两种模式。
    恢复前会校验文件是否为合法备份。"""
    import sqlite3

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"备份文件不存在: {file_path}")

    # ---- 校验备份文件 ----
    try:
        test_conn = sqlite3.connect(file_path)
        tables = test_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        table_names = set(t[0] for t in tables)
        test_conn.close()
    except sqlite3.DatabaseError as e:
        raise ValueError(f"上传的文件不是有效的 SQLite 数据库：{e}")

    required_tables = {'users', 'questions', 'question_banks'}
    missing = required_tables - table_names
    if missing:
        raise ValueError(
            f"备份文件缺少核心表：{', '.join(missing)}。"
            f"请上传由本系统导出的合法 .db 备份文件。"
        )

    # ---- 执行恢复 ----
    dst = get_conn()  # 目标数据库（Turso 或本地 SQLite）
    src = sqlite3.connect(file_path)
    src.row_factory = sqlite3.Row

    # 按逆依赖顺序清空现有数据
    tables_to_clear = ['answers', 'exam_attempts', 'upload_logs', 'questions',
                       'question_banks', 'users', 'campuses']
    for table in tables_to_clear:
        try:
            dst.execute(f"DELETE FROM {table}")
        except Exception:
            pass

    # 按依赖顺序导入数据
    tables_to_import = ['campuses', 'users', 'question_banks', 'questions',
                        'exam_attempts', 'answers', 'upload_logs']
    for table in tables_to_import:
        try:
            src_rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if not src_rows:
                continue
            # 获取列名
            pragma_rows = src.execute(f"PRAGMA table_info({table})").fetchall()
            cols = [r['name'] for r in pragma_rows]
            placeholders = ','.join(['?' for _ in cols])
            col_names = ','.join(cols)
            for row in src_rows:
                values = [row[c] for c in cols]
                dst.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    values
                )
        except Exception:
            pass

    src.close()
    dst.close()


# 启动时自动初始化数据库
init_db()
