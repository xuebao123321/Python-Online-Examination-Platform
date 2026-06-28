# 在线考试练习系统 — AI 开发批次提示词 V2

> 项目路径：`/Users/andy/Documents/Andy AI/python study`
> 接续 AI_BATCHES.md（批次一至五）
> 每个批次执行完系统必须完整可运行，无 bug。

---

## 批次六：历史记录列表增加订正状态标识

```
请修改历史记录页面，在学生端「📜 历史记录」列表中为每场考试增加订正状态标识，
确保修改后系统完整可运行：

**改动1：db.py 新增 get_attempt_review_stats() 函数**
在 db.py 中新增一个函数，输入 attempt_id，返回该次考试的订正统计字典：
```python
def get_attempt_review_stats(attempt_id):
    """返回 {total_answers, wrong_count, corrected_count, uncorrected_count, 
              original_score, current_score, error_reasons: [{reason, cnt}]}"""
```
查询逻辑：
- total_answers: 该 attempt 的总答题数
- wrong_count: is_correct=0 且 qtype!='编程' 的题目数（原始错题数，包括 phase='first' 时就是错的）
  - 提示：需要区分为"首次提交时的错题数"和"当前仍错的题数"
  - 首次错题数：所有 phase='first' 时 is_correct=0 且 qtype!='编程' 的数量
  - 当前仍错数（uncorrected_count）：is_correct=0 且 qtype!='编程'（订正后仍错 + 从未订正过的）
  - corrected_count: phase='review' 且 is_correct=1 的数量（订正后正确了的）
- original_score: 首次提交时的得分（不计编程题）
- current_score: 当前得分（含订正后的得分）
- error_reasons: 该考试中 error_reason 的分布统计（按原因分组计数）

注意：original_score 需要从原始提交数据获取。如果 answers 表中第一次提交后 score 被更新了，
可以从 exam_attempts 的 score 字段读取当前分数，原始分数需要计算首次 phase='first' 时的 is_correct 求和。
思考清楚后再实现，确保数据准确。

**改动2：app.py 历史记录列表增加订正状态行**
修改 `page_student_history()` 函数（约 L1124），在每条考试记录中增加一行订正状态提示。
对每条 attempt，调用刚写的 get_attempt_review_stats() 获取统计。

状态显示规则：
- 如果 wrong_count == 0：显示 🎉 全部正确
- 如果 uncorrected_count == 0 且 corrected_count > 0：显示 ✅ 错题已全部订正通过（原始{X}题 → 当前全部正确）
- 如果 uncorrected_count > 0 且 corrected_count > 0：显示 ⏳ 已订正{corrected_count}题，还有{uncorrected_count}题待订正
- 如果 uncorrected_count > 0 且 corrected_count == 0：显示 📝 {uncorrected_count}道错题未订正

每条记录在得分/正确率/用时的指标行下方，用一行 st.caption() 或 st.markdown() 展示订正状态。

**改动3：列表性能优化**
注意：get_attempt_review_stats() 会在每条记录渲染时被调用。如果学生有几十场考试，会产生 N+1 查询问题。
优化方案：在 db.py 中新增一个批量查询函数 `get_attempts_with_review_stats(user_id, limit, offset)`
一次性 JOIN 查询出所有 attempt 的订正统计，避免循环查询。
返回的每条记录直接包含订正统计字段，app.py 历史列表直接用。

执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理。
```

---

## 批次七：考试详情页增加报告卡片

```
请在考试结果详情页增加一份「考试报告」汇总卡片，确保修改后系统完整可运行：

**改动1：db.py 新增完整的考试报告查询**
确认批次六中实现的 get_attempt_review_stats() 或批量查询函数已经返回了足够的数据。
如果不够，补充以下字段：
- 首次得分（original_score）和首次正确率
- 当前得分（current_score）和当前正确率  
- 提升幅度（improvement = current_score - original_score）
- 错因分布列表 [{reason, cnt}, ...]
- 订正进度（corrected_count / wrong_count）

**改动2：考试结果详情页增加报告卡片**
修改 app.py 中加载历史考试详情的逻辑。目前在 page_student_results() 中，
当 review_attempt_id 被设置时（L732-755），从数据库加载 attempt detail 并调用 _render_result_full() 渲染。

在 _render_result_full() 函数开头（逐题回顾之前）插入一个「📊 考试报告」卡片，
使用 st.container() 包裹，包含以下内容：

卡片布局（用 columns）：
```
┌─────────────────────────────────────────────────┐
│ 📊 考试报告 — 电子协会一级 2025年3月              │
│                                                 │
│ 首次得分        订正后得分        提升           │
│ 7/10 (70%)     9/10 (90%)       +2题 (+20%)    │
│                                                 │
│ 📝 订正进度：▓▓▓▓▓▓▓░░░ 2/3 已完成              │
│                                                 │
│ 📌 错因分布：                                   │
│   粗心马虎      1次  ████                       │
│   知识点未掌握   1次  ████                       │
│   审题不清      1次  ████                       │
└─────────────────────────────────────────────────┘
```

具体实现：
- 第一行用 3 列展示得分对比（首次 / 订正后 / 提升），使用 st.metric()
- 第二行用 st.progress() 展示订正进度条 + 文字说明
- 如果 wrong_count == 0，进度条替换为 🎉 全部正确，无需订正
- 第三行展示错因分布：遍历 error_reasons 列表，每行显示原因名称 + 次数 + 迷你进度条
- 如果还没有错因数据（学生未做订正），显示「📝 尚未完成错题订正」

**改动3：适配三种查看场景**
报告卡片需要在以下场景正确显示：
1. 学生从历史记录点击详情 → 加载历史考试（review_attempt_id 设置）
2. 学生刚提交考试（exam_state == "submitted"）→ 只显示原始得分，不显示订正相关（此时还没有订正数据）
3. 学生完成订正后查看（exam_state == "reviewed"）→ 显示完整报告含订正数据
4. 管理员查看学生考试详情 → 同样显示完整报告

场景2中，报告卡片只显示原始得分和"💡 提交后请完成错题订正以解锁全部解析"的提示，
不显示订正进度和错因分布（因为还没有）。

执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理。
```

