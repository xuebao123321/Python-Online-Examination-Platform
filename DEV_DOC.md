# Python 在线考试系统 开发文档

> 版本：v2.1  
> 更新：2026-06-26  
> 数据库：Turso 云数据库（生产） / SQLite（本地开发）  
> 部署：Streamlit Cloud（免费）

---

## 一、项目概述

Python 在线考试系统是一个面向编程培训校区的 SaaS 考试练习平台。支持三种题型（单选/判断/编程）、多校区数据隔离、错题订正流程、管理员仪表盘。

### 核心功能

- 多校区数据完全隔离，互不可见
- 单选题 + 判断题 + 编程题（Pyodide 浏览器端运行）
- 倒计时考试 + 题号导航 + 自动判分
- 错题订正 + 错误原因分析 + 答案分阶段解锁
- CSV 题库导入（Excel 编辑），含版权声明和上传审计
- Turso 云数据库永久持久化，部署重启不丢数据
- 三种角色：超级管理员 / 校区管理员 / 学生

---

## 二、技术架构

| 层级 | 技术 | 说明 |
|------|------|------|
| UI | Streamlit | 纯 Python，无需前端代码 |
| 数据库 | Turso（生产）/ SQLite（本地） | 双模式自动切换 |
| 认证 | PBKDF2 + SHA256 + 随机盐 | 密码加密存储 |
| 编程题运行 | Pyodide（WebAssembly） | 浏览器沙箱执行，无需服务器 |
| 部署 | Streamlit Cloud | 免费托管，自动 CI/CD |
| 语言 | Python 3.9+ | 仅需 streamlit 一个依赖 |

### 双数据库模式

```
检测环境变量 TURSO_URL
├── 已配置 → Turso 云数据库（生产，数据持久化）
└── 未配置 → SQLite 本地文件（data/exam.db）
```

---

## 三、数据库设计

### ER 图

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐
│ campuses │     │    users     │     │ question_banks│
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
                        ▼                     ▼
                 ┌──────────────┐     ┌───────────────┐
                 │exam_attempts │     │   questions   │
                 ├──────────────┤     ├───────────────┤
                 │ id           │     │ id            │
                 │ user_id      │     │ bank_id       │
                 │ bank_id──────┼────►│ seq           │
                 │ score        │     │ qtype(单选/判断/编程)│
                 │ total        │     │ question      │
                 │ time_sec     │     │ option_a~d    │
                 │ started_at   │     │ answer        │
                 │ submitted_at │     │ explanation   │
                 └──────┬───────┘     └───────────────┘
                        │
                        ▼
                 ┌──────────────┐     ┌───────────────┐
                 │   answers    │     │  upload_logs  │
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

### 关键字段说明

#### answers 表
| 字段 | 说明 |
|------|------|
| phase | `first` 首次答题 / `review` 订正后 |
| review_answer | 订正时的新答案 |
| error_reason | 错因：粗心马虎/知识点未掌握/没有思路/审题不清/其他 |

#### question_banks 表
| 字段 | 说明 |
|------|------|
| delete_requested | 0=正常 1=待审批 2=已删除 |
| campus_id | 归属校区（数据隔离核心字段） |

---

## 四、用户角色与权限

### 判断逻辑

| 角色 | 条件 |
|------|------|
| 🔑 超级管理员 | `role='admin' AND campus_id IS NULL` |
| 👩‍🏫 校区管理员 | `role='admin' AND campus_id IS NOT NULL` |
| 👨‍🎓 学生 | `role='student'` |

### 权限矩阵

| 功能 | 超级管理员 | 校区管理员 | 学生 |
|------|:--:|:--:|:--:|
| 创建校区 | ✅ | ❌ | ❌ |
| 全校数据 | ✅ | ❌ | ❌ |
| 本校数据 | ✅ | ✅ | ❌ |
| 上传题库 | ✅（选校区） | ✅（归本校） | ❌ |
| 删除题库 | ✅ 直接删 | 📩 申请删 | ❌ |
| 审批删除 | ✅ | ❌ | ❌ |
| 上传日志 | ✅ | ❌ | ❌ |
| 查看全校学生 | ✅ | ❌ | ❌ |
| 查看本校学生 | ✅ | ✅ | ❌ |
| 查看学生答题详情 | ✅（全解析） | ✅（全解析） | ❌ |
| 重置密码 | ✅ | ❌ | ❌ |
| 参加考试 | ❌ | ❌ | ✅ |
| 考试结果 | ❌ | ❌ | ✅（分阶段解锁） |
| 错题订正 | ❌ | ❌ | ✅ |
| 错题本 | ❌ | ❌ | ✅ |
| 下载备份 | ✅ | ✅ | ❌ |

---

## 五、考试流程

### 考试状态机

```
idle → in_progress → submitted → reviewing → reviewed
  │         │            │            │           │
  │     答题中      首次提交     错题订正中   订正完成
  │   倒计时60分钟  只显示✅❌   选错因+重做   解锁全解析
```

### 首次提交

