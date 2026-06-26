# Python 在线考试系统 开发文档

> 版本：v2.0  
> 更新：2026-06-26  
> 数据库：Turso 云数据库（生产） / SQLite（本地开发）

---

## 一、项目概述

Python 在线考试系统是一个面向编程培训校区的 SaaS 考试练习平台。学生在线答题、自动判分、错题订正；管理员按校区管理题库、学生和数据。

### 核心特性

- 多校区数据隔离，互不可见
- 单选题 + 判断题自动判分
- 错题订正 + 错误原因分析
- CSV 题库导入，支持 Excel 编辑
- Turso 云数据库，数据永久持久化
- 一键部署到 Streamlit Cloud

---

## 二、技术架构

| 层级 | 技术 | 说明 |
|------|------|------|
| UI | Streamlit | 纯 Python，无需前端代码 |
| 数据库 | Turso（生产）/ SQLite（本地） | HTTP API 适配，零原生依赖 |
| 认证 | PBKDF2 + SHA256 + 随机盐 | 密码加密存储 |
| 部署 | Streamlit Cloud | 免费托管，自动 CI/CD |
| 语言 | Python 3.9+ | 仅需 streamlit 一个依赖 |

### 双数据库模式

```
┌─ 检测环境变量 TURSO_URL ─┐
│                           │
├─ 已配置 → Turso 云数据库  │  生产环境，数据持久化
├─ 未配置 → SQLite 本地文件 │  本地开发，零配置
└───────────────────────────┘
```

切换逻辑在 `db.py` → `get_conn()` 中实现。Turso 通过 `turso_adapter.py` 的 HTTP API 适配器访问。

---

## 三、数据库设计

### 3.1 ER 图

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐
│ campuses │     │  users       │     │ question_banks│
├──────────┤     ├──────────────┤     ├───────────────┤
│ id       │◄────│ campus_id    │     │ id            │
│ name     │     │ username     │     │ name          │
│ created  │     │ password_hash│     │ level         │
└──────────┘     │ salt         │     │ year          │
                 │ role         │     │ uploader_id───┼──► users.id
                 │ display_name │     │ campus_id─────┼──► campuses.id
                 │ agreed_terms │     │ delete_req    │
                 │ created      │     │ created_at    │
                 └──────┬───────┘     └───────┬───────┘
                        │                     │
                        │ user_id             │ bank_id
                        ▼                     ▼
                 ┌──────────────┐     ┌───────────────┐
                 │exam_attempts │     │  questions    │
                 ├──────────────┤     ├───────────────┤
                 │ id           │     │ id            │
                 │ user_id      │     │ bank_id       │
                 │ bank_id──────┼────►│ seq           │
                 │ score        │     │ qtype         │
                 │ total        │     │ question      │
                 │ time_sec     │     │ option_a~d    │
                 │ started_at   │     │ answer        │
                 │ submitted_at │     │ explanation   │
                 └──────┬───────┘     └───────────────┘
                        │
                        │ attempt_id
                        ▼
                 ┌──────────────┐     ┌───────────────┐
                 │  answers     │     │ upload_logs   │
                 ├──────────────┤     ├───────────────┤
                 │ id           │     │ id            │
                 │ attempt_id   │     │ user_id       │
                 │ question_id──┼──►  │ campus_id     │
                 │ given_answer │     │ filename      │
                 │ is_correct   │     │ question_count│
                 │ phase        │     │ bank_name     │
                 │ review_answer│     │ uploaded_at   │
                 │ error_reason │     └───────────────┘
                 └──────────────┘
