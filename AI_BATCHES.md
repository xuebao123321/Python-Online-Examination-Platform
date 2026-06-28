# 在线考试练习系统 — AI 修复批次提示词

> 项目路径：`/Users/andy/Documents/Andy AI/python study`
> 每个批次执行完系统必须完整可运行，无 bug。

---

## 批次一：修复 4 个严重 Bug

```
请修复以下4个严重Bug，确保系统完整可运行：

**Bug 1：恢复考试丢失已作答内容**
文件 app.py 的 `_resume_exam()` 函数中，`st.session_state.answers = {}` 把学生之前的作答全部清空了。应该从数据库 answers 表中查询该 attempt_id 已有的答案，恢复到 st.session_state.answers 中（key=question_id, value=given_answer）。

**Bug 2：恢复考试倒计时重置**
同样是 `_resume_exam()`，`st.session_state.start_time = time.time()` 让倒计时重新开始，学生可以通过退出再恢复来无限刷时间。应该根据 attempt 记录的 `started_at` 字段计算已用时间，设置正确的 start_time：`start_time = time.time() - 已经过的秒数`。注意 `started_at` 是字符串格式 "%Y-%m-%d %H:%M:%S"，需要用 datetime 解析。

**Bug 3：校区管理员下载备份获取了全校数据**
db.py 的 `ensure_local_backup()` 导出全部7张表时没有做 campus_id 过滤，校区管理员能下载到其他校区的所有数据。修改方案：
- 给 `ensure_local_backup()` 增加可选参数 `campus_id=None`
- 当 campus_id 不为 None 时，每张表只导出属于该校区数据：
  - campuses: WHERE id = campus_id
  - users: WHERE campus_id = campus_id  
  - question_banks: WHERE campus_id = campus_id
  - questions: JOIN question_banks WHERE qb.campus_id = campus_id
  - exam_attempts: JOIN users WHERE u.campus_id = campus_id
  - answers: JOIN exam_attempts JOIN users WHERE u.campus_id = campus_id
  - upload_logs: WHERE campus_id = campus_id
- app.py 中调用时，传入当前用户的 campus_id（超管传 None 导出全部）

**Bug 4：编程题被自动判分引擎判为错误**
grader.py 的 `grade_single()` 用字符串比较判分，编程题答案字段是空或参考代码，学生代码不可能完全匹配，所以编程题永远判错。修改方案：
- `grade_single()` 对 qtype=="编程" 返回特殊标记（如返回 None 表示需人工批改）
- `grade_all()` 中编程题不计入 score 和 total
- app.py 结果页面对编程题显示「📝 待人工批改」而非 ✅/❌
- 编程题不应影响自动评分的正确率计算

注意：修改 grader.py 的返回值结构可能影响 app.py 中的多处引用（考试结果展示、订正流程、总分计算），请仔细检查所有调用处并适配。

执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理。
```

---

## 批次二：安全加固

```
请修复以下4个安全问题，确保修改后系统完整可运行：

**问题1：删除校区无二次确认**
app.py 的 `page_admin_campuses()` 中，删除按钮点击后立即执行 `db.delete_campus()`，这会不可逆地删除该校区所有学生、考试记录和题库。请改为：点击删除后弹出二次确认，需要用户再次点击「确认删除」才真正执行。参考 app.py 中提交考试的确认模式（使用 st.session_state 标记 + 两个按钮）。

**问题2：恢复数据库备份无校验**
db.py 的 `restore_from_sqlite()` 直接清空目标数据库再导入，没有验证上传的 .db 文件是否是合法的备份文件。请增加校验：
- 检查文件是否为有效的 SQLite 数据库
- 检查是否包含核心表（users, questions, question_banks 至少要有）
- 校验不通过则抛出明确错误，由 app.py 捕获并提示用户

**问题3：默认超管密码硬编码在源码中**
app.py line 1486 的 `st.secrets.get("default_admin_pass", "xuxuchang123")` 把兜底密码写死在代码里并已提交到 Git。请改为：
- 如果 secrets 中没有配置 default_admin_pass，则不创建默认管理员
- 只在 secrets 中显式配置了 default_admin_user 和 default_admin_pass 时才自动创建
- 启动时如果检测到默认管理员不存在且 secrets 未配置，打印一条提示日志但不崩溃

**问题4：登录无暴力破解防护**
auth.py 的 `login_user()` 没有登录频率限制。请实现一个简单的内存限流：
- 在 auth.py 中维护一个登录失败计数器（用 Python dict）
- 同一用户名连续失败 5 次后，锁定 5 分钟
- 锁定期间返回「账号已临时锁定，请5分钟后再试」
- 登录成功后清除失败计数

执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理。
```

---

## 批次三：列表分页、搜索与题库管理优化

