"""
用户认证模块
支持注册、登录、密码哈希。
"""

import hashlib
import os
import time
import db
from datetime import datetime

# ==================== 登录限流 ====================
# 内存计数器：{username: {"failures": int, "locked_until": float}}
_login_failures = {}
MAX_FAILURES = 5        # 连续失败次数上限
LOCK_MINUTES = 5         # 锁定时长（分钟）


def _check_login_lock(username):
    """检查是否被锁定。返回 (is_locked: bool, wait_seconds: int)"""
    record = _login_failures.get(username)
    if not record:
        return False, 0
    if record.get("locked_until") and time.time() < record["locked_until"]:
        wait = int(record["locked_until"] - time.time())
        return True, max(wait, 1)
    # 锁定已过期，清除记录
    if record.get("locked_until") and time.time() >= record["locked_until"]:
        _login_failures.pop(username, None)
    return False, 0


def _record_login_failure(username):
    """记录一次登录失败"""
    record = _login_failures.get(username, {"failures": 0, "locked_until": 0})
    record["failures"] += 1
    if record["failures"] >= MAX_FAILURES:
        record["locked_until"] = time.time() + LOCK_MINUTES * 60
    _login_failures[username] = record


def _clear_login_failures(username):
    """登录成功后清除失败记录"""
    _login_failures.pop(username, None)


def hash_password(password, salt=None):
    """
    使用 PBKDF2 对密码进行哈希。
    如果未提供 salt，则生成新的随机 salt。
    返回 (hash_hex, salt_hex) 元组。
    """
    if salt is None:
        salt = os.urandom(32)
    elif isinstance(salt, str):
        salt = bytes.fromhex(salt)

    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        100000,  # 迭代次数
        dklen=32,
    )
    return key.hex(), salt.hex()


def register_user(username, password, role='student', display_name='', campus_id=None, agreed_terms=False):
    """注册新用户。agreed_terms 必须为 True 才允许注册。"""
    if not agreed_terms:
        return False, "请先阅读并同意用户协议", None

    username = username.strip()
    if not username or len(username) < 2:
        return False, "用户名至少需要2个字符", None
    if len(username) > 30:
        return False, "用户名不能超过30个字符", None

    existing = db.get_user_by_username(username)
    if existing:
        return False, f"用户名「{username}」已被注册", None

    if not password or len(password) < 4:
        return False, "密码至少需要4个字符", None

    if role not in ('student', 'admin'):
        return False, "无效的用户角色", None

    if role != 'admin' or campus_id is not None:
        if campus_id is None:
            return False, "请选择校区", None

    pwd_hash, salt = hash_password(password)
    display = display_name.strip() if display_name.strip() else username
    agreed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        user_id = db.create_user(username, pwd_hash, salt, role, display, campus_id, agreed_at)
        return True, f"注册成功！欢迎，{display}！", user_id
    except Exception as e:
        return False, f"注册失败：{e}", None


def login_user(username, password):
    """
    用户登录验证。
    返回 (success: bool, message: str, user: dict|None)
    """
    username = username.strip()
    if not username or not password:
        return False, "请输入用户名和密码", None

    # 检查是否被锁定
    locked, wait = _check_login_lock(username)
    if locked:
        minutes = wait // 60
        seconds = wait % 60
        if minutes > 0:
            return False, f"账号已临时锁定，请 {minutes} 分 {seconds} 秒后再试", None
        return False, f"账号已临时锁定，请 {seconds} 秒后再试", None

    user = db.get_user_by_username(username)
    if not user:
        _record_login_failure(username)
        return False, "用户名不存在", None

    # 验证密码
    pwd_hash, _ = hash_password(password, user['salt'])
    if pwd_hash != user['password_hash']:
        _record_login_failure(username)
        return False, "密码错误", None

    # 登录成功，清除失败记录
    _clear_login_failures(username)
    return True, f"登录成功！欢迎回来，{user['display_name']}！", user


def reset_password(username, new_password, recovery_key, expected_key):
    """应急密码重置。expected_key 从 st.secrets 传入。"""
    if recovery_key != expected_key:
        return False, "恢复密钥错误"
    user = db.get_user_by_username(username)
    if not user:
        return False, "用户名不存在"
    pwd_hash, salt = hash_password(new_password)
    ok = db.reset_user_password(username, pwd_hash, salt)
    if ok:
        return True, f"✅ 用户「{username}」密码已重置"
    return False, "重置失败"


def ensure_default_admin(username, password):
    """
    确保默认超级管理员存在。仅首次创建，不覆盖已有密码。
    """
    existing = db.get_user_by_username(username)
    if existing:
        return  # 已存在，不修改密码

    pwd_hash, salt = hash_password(password)
    db.create_user(username, pwd_hash, salt, 'admin', '系统管理员', None, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