```

### 3.2 表结构详解

#### campuses 校区表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT UNIQUE | 校区名称 |
| created_at | TEXT | 创建时间 |

#### users 用户表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| username | TEXT UNIQUE | 登录用户名 |
| password_hash | TEXT | PBKDF2 哈希 |
| salt | TEXT | 随机盐 |
| role | TEXT | `student` / `admin` |
| display_name | TEXT | 显示名称 |
| campus_id | INTEGER FK | 归属校区（NULL=超级管理员） |
| agreed_terms_at | TEXT | 用户协议同意时间 |
| created_at | TEXT | 注册时间 |

#### question_banks 题库表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT | 题库显示名（级别+年月） |
| level | TEXT | 考试级别（如"电子协会一级"） |
| year | TEXT | 考试年月（如"2023年3月"） |
| uploader_id | INTEGER FK | 上传者 |
| campus_id | INTEGER FK | 归属校区 |
| delete_requested | INTEGER | 0=正常 1=申请删除 2=已删除 |
| created_at | TEXT | 创建时间 |
| UNIQUE | (level, year) | 同级别年月唯一 |

#### questions 题目表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| bank_id | INTEGER FK | 所属题库 |
| seq | INTEGER | 题号 |
| qtype | TEXT | `单选` / `判断` |
| question | TEXT | 题目文字 |
| option_a~d | TEXT | 选项内容 |
| answer | TEXT | 正确答案 A/B/C/D 或 对/错 |
| explanation | TEXT | 答案解析 |

#### exam_attempts 考试记录表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| user_id | INTEGER FK | 考生 |
| bank_id | INTEGER FK | 题库 |
| score | INTEGER | 得分 |
| total | INTEGER | 总题数 |
| time_sec | INTEGER | 用时（秒） |
| started_at | TEXT | 开始时间 |
| submitted_at | TEXT | 提交时间（NULL=未提交） |

#### answers 答题记录表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| attempt_id | INTEGER FK | 考试记录 |
| question_id | INTEGER FK | 题目 |
| given_answer | TEXT | 首次答案 |
| is_correct | INTEGER | 0/1 |
| phase | TEXT | `first` / `review` |
| review_answer | TEXT | 订正答案 |
| error_reason | TEXT | 错误原因 |

#### upload_logs 上传审计表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| user_id | INTEGER FK | 上传者 |
| campus_id | INTEGER | 校区 |
| filename | TEXT | 文件名 |
| question_count | INTEGER | 题目数 |
| bank_name | TEXT | 题库名 |
| uploaded_at | TEXT | 上传时间 |

---

## 四、用户角色与权限

### 4.1 三种角色

| 角色 | campus_id | 识别条件 |
|------|-----------|---------|
| 🔑 超级管理员 | NULL | `role='admin' AND campus_id IS NULL` |
| 👩‍🏫 校区管理员 | 校区ID | `role='admin' AND campus_id IS NOT NULL` |
| 👨‍🎓 学生 | 校区ID | `role='student'` |

### 4.2 权限矩阵

| 功能 | 超级管理员 | 校区管理员 | 学生 |
|------|:--:|:--:|:--:|
| 创建校区 | ✅ | ❌ | ❌ |
| 查看全校数据 | ✅ | ❌ | ❌ |
| 查看本校数据 | ✅ | ✅ | ❌ |
| 上传题库 | ✅（选目标校区） | ✅（自动归属本校） | ❌ |
| 删除题库 | ✅ 直接删除 | 📩 申请删除 | ❌ |
| 审批删除 | ✅ | ❌ | ❌ |
| 查看上传日志 | ✅ | ❌ | ❌ |
| 查看学生列表 | ✅ 全校 | ✅ 本校 | ❌ |
| 查看学生详情 | ✅ | ✅ | ❌ |
| 重置密码 | ✅ | ❌ | ❌ |
| 参加考试 | ❌ | ❌ | ✅ |
| 查看历史记录 | ❌ | ❌ | ✅（自己） |
| 错题本 | ❌ | ❌ | ✅（自己） |
| 下载数据库备份 | ✅ | ✅ | ❌ |

---

## 五、题库管理

### 5.1 CSV 格式

上传的题库文件为 UTF-8 编码的 CSV，必需列名：

```
序号,题型,题目,选项A,选项B,选项C,选项D,正确答案,解析
```

| 题型 | 选项 | 正确答案 |
|------|------|---------|
| 单选 | 至少填 A、B | A / B / C / D |
| 判断 | 可留空 | 对 / 错 |

### 5.2 上传流程

```
选择 CSV 文件 → 选择级别名称 → 选择年月
    ↓
[超管] 选择目标校区
    ↓
勾选版权声明 → 点击导入
    ↓
记录上传审计日志
```

### 5.3 题库归属

- 校区管理员上传 → 自动归属本校
- 超级管理员上传 → 需选择目标校区
- 题库按 `campus_id` 隔离，学生只看本校题库
- 题库表 `delete_requested` 字段：0=正常 1=待审批 2=已删除

### 5.4 删除审批流程

```
校区管理员 → 申请删除 → delete_requested=1
    ↓
超级管理员 → 仪表盘看到待审批 → 同意/拒绝
    ↓
同意 → 物理删除题库及题目
拒绝 → delete_requested=0 恢复
```

---

## 六、考试流程

### 6.1 考试状态机

```
idle → in_progress → submitted → reviewing → reviewed
  │         │            │            │           │
  │     答题中      首次提交     错题订正中   订正完成
  │                 只显示✅❌   选错因+重做   解锁全解析
```

### 6.2 首次提交

1. 学生选择题库，开始考试
2. 逐题作答，计时（每题60秒）
3. 提交时有未答题二次确认
4. **提交后仅显示得分和 ✅❌，不显示答案和解析**

### 6.3 错题订正

1. 有错题时必须进入「错题订正」
2. 逐题重做 + 选择错误原因（必选）
   - 粗心马虎 / 知识点未掌握 / 没有思路 / 审题不清 / 其他
3. 提交订正后**解锁全部答案和解析**
4. 全对则直接解锁

### 6.4 管理员查看

管理员查看学生试卷时**始终可见**完整答案和解析，包括错因统计。

---

## 七、数据安全

### 7.1 数据隔离

| 维度 | 隔离方式 |
|------|---------|
| 题库 | `campus_id` 过滤 |
| 学生 | `campus_id` 过滤 |
| 考试记录 | 通过 user → campus_id 关联过滤 |
| 上传日志 | campus_id 隔离 |

### 7.2 密码安全

- PBKDF2 + SHA256 哈希，100,000 次迭代
- 随机 256-bit 盐值
- 恢复密钥存储在 Streamlit Secrets 中

### 7.3 法律合规

- 注册时强制同意《用户协议》
- 上传前勾选版权声明
- 上传审计日志可溯源
- 题库完全按校区隔离，禁止跨账号共享

### 7.4 已排除于 Git 仓库的敏感文件

```
.gitignore:
  data/exam.db           # 用户数据
  .streamlit/secrets.toml # 密钥和密码
  .claude/               # Claude 本地配置