---

## 批次八：错题订正入口优化与操作引导

```
请优化错题订正的操作入口，让学生在任何地方都能方便地进入订正流程，
确保修改后系统完整可运行：

**改动1：历史记录列表增加「继续订正」按钮**
修改 `page_student_history()` 中每条考试记录的操作列。
当前只有一个「🔍 详情」按钮。请根据订正状态增加不同按钮：

状态判断逻辑（使用批次六中已有的 review stats 数据）：
- uncorrected_count > 0：显示「📝 继续订正」按钮（主色调）
  - 点击后：设置 st.session_state.attempt_id 为该考试的 attempt_id
  - 设置 st.session_state.exam_state = "reviewing"
  - 设置 st.session_state.page = "📊 考试结果"（会自动进入订正模式）
  - 注意：需要确保 last_time_sec 和 last_result 也能正确恢复
  - 提示：可以复用 _resume_exam 的部分逻辑，但不要重新开始考试，
    只需要让 exam_state = "reviewing" 且 attempt_id 正确，
    _show_review_mode() 会从数据库加载当前状态
- uncorrected_count == 0 且 wrong_count > 0：显示「✅ 已全部订正」+「🔍 详情」
- wrong_count == 0：只显示「🔍 详情」

按钮布局：将原来的 5 列改为 6 列，或把详情按钮和订正按钮放在同一列用两行显示。

**改动2：考试结果页 submitted 状态增加引导话术**
修改 app.py 的 page_student_results() 中 submitted 状态（L778-842）。
当前提示词为「💡 提交后暂不显示答案和解析。请先完成错题订正，订正后将解锁全部解析。」
改为根据错题数量显示不同话术：
- wrong_count >= 5：📚 有 {wrong_count} 道错题，建议逐题订正，掌握知识点后再查看解析
- wrong_count 1-4：💪 只有 {wrong_count} 道错题，花几分钟订正就能解锁全部解析！
- wrong_count == 0：🎉 全部正确！太棒了！

同时把「错题订正」按钮的文案改为更鼓励性的：
- wrong_count >= 5：📝 开始错题订正（{wrong_count}题）
- wrong_count 1-4：📝 订正错题，解锁解析（仅{wrong_count}题）

**改动3：错题本增加「去订正」入口**
修改 `page_student_wrong()` 中未订正题目的展示。当前已显示「🔒 完成错题订正后可解锁正确答案和解析」。
在每条未订正的错题展开后，增加一个「📝 去订正本题」按钮。
点击后跳转到该题的订正页面（如果能定位到具体题目更好，不能则进入该考试的订正列表）。

实现方式：
- 错题数据中已有 attempt_id（从 answers JOIN exam_attempts），把它传出来
- 在 get_wrong_questions() 查询中增加 ea.id as attempt_id
- 点击按钮时：设置 attempt_id 和 exam_state = "reviewing"，跳转到考试结果页

执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理。
```

---

## 使用说明

1. 本文件是 AI_BATCHES.md 的延续，批次编号从六开始
2. 按批次顺序执行，**每个批次一个独立的 AI 对话**
3. 每批次执行完后，运行以下命令确认语法无误：

```bash
cd "/Users/andy/Documents/Andy AI/python study"
python3 -c "import ast; ast.parse(open('app.py').read()); ast.parse(open('db.py').read()); ast.parse(open('auth.py').read()); ast.parse(open('grader.py').read())"
```

4. 确认无语法报错后，启动 Streamlit 验证功能：

```bash
cd "/Users/andy/Documents/Andy AI/python study"
streamlit run app.py
```

5. 用学生账号完整走一遍：考试 → 提交 → 历史记录（检查订正状态）→ 详情（检查报告卡片）→ 订正 → 错题本（检查入口）
6. 每个批次末尾都有「执行完这些提示词后，系统要完整可运行并且不会有任何bug，认真仔细整理」这句话
