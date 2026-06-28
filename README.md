# 📝 在线考试练习系统

面向编程培训校区的 SaaS 考试练习平台。支持三种题型（单选/判断/编程）、多校区数据隔离、错题订正流程、管理员仪表盘。

## ✨ 核心功能

- 🏫 **多校区管理** — 超级管理员创建校区，数据按 campus_id 完全隔离
- 👥 **三级角色** — 超级管理员 / 校区管理员 / 学生，权限矩阵精细控制
- 📝 **三种题型** — 单选题、判断题、编程题（Pyodide 浏览器端运行 Python）
- ⏱️ **倒计时考试** — 可配时长（默认60分钟），时间到自动提交
- 🔀 **随机出题** — 考试模式可选顺序或随机排列题目
- 📝 **练习模式** — 无倒计时、答后即时显示对错与解析、不记录成绩
- ✏️ **错题订正** — 答错需重新作答+选择错误原因，订正后解锁全部解析
- 📊 **管理员仪表盘** — 学生统计、错因分布、题库使用率一目了然
- 🔍 **分页搜索** — 学生列表支持模糊搜索，所有列表分页显示
- 📤 **CSV 批量导入** — 用 Excel 编辑题库，一键导入（含版权声明+审计日志）
- ☁️ **双数据库模式** — Turso 云数据库（生产） / SQLite 本地文件（开发），自动切换
- 📦 **数据库备份** — 支持一键导出和恢复，校区管理员仅导出本校数据
- 🔒 **安全加固** — PBKDF2+SHA256 密码加密、登录限流、会话超时、操作审计日志

## 🚀 本地启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动
streamlit run app.py
# → http://localhost:8501
```

本地模式使用 SQLite 存储，数据文件在 `data/exam.db`。

## ☁️ 部署到 Streamlit Cloud

1. Fork 本仓库，在 Streamlit Cloud 中连接
2. 在 Settings → Secrets 中配置：

```toml
# 云数据库（必填，否则使用本地 SQLite）
TURSO_URL = "libsql://your-db.turso.io"
TURSO_TOKEN = "your-token"

# 恢复密钥（用于重置密码）
recovery_key = "your-secret-key"

# 默认管理员（选填，首次部署时自动创建）
default_admin_user = "admin"
default_admin_pass = "your-secure-password"
```

3. 点击 Deploy

## 📋 CSV 题库格式

用 Excel 编辑，另存为 CSV（UTF-8 编码）。第一行必须是列名：

```
序号,题型,题目,选项A,选项B,选项C,选项D,正确答案,解析
```

| 题型 | 选项 | 正确答案 | 解析 |
|------|------|---------|------|
| 单选 | 至少填 A、B | A/B/C/D | 答对后展示 |
| 判断 | 可留空 | 对/错 | 答对后展示 |
| 编程 | 可留空 | 参考代码（可选） | 解题思路或参考代码 |

上传时需先同意版权声明，系统会记录上传审计日志。

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| UI | Streamlit（纯 Python） |
| 数据库 | Turso（生产）/ SQLite（本地） |
| 认证 | PBKDF2 + SHA256 + 随机盐 |
| 编程题运行 | Pyodide（WebAssembly 浏览器沙箱） |
| 部署 | Streamlit Cloud（免费） |

## 📁 文件结构

```
├── app.py              # 主程序（UI + 路由）
├── db.py               # 数据库操作（Turso/SQLite 双模式）
├── auth.py             # 用户认证（注册/登录/密码重置/限流）
├── csv_import.py       # CSV 解析和验证
├── grader.py           # 判分引擎（单选+判断，编程题待人工批改）
├── code_runner.py      # Pyodide 代码运行器
├── turso_adapter.py    # Turso HTTP API 适配器
├── requirements.txt    # streamlit
├── DEV_DOC.md          # 开发文档（架构/数据库/权限/部署）
├── AI_BATCHES.md       # AI 修复批次记录
├── data/               # 本地数据库目录
└── sample_questions/   # 示例题库模板
```