```

---

## 八、部署

### 8.1 本地开发

```bash
pip install streamlit
streamlit run app.py
# → http://localhost:8501
```

默认使用本地 SQLite（`data/exam.db`），无需额外配置。

### 8.2 Streamlit Cloud 生产部署

1. GitHub 推送代码
2. Streamlit Cloud 连接仓库
3. 配置 Secrets（`TURSO_URL`、`TURSO_TOKEN`、`recovery_key`）
4. 自动部署 → 获得 `https://xxx.streamlit.app`

### 8.3 必需 Secrets

```toml
# Streamlit Cloud → Settings → Secrets
TURSO_URL = "libsql://your-db.turso.io"
TURSO_TOKEN = "your-auth-token"
recovery_key = "your-recovery-key"
default_admin_user = "admin"
default_admin_pass = "your-password"
```

### 8.4 数据库备份

管理后台侧边栏提供 **📥 下载数据库备份** 和 **📤 恢复数据库备份**。

---

## 九、文件结构

```
python study/
├── app.py                  # Streamlit 主程序（UI + 路由）
├── db.py                   # 数据库操作（双模式：Turso/SQLite）
├── auth.py                 # 用户认证（注册/登录/密码重置）
├── csv_import.py           # CSV 解析和验证
├── grader.py               # 判分引擎（单选+判断）
├── turso_adapter.py        # Turso HTTP API 适配器
├── requirements.txt        # 依赖（streamlit）
├── .gitignore              # 排除敏感文件
├── .streamlit/
│   └── secrets.toml        # 本地密钥（不入库）
├── data/
│   └── .gitkeep            # 确保目录存在
├── sample_questions/
│   ├── 考试题库模板.csv     # 下载模板
│   └── 电子协会一级_2023_示例.csv
├── README.md               # 用户使用文档
└── DEV_DOC.md              # 本开发文档
```

---

## 十、API 接口说明

### 10.1 数据库核心函数

| 模块 | 主要函数 | 说明 |
|------|---------|------|
| db.py | `get_conn()` | 自动选择 Turso 或 SQLite |
| db.py | `init_db()` | 建表 + 自动迁移 |
| db.py | `create_user()` | 创建用户 |
| db.py | `create_bank()` | 创建题库 |
| db.py | `create_attempt()` | 创建考试 |
| db.py | `get_admin_stats()` | 仪表盘统计 |
| db.py | `get_attempt_detail()` | 考试详情（含逐题答案） |
| auth.py | `register_user()` | 注册（含协议检查） |
| auth.py | `login_user()` | 登录验证 |
| auth.py | `ensure_default_admin()` | 默认管理员初始化 |
| auth.py | `reset_password()` | 密码重置 |
| grader.py | `grade_all()` | 批量判分 |
| grader.py | `grade_single()` | 单题判分 |
| csv_import.py | `parse_csv()` | CSV 解析 + 验证 |

### 10.2 Turso 适配器接口

`turso_adapter.py` 提供与 `sqlite3` 兼容的接口：

| 类/方法 | 对应 sqlite3 |
|---------|-------------|
| `TursoConnection` | `sqlite3.Connection` |
| `TursoConnection.execute()` | `conn.execute()` |
| `TursoConnection.executemany()` | `conn.executemany()` |
| `TursoConnection.cursor()` | `conn.cursor()` |
| `TursoCursor` | `sqlite3.Cursor` |
| `TursoCursor.execute()` | `cursor.execute()` |
| `TursoCursor.fetchone()` | `cursor.fetchone()` |
| `TursoCursor.fetchall()` | `cursor.fetchall()` |
| `TursoRow` | `sqlite3.Row` |
| `TursoRow.to_dict()` | `dict(row)` |
| `TursoRow['key']` | `row['key']` |

---

## 十一、关键业务规则

### 11.1 默认管理员

- 系统启动时自动检查 `admin` 用户是否存在
- 不存在则用 secrets 中的用户名密码创建
- 已存在则**不覆盖密码**（允许管理员自行修改）

### 11.2 考试计时

- 每题默认 60 秒（`total * 60`）
- 提交时按实际用时记录
- 计时器在每次交互时更新（Streamlit 特性）

### 11.3 分数计算

- 首次得分：第一次提交的原始成绩
- 订正得分：错题订正后的更新成绩
- 每题答对 1 分，答错 0 分

### 11.4 题库去重

- 同一 `(level, year)` 组合只能存在一个题库
- 重复上传会提示替换（保留原有 uploader 信息）
