"""
用户认证模块
支持注册、登录、密码哈希。
"""

import hashlib
import os
import db
from datetime import datetime


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


def register_user(username, password, role='student', display_name='', campus_id=None):
    """
    注册新用户。
    campus_id=None 表示超级管理员（仅当 role='admin' 时有效）
    """
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

    # 非超级管理员必须选择校区
    if role != 'admin' or campus_id is not None:
        if campus_id is None:
            return False, "请选择校区", None

    pwd_hash, salt = hash_password(password)
    display = display_name.strip() if display_name.strip() else username

    try:
        user_id = db.create_user(username, pwd_hash, salt, role, display, campus_id)
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

    user = db.get_user_by_username(username)
    if not user:
        return False, "用户名不存在", None

    # 验证密码
    pwd_hash, _ = hash_password(password, user['salt'])
    if pwd_hash != user['password_hash']:
        return False, "密码错误", None

    return True, f"登录成功！欢迎回来，{user['display_name']}！", user