```
请完成以下优化，确保每一步修改后系统完整可运行：

**优化1：全局列表分页**
以下页面目前一次性加载全部数据，数据量大时会卡死。请全部加上分页（每页20条）：
- app.py `page_admin_students()` 学生列表
- app.py `page_admin_records()` 全部考试记录
- app.py `page_admin_audit_log()` 上传日志
- app.py `page_student_history()` 学生历史记录
- app.py `page_student_wrong()` 错题本

分页实现方式：在 db.py 的对应查询函数中增加 `limit` 和 `offset` 参数，app.py 中用 st.session_state 维护当前页码，显示「上一页/下一页」按钮和「第X页/共Y页」信息。

**优化2：学生管理加搜索**
app.py `page_admin_students()` 页面上方增加一个搜索框，支持按用户名或显示名模糊搜索。在 db.py 增加相应的查询函数。搜索与分页要配合使用。

**优化3：年份选择器动态生成**
app.py 的 `page_admin_upload()` 中年份列表硬编码为 `range(2010, 2027)`。改为动态生成：当前年份往前推20年到往后推1年。

**优化4：题库预览功能**
在上传题库页面右侧「已有题库」列表中，每个题库增加一个「👁️ 预览」按钮，点击后用 st.expander 展示该题库的前10道题目（题型+题目文本+正确答案）。在 db.py 中已有 `get_questions(bank_id)` 可以直接用。

**优化5：单题编辑功能**
题库预览中，每道题旁边增加「✏️ 编辑」按钮，点击后可修改题目文本、选项、正确答案、解析。在 db.py 中增加 `update_question(question_id, **fields)` 函数。

执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理。
```

---

## 批次四：考试体验升级

```
请完成以下考试系统体验优化，确保每步修改后系统完整可运行：

**优化1：考试题目随机排序**
目前考试题目始终按 seq 顺序排列。增加一个选项：学生开始考试前，可以选择「顺序出题」或「随机出题」。如果选随机，在 `_start_exam()` 中将题目列表用 `random.shuffle()` 打乱。注意：打乱后题号导航栏仍要按实际显示顺序编号。

**优化2：可配置的考试时长**
目前倒计时固定 3600 秒（60分钟）。改为在 question_banks 表中增加 `duration_minutes` 字段（默认60），创建题库时可设置。在考试时读取该题库的时长配置。需要：
- db.py 修改 question_banks 表结构（ALTER TABLE 或迁移）
- csv_import.py 支持可选的「考试时长(分钟)」列
- app.py 上传页面增加时长设置
- app.py 考试页面读取该配置

**优化3：练习模式**
学生在「参加考试」页面增加一个选项：「📝 练习模式」vs「📝 考试模式」。
- 练习模式：无倒计时、每题提交后立即显示对错和解析、可随时退出、不记录考试成绩
- 考试模式：保持现有逻辑不变

**优化4：密码强度要求**
auth.py 的 `register_user()` 中密码只要求 ≥4 个字符。改为：
- 至少 6 个字符
- 必须包含字母和数字
- 注册页面前端给出密码强度提示

执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理。
```

---

## 批次五：文档更新与运维优化

```
请完成以下文档和运维优化，确保系统完整可运行：

**优化1：README.md 重写**
当前 README.md 描述的是最早期单机版功能。请根据 DEV_DOC.md 和实际代码，重写 README.md，包含：
- 项目简介（多校区在线考试练习平台）
- 核心功能列表（三种题型、角色权限、错题订正、Turso 云数据库等）
- 本地快速启动步骤
- 部署到 Streamlit Cloud 的步骤（含 Secrets 配置说明）
- CSV 题库格式说明（含编程题）
- 技术栈说明

**优化2：增加操作日志**
在 db.py 中增加 `operation_logs` 表，记录关键管理操作：
- 删除题库（谁、什么时候、删了什么）
- 删除校区
- 重置密码
- 恢复数据库备份
在 app.py 的对应操作处调用日志记录。
超管在「📋 上传日志」页面可以切换查看「上传日志」和「操作日志」。

**优化3：会话超时**
增加登录会话超时机制：如果用户超过 2 小时无操作，自动退出登录。实现方式：
- st.session_state 中记录 `last_activity` 时间戳
- 在 main() 开头检查：如果已登录且超过 2 小时无活动，自动调用 logout()

**优化4：备份下载性能优化**
当前 `ensure_local_backup()` 在每次管理员侧边栏渲染时都会执行（即使不点下载按钮），在 Turso 模式下每次全量导出很慢。改为懒加载：
- 不在侧边栏渲染时调用 ensure_local_backup()
- 改为「生成备份」按钮
- 点击后生成备份文件，生成后再显示下载按钮

执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理。
```

---

## 使用说明

1. 按批次顺序执行，**每批次一个 AI 对话**
2. 每批次执行完后，运行以下命令确认语法无误：

```bash
cd "/Users/andy/Documents/Andy AI/python study"
python3 -c "import ast; ast.parse(open('app.py').read()); ast.parse(open('db.py').read()); ast.parse(open('auth.py').read()); ast.parse(open('grader.py').read())"
```

3. 确认无报错后，再进入下一批次
4. 每个批次末尾都有「执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理」这句话，AI 会自行检查