1. 学生选择级别和年月，开始考试
2. 界面上方：题号导航栏（✅已答/○未答/当前高亮，可点击跳转）
3. 倒计时 60 分钟（剩余 <10 分变橙，<5 分变红）
4. 逐题作答，有未答题提交时二次确认
5. 提交后：得分 + ✅❌，**答对显示解析，答错不显示正确答案和解析**

### 错题订正

1. 有错题时必须进入「错题订正」
2. 逐题重做 + 选择错误原因（必选）
3. 提交订正后**解锁全部正确答案和解析**
4. 全对则直接解锁

### 答案分阶段解锁（学生端）

| 阶段 | 答对 | 答错 |
|------|------|------|
| 首次提交 | ✅ + 解析 | ❌ + 引导订正（无正确答案无解析） |
| 订正后 | ✅ + 解析 | ✅ + 解析（全部解锁） |

### 管理员查看

管理员查看学生试卷时**始终可见**完整答案、解析和错因统计。

---

## 六、题库管理

### CSV 格式

```
序号,题型,题目,选项A,选项B,选项C,选项D,正确答案,解析
```

| 题型 | 选项 | 正确答案 |
|------|------|---------|
| 单选 | 至少填 A、B | A/B/C/D |
| 判断 | 可留空 | 对/错 |
| 编程 | 可留空 | 留空或参考代码 |

### 上传流程

选择 CSV → 选级别名称 → 选年月 → [超管选校区] → 勾版权声明 → 导入

### 题库隔离

- 校区管理员上传 → 自动归属本校
- 超级管理员上传 → 需手动选择目标校区
- 题库按 campus_id 完全隔离，不同校区互不可见

### 删除审批

```
校区管理员 → 申请删除 → delete_requested=1
超级管理员 → 仪表盘审批 → 同意/拒绝
```

---

## 七、编程题

### 技术实现

Pyodide = Python 解释器编译为 WebAssembly，在浏览器中直接运行 Python 代码。

### 考试体验

1. 学生看到代码编辑器（textarea）
2. 编写 Python 代码
3. 点击「▶️ 运行代码」→ Pyodide 浏览器端执行 → 显示输出
4. 代码不经过服务器，纯浏览器沙箱

### 判分

编程题暂为人工判分，管理员在后台查看学生代码后评分。

---

## 八、数据安全

### 数据隔离

| 维度 | 方式 |
|------|------|
| 题库 | `campus_id` 过滤 |
| 学生 | `campus_id` 过滤 |
| 考试记录 | user → campus_id 关联过滤 |
| 上传日志 | campus_id 隔离 |

### 密码安全

- PBKDF2 + SHA256，100,000 次迭代
- 随机 256-bit 盐值
- 恢复密钥在 Streamlit Secrets 中

### 法律合规

- 注册时强制同意《用户协议》（含版权免责/赔偿条款）
- 上传前勾选版权声明
- 上传审计日志可溯源（时间/上传者/校区/文件名）
- 题库完全按校区隔离
- `agreed_terms_at` 记录用户协议同意时间

### Git 安全

```
.gitignore 排除：
  data/exam.db           # 用户数据
  .streamlit/secrets.toml # 密钥密码
  .claude/               # 本地配置
```

---

## 九、部署

### 本地开发

```bash
pip install streamlit
streamlit run app.py
# → http://localhost:8501
```

### Streamlit Cloud（生产）

1. GitHub 推送代码
2. Streamlit Cloud 连接仓库
3. 配置 Secrets：

```toml
TURSO_URL = "libsql://your-db.turso.io"
TURSO_TOKEN = "your-token"
recovery_key = "your-key"
default_admin_user = "admin"
default_admin_pass = "your-password"
```

### 数据库备份

管理员侧边栏 → 📥 下载备份 / 📤 恢复备份

---

## 十、文件结构

```
python study/
├── app.py                  # 主程序（UI + 路由，~1400行）
├── db.py                   # 数据库操作（双模式：Turso/SQLite）
├── auth.py                 # 用户认证（注册/登录/密码重置）
├── csv_import.py           # CSV 解析和验证
├── grader.py               # 判分引擎（单选+判断+编程）
├── code_runner.py          # Pyodide 代码运行器
├── turso_adapter.py        # Turso HTTP API 适配器
├── requirements.txt        # streamlit
├── .gitignore
├── .streamlit/
│   └── secrets.toml        # 本地密钥（不入库）
├── data/.gitkeep
├── sample_questions/
│   └── 考试题库模板.csv
├── README.md               # 用户文档
└── DEV_DOC.md              # 本开发文档
```

---

## 十一、关键业务规则

- **默认管理员**：系统启动时若 `admin` 不存在则自动创建，已存在不覆盖密码
- **考试倒计时**：默认 60 分钟（3600 秒），剩余 <5 分钟红色警告
- **刷新免登录**：登录后 URL 带 `?user=用户名`，刷新自动恢复
- **题库去重**：同一 `(level, year)` 只能存在一个题库
- **编程题加载**：Pyodide 首次加载约 15 秒（CDN），之后缓存秒开
