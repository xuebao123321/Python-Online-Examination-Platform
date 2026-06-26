"""
Python 在线考试系统 — 多用户版
支持学生和管理员两种角色。
"""

import streamlit as st
import time
import os
import db
import csv_import
import grader
import auth

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="Python 考试系统",
    page_icon="🐍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==================== Session State 初始化 ====================
def init_session():
    defaults = {
        "logged_in": False,
        "user": None,           # 当前用户 dict
        "page": "📝 参加考试",
        "exam_state": "idle",   # 'idle' | 'in_progress' | 'submitted'
        "questions": [],
        "current_idx": 0,
        "answers": {},
        "start_time": None,
        "attempt_id": None,
        "last_result": None,
        "last_time_sec": 0,
        "review_attempt_id": None,
        "show_register": False,
        "admin_view_student": None,
        "confirm_submit": False,
        "review_idx": 0,
        "review_answers": {},
        "review_reasons": {},
        "wrong_qids": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session()


# ==================== 辅助函数 ====================

def format_time(seconds):
    if seconds is None:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def get_elapsed_seconds():
    if st.session_state.start_time is None:
        return 0
    return int(time.time() - st.session_state.start_time)


def reset_exam_state():
    st.session_state.exam_state = "idle"
    st.session_state.questions = []
    st.session_state.current_idx = 0
    st.session_state.answers = {}
    st.session_state.start_time = None
    st.session_state.attempt_id = None
    st.session_state.last_result = None
    st.session_state.last_time_sec = 0


def logout():
    """退出登录"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session()
    st.rerun()


# ==================== 登录 / 注册页 ====================

def page_login():
    """登录和注册页面"""
    st.markdown("<h1 style='text-align:center'>🐍 Python 在线考试系统</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:gray'>中国电子学会 Python 等级考试练习平台</p>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    col_center = st.columns([1, 2, 1])
    with col_center[1]:
        if not st.session_state.show_register:
            # ---- 登录 ----
            st.subheader("🔑 登录")
            username = st.text_input("用户名", placeholder="请输入用户名", key="login_user")
            password = st.text_input("密码", type="password", placeholder="请输入密码", key="login_pwd")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("登录", type="primary", use_container_width=True):
                    success, msg, user = auth.login_user(username, password)
                    if success:
                        st.session_state.logged_in = True
                        st.session_state.user = user
                        st.session_state.page = "📝 参加考试" if user['role'] == 'student' else "📊 仪表盘"
                        st.success(msg)
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)

            with col_btn2:
                if st.button("还没有账号？去注册", use_container_width=True):
                    st.session_state.show_register = True
                    st.rerun()
        else:
            # ---- 注册 ----
            st.subheader("📝 注册新账号")
            reg_user = st.text_input("用户名", placeholder="至少2个字符", key="reg_user")
            reg_pwd = st.text_input("密码", type="password", placeholder="至少4个字符", key="reg_pwd")
            reg_pwd2 = st.text_input("确认密码", type="password", placeholder="再次输入密码", key="reg_pwd2")
            reg_display = st.text_input("显示名称", placeholder="你的姓名或昵称", key="reg_display")
            reg_role = st.selectbox("角色", ["student", "admin", "super_admin"],
                                    format_func=lambda x: "👨‍🎓 学生" if x == "student" else ("👩‍🏫 校区管理员" if x == "admin" else "🔑 超级管理员"),
                                    key="reg_role")

            # 校区选择（非超级管理员需要选校区）
            reg_campus_id = None
            if reg_role != "super_admin":
                campuses = db.get_all_campuses()
                if not campuses:
                    st.warning("⚠️ 还没有校区，请联系超级管理员创建校区")
                else:
                    campus_options = {c['name']: c['id'] for c in campuses}
                    selected_campus = st.selectbox("选择校区", list(campus_options.keys()), key="reg_campus")
                    reg_campus_id = campus_options[selected_campus]
            else:
                st.info("🔑 超级管理员可以管理所有校区，无需选择校区")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("注册", type="primary", use_container_width=True):
                    if reg_pwd != reg_pwd2:
                        st.error("两次输入的密码不一致")
                    else:
                        role = "admin" if reg_role == "super_admin" else reg_role
                        success, msg, uid = auth.register_user(reg_user, reg_pwd, role, reg_display, reg_campus_id)
                        if success:
                            st.success(msg)
                            st.session_state.show_register = False
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(msg)
            with col_btn2:
                if st.button("← 返回登录", use_container_width=True):
                    st.session_state.show_register = False
                    st.rerun()


# ==================== 学生：参加考试 ====================

def page_student_exam():
    st.title("📝 参加考试")
    user = st.session_state.user

    if st.session_state.exam_state == "idle":
        # 检查未完成的考试
        unsubmitted = db.get_unsubmitted_attempt(user['id'])
        if unsubmitted:
            bank = db.get_bank_by_id(unsubmitted["bank_id"])
            if bank:
                st.warning(f"⚠️ 检测到一场未完成的考试：**{bank['name']}**")
                c1, c2, _ = st.columns(3)
                with c1:
                    if st.button("▶️ 继续考试", type="primary", use_container_width=True):
                        _resume_exam(unsubmitted)
                        return
                with c2:
                    if st.button("🗑️ 放弃", use_container_width=True):
                        db.abandon_attempt(unsubmitted["id"])
                        st.rerun()
                st.divider()

        _show_exam_selector(user)

    elif st.session_state.exam_state == "in_progress":
        _show_exam_questions()

    elif st.session_state.exam_state == "submitted":
        st.session_state.page = "📊 考试结果"
        st.rerun()


def _show_exam_selector(user):
    levels = db.get_all_levels()
    if not levels:
        st.info("📚 还没有题库，请联系管理员上传。")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_level = st.selectbox("选择级别", levels)
    with col2:
        years = db.get_years_for_level(selected_level)
        if years:
            selected_year = st.selectbox("选择年月", years)
        else:
            st.warning("该级别没有可用题库")
            return
    with col3:
        if selected_level and years:
            bank = db.get_bank_by_level_year(selected_level, selected_year)
            if bank:
                count = db.get_question_count(bank["id"])
                st.metric("题目数量", f"{count} 题")

    if selected_level and years:
        st.divider()
        bank = db.get_bank_by_level_year(selected_level, selected_year)
        qs = db.get_questions(bank["id"])
        qtype_summary = {}
        for q in qs:
            qtype_summary[q["qtype"]] = qtype_summary.get(q["qtype"], 0) + 1
        qtype_text = "、".join([f"{k} {v}道" for k, v in qtype_summary.items()])
        st.markdown(f"**📋 {selected_level} {selected_year}** ｜ 共 {len(qs)} 道题（{qtype_text}）")
        st.markdown("⏱️ 逐题作答，可前进后退，提交后自动判分。")
        if st.button("🚀 开始考试", type="primary", use_container_width=True):
            _start_exam(bank, user)


def _start_exam(bank, user):
    questions = db.get_questions(bank["id"])
    if not questions:
        st.error("题库为空！")
        return
    attempt_id = db.create_attempt(user['id'], bank["id"], len(questions))
    st.session_state.exam_state = "in_progress"
    st.session_state.questions = questions
    st.session_state.current_idx = 0
    st.session_state.answers = {}
    st.session_state.start_time = time.time()
    st.session_state.attempt_id = attempt_id
    st.rerun()


def _resume_exam(attempt):
    bank = db.get_bank_by_id(attempt["bank_id"])
    if not bank:
        st.error("题库已删除。")
        db.abandon_attempt(attempt["id"])
        st.rerun()
        return
    questions = db.get_questions(bank["id"])
    if not questions:
        st.error("题库题目已被删除，无法恢复考试。")
        db.abandon_attempt(attempt["id"])
        st.rerun()
        return
    st.session_state.exam_state = "in_progress"
    st.session_state.questions = questions
    st.session_state.current_idx = 0
    st.session_state.answers = {}
    st.session_state.start_time = time.time()
    st.session_state.attempt_id = attempt["id"]
    st.rerun()


def _show_exam_questions():
    questions = st.session_state.questions
    total = len(questions)
    idx = st.session_state.current_idx
    current_q = questions[idx]
    elapsed = get_elapsed_seconds()
    answered_count = len([a for a in st.session_state.answers.values() if a])

    # 顶部状态栏
    ct1, ct2, ct3, ct4 = st.columns([2, 1, 1, 1])
    with ct1:
        st.progress((idx + 1) / total, f"第 {idx + 1} / {total} 题")
    with ct2:
        st.metric("已答", f"{answered_count}/{total}")
    with ct3:
        st.metric("⏱️ 用时", format_time(elapsed))
    with ct4:
        st.metric("⏳ 剩余", format_time(max(0, total * 60 - elapsed)))
    st.divider()

    # 题目
    qtype_badge = "🔵 单选题" if current_q["qtype"] == "单选" else "🟢 判断题"
    st.markdown(f"### {qtype_badge} · 第 {idx + 1} 题")
    st.markdown(f"**{current_q['question']}**")

    qid = current_q["id"]
    current_answer = st.session_state.answers.get(qid, "")

    if current_q["qtype"] == "单选":
        choice_labels, choice_map = [], {}
        for label, key in [("A", "option_a"), ("B", "option_b"), ("C", "option_c"), ("D", "option_d")]:
            if current_q.get(key):
                text = f"{label}. {current_q[key]}"
                choice_labels.append(text)
                choice_map[text] = label
        current_text = next((t for t, l in choice_map.items() if l == current_answer), None)
        idx_default = choice_labels.index(current_text) if current_text in choice_labels else None
        selected = st.radio("请选择答案：", choice_labels, index=idx_default, key=f"q_{qid}")
        if selected:
            st.session_state.answers[qid] = choice_map[selected]
    else:
        tf_labels = ["对 ✅", "错 ❌"]
        tf_map = {"对 ✅": "对", "错 ❌": "错"}
        current_index = 1 if current_answer == "错" else (0 if current_answer == "对" else None)
        selected = st.radio("请判断：", tf_labels, index=current_index, key=f"q_{qid}", horizontal=True)
        if selected:
            st.session_state.answers[qid] = tf_map[selected]

    # 当前题作答状态提示
    if not st.session_state.answers.get(qid):
        st.caption("⚠️ 请选择一个答案")

    st.divider()

    # 导航
    nc1, nc2, nc3, nc4 = st.columns([1, 1, 1, 1])
    with nc1:
        if st.button("⬅️ 上一题", use_container_width=True, disabled=(idx == 0)):
            st.session_state.current_idx -= 1
            st.rerun()
    with nc2:
        if st.button("下一题 ➡️", use_container_width=True, type="primary", disabled=(idx == total - 1)):
            st.session_state.current_idx += 1
            st.rerun()
    with nc4:
        unanswered = total - answered_count
        label = "📩 提交试卷" if unanswered == 0 else f"📩 提交（{unanswered}题未答）"
        submit_clicked = st.button(label, type="primary", use_container_width=True)

        # 提交确认：有未答题时弹出确认
        if submit_clicked:
            if unanswered > 0 and not st.session_state.get("confirm_submit", False):
                st.session_state.confirm_submit = True
                st.warning(f"⚠️ 还有 {unanswered} 道题未作答！未答题目将计 0 分。")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ 确认提交，不再检查", type="primary", use_container_width=True):
                        st.session_state.confirm_submit = False
                        _submit_exam(questions, elapsed)
                with c2:
                    if st.button("↩️ 继续答题", use_container_width=True):
                        st.session_state.confirm_submit = False
                        st.rerun()
            else:
                st.session_state.confirm_submit = False
                _submit_exam(questions, elapsed)


def _submit_exam(questions, elapsed):
    result = grader.grade_all(questions, st.session_state.answers)
    db.submit_attempt(st.session_state.attempt_id, result["score"], elapsed)
    answers_batch = [
        (st.session_state.attempt_id, r["question"]["id"], r["given_answer"], 1 if r["is_correct"] else 0)
        for r in result["results"]
    ]
    db.save_answers_batch(answers_batch)
    st.session_state.last_result = result
    st.session_state.last_time_sec = elapsed
    st.session_state.exam_state = "submitted"  # 首次提交，不展示解析
    st.session_state.wrong_qids = [r["question"]["id"] for r in result["results"] if not r["is_correct"]]
    st.session_state.review_answers = {}
    st.session_state.review_reasons = {}
    st.rerun()


# ==================== 考试结果（学生+共用） ====================

def page_student_results():
    st.title("📊 考试结果")
    user = st.session_state.user
    is_admin_view = user['role'] == 'admin'

    result = st.session_state.last_result
    time_sec = st.session_state.last_time_sec
    exam_state = st.session_state.exam_state

    # 从数据库重新加载结果（历史回顾 / 订正完成后）
    if result is None and st.session_state.review_attempt_id:
        detail = db.get_attempt_detail(st.session_state.review_attempt_id)
        if detail:
            result = {"score": detail["score"], "total": detail["total"], "results": [
                {"question": a, "given_answer": a["given_answer"], "is_correct": bool(a["is_correct"])}
                for a in detail["answers"]
            ]}
            time_sec = detail.get("time_sec", 0)
            _render_result_full(result, time_sec, detail.get("bank_name", ""), detail.get("submitted_at", ""))
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔄 重新考试", use_container_width=True, type="primary"):
                    reset_exam_state()
                    st.session_state.last_result = None
                    st.session_state.review_attempt_id = None
                    st.session_state.page = "📝 参加考试"
                    st.rerun()
            with c2:
                if st.button("↩️ 返回", use_container_width=True):
                    st.session_state.review_attempt_id = None
                    st.session_state.exam_state = "idle"
                    st.rerun()
            return

    if result is None:
        st.info("还没有考试结果，去「参加考试」完成一次考试吧！")
        return

    # ---- 订正模式 ----
    if exam_state == "reviewing":
        _show_review_mode()
        return

    # ---- 已订正完成 / 管理员查看 ----
    if exam_state == "reviewed" or is_admin_view:
        _render_result_full(result, time_sec)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 重新考试", use_container_width=True, type="primary"):
                reset_exam_state()
                st.session_state.last_result = None
                st.session_state.page = "📝 参加考试"
                st.rerun()
        return

    # ---- 首次提交：只显示得分和 ✅❌，不给答案 ----
    score, total = result["score"], result["total"]
    percentage = round(score / total * 100, 1) if total > 0 else 0
    emoji = "🏆" if percentage >= 90 else ("👍" if percentage >= 75 else ("💪" if percentage >= 60 else "📚"))

    st.markdown(f"## {emoji} 得分：{score} / {total}（{percentage}%）")
    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.metric("得分", f"{score} / {total}")
    with mc2:
        st.metric("正确率", f"{percentage}%")
    with mc3:
        st.metric("用时", format_time(time_sec))
    st.progress(score / total if total > 0 else 0)

    st.divider()
    st.subheader("📋 答题情况")
    st.info("💡 提交后暂不显示答案和解析。请先完成错题订正，订正后将解锁全部解析。")

    wrong_count = 0
    for i, r in enumerate(result["results"]):
        icon = "✅" if r["is_correct"] else "❌"
        q = r["question"]
        if not r["is_correct"]:
            wrong_count += 1
        with st.expander(f"{icon} 第 {i+1} 题 — {q['question'][:60]}{'...' if len(q['question'])>60 else ''}"):
            st.markdown(f"**题型：**{'🔵 单选题' if q['qtype']=='单选' else '🟢 判断题'}")
            st.markdown(f"**题目：**{q['question']}")
            st.markdown(f"**你的答案：**{r['given_answer'] or '未作答'}")
            if r["is_correct"]:
                st.success("✅ 回答正确")
            else:
                st.error("❌ 回答错误")

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        if wrong_count > 0:
            if st.button(f"📝 错题订正（{wrong_count}题）", type="primary", use_container_width=True):
                st.session_state.exam_state = "reviewing"
                st.session_state.review_idx = 0
                st.rerun()
        else:
            if st.button("🎉 查看全部解析", type="primary", use_container_width=True):
                st.session_state.exam_state = "reviewed"
                st.rerun()
    with c2:
        if st.button("🔄 重新考试", use_container_width=True):
            reset_exam_state()
            st.session_state.last_result = None
            st.session_state.page = "📝 参加考试"
            st.rerun()


def _show_review_mode():
    """错题订正模式"""
    st.subheader("📝 错题订正")
    st.caption("请重新作答错题，并选择错误原因。完成后将解锁全部解析。")

    result = st.session_state.last_result
    wrong_results = [r for r in result["results"] if not r["is_correct"]]
    total_wrong = len(wrong_results)
    idx = st.session_state.get("review_idx", 0)

    if idx >= total_wrong:
        # 订正完成，提交
        _submit_review()
        return

    r = wrong_results[idx]
    q = r["question"]
    qid = q["id"]

    st.progress((idx + 1) / total_wrong, f"错题 {idx + 1} / {total_wrong}")
    st.markdown(f"### 第 {idx+1} 题")
    st.markdown(f"**{q['question']}**")

    if q["qtype"] == "单选":
        choice_labels, choice_map = [], {}
        for label, key in [("A", "option_a"), ("B", "option_b"), ("C", "option_c"), ("D", "option_d")]:
            if q.get(key):
                text = f"{label}. {q[key]}"
                choice_labels.append(text)
                choice_map[text] = label
        prev = st.session_state.review_answers.get(qid, "")
        prev_text = next((t for t, l in choice_map.items() if l == prev), None)
        idx_default = choice_labels.index(prev_text) if prev_text in choice_labels else None
        selected = st.radio("你的新答案：", choice_labels, index=idx_default, key=f"review_q_{qid}")
        if selected:
            st.session_state.review_answers[qid] = choice_map[selected]
    else:
        tf_labels = ["对 ✅", "错 ❌"]
        tf_map = {"对 ✅": "对", "错 ❌": "错"}
        prev = st.session_state.review_answers.get(qid, "")
        cur_idx = 1 if prev == "错" else (0 if prev == "对" else None)
        selected = st.radio("你的新答案：", tf_labels, index=cur_idx, key=f"review_q_{qid}", horizontal=True)
        if selected:
            st.session_state.review_answers[qid] = tf_map[selected]

    st.markdown("**错误原因：**（必选）")
    reasons = ["粗心马虎", "知识点未掌握", "没有思路", "审题不清", "其他"]
    reason = st.selectbox("选择错误原因", [""] + reasons, key=f"reason_{qid}")
    if reason:
        st.session_state.review_reasons[qid] = reason

    st.divider()
    nc1, nc2, nc3 = st.columns([1, 1, 2])
    with nc1:
        if idx > 0 and st.button("⬅️ 上一题", use_container_width=True):
            st.session_state.review_idx -= 1
            st.rerun()
    with nc2:
        can_next = qid in st.session_state.review_answers and qid in st.session_state.review_reasons
        if st.button("下一题 ➡️", use_container_width=True, type="primary", disabled=not can_next):
            if not can_next:
                st.warning("请选择答案和错误原因")
            else:
                st.session_state.review_idx += 1
                st.rerun()
    with nc3:
        if idx == total_wrong - 1:
            all_done = all(
                qid in st.session_state.review_answers and qid in st.session_state.review_reasons
                for qid in [wr["question"]["id"] for wr in wrong_results]
            )
            if st.button("📩 提交订正", type="primary", use_container_width=True, disabled=not all_done):
                _submit_review()


def _submit_review():
    """提交订正"""
    result = st.session_state.last_result
    wrong_qids = st.session_state.wrong_qids
    review_answers = st.session_state.review_answers
    review_reasons = st.session_state.review_reasons
    attempt_id = st.session_state.attempt_id

    # 构建订正数据
    review_list = []
    for qid in wrong_qids:
        ra = review_answers.get(qid, "")
        rr = review_reasons.get(qid, "")
        # 判断订正是否正确
        correct_q = next((r["question"] for r in result["results"] if r["question"]["id"] == qid), None)
        is_correct = grader.grade_single(correct_q, ra) if correct_q else False
        review_list.append((attempt_id, qid, ra, 1 if is_correct else 0, rr))

    db.save_review_answers(review_list)

    # 更新考试分数（订正后重新计算）
    # 获取所有答案（首次 + 订正）
    detail = db.get_attempt_detail(attempt_id)
    if detail:
        new_score = sum(1 for a in detail["answers"] if a["is_correct"])
        db.submit_attempt(attempt_id, new_score, st.session_state.last_time_sec)

    st.session_state.exam_state = "reviewed"
    st.session_state.review_attempt_id = attempt_id  # 标记从数据库重新加载
    st.session_state.last_result = None
    st.rerun()


def _render_result_full(result, time_sec, bank_name="", submitted_at=""):
    """渲染完整结果（含答案和解析），管理员和学生订正后可见"""
    if not result:
        st.info("暂无考试结果数据")
        return
    score, total = result["score"], result["total"]
    percentage = round(score / total * 100, 1) if total > 0 else 0

    emoji = "🏆" if percentage >= 90 else ("👍" if percentage >= 75 else ("💪" if percentage >= 60 else "📚"))
    comment = "非常棒！" if percentage >= 90 else ("做得不错！" if percentage >= 75 else ("继续加油！" if percentage >= 60 else "别灰心！"))

    st.markdown(f"## {emoji} {comment}")
    if bank_name:
        st.caption(f"考试：{bank_name} ｜ {submitted_at}")

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.metric("得分", f"{score} / {total}")
    with mc2:
        st.metric("正确率", f"{percentage}%")
    with mc3:
        st.metric("用时", format_time(time_sec))
    st.progress(score / total if total > 0 else 0)
    st.divider()

    st.subheader("📋 逐题回顾")
    for i, r in enumerate(result["results"]):
        q = r["question"]
        icon = "✅" if r["is_correct"] else "❌"
        # 如果有订正答案则显示订正后的，否则显示首次答案
        review_ans = q.get("review_answer", "")
        given = review_ans if review_ans else (r["given_answer"] or "（未作答）")
        error_reason = q.get("error_reason", "")

        title = f"{icon} 第 {i+1} 题 — {q['question'][:50]}{'...' if len(q['question'])>50 else ''}"
        if error_reason:
            title += f"  [{error_reason}]"

        with st.expander(title):
            st.markdown(f"**题型：**{'🔵 单选题' if q['qtype']=='单选' else '🟢 判断题'}")
            st.markdown(f"**题目：** {q['question']}")
            if q["qtype"] == "单选":
                for label, key in [("A", "option_a"), ("B", "option_b"), ("C", "option_c"), ("D", "option_d")]:
                    if q.get(key):
                        mark = ""
                        if label == q["answer"]:
                            mark = " ✅（正确答案）"
                        elif label == given:
                            mark = " ❌（你的答案）"
                        st.markdown(f"　**{label}**) {q[key]}{mark}")
            else:
                st.markdown(f"　**你的答案：** {given}")
                st.markdown(f"　**正确答案：** {q['answer']}")
            if error_reason:
                st.markdown(f"　**错误原因：** {error_reason}")
            if q.get("explanation"):
                st.markdown(f"💡 **解析：** {q['explanation']}")


# ==================== 学生：历史记录 ====================

def page_student_history():
    st.title("📜 历史记录")
    user = st.session_state.user
    attempts = db.get_attempts(user_id=user['id'])

    if not attempts:
        st.info("还没有考试记录。去「参加考试」完成第一次考试吧！🚀")
        return

    total_exams = len(attempts)
    avg_pct = round(sum(a["score"] / max(a["total"], 1) * 100 for a in attempts) / total_exams, 1) if total_exams > 0 else 0
    best_pct = round(max(a["score"] / max(a["total"], 1) * 100 for a in attempts), 1) if total_exams > 0 else 0

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        st.metric("考试次数", total_exams)
    with sc2:
        st.metric("平均正确率", f"{avg_pct}%")
    with sc3:
        st.metric("最高正确率", f"{best_pct}%")
    st.divider()

    for a in attempts:
        pct = round(a["score"] / a["total"] * 100, 1) if a["total"] > 0 else 0
        icon = "🟢" if pct >= 90 else ("🟡" if pct >= 60 else "🔴")
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 2])
            with c1:
                st.markdown(f"{icon} **{a['bank_name']}**")
                st.caption(a.get("submitted_at", ""))
            with c2:
                st.metric("得分", f"{a['score']}/{a['total']}")
            with c3:
                st.metric("正确率", f"{pct}%")
            with c4:
                st.metric("用时", format_time(a.get("time_sec", 0)))
            with c5:
                if st.button("🔍 详情", key=f"h_{a['id']}", use_container_width=True):
                    st.session_state.review_attempt_id = a["id"]
                    st.session_state.last_result = None
                    st.session_state.page = "📊 考试结果"
                    st.rerun()
            st.divider()


# ==================== 学生：错题本 ====================

def page_student_wrong():
    st.title("❌ 错题本")
    user = st.session_state.user
    wrong_qs = db.get_wrong_questions(user['id'], limit=100)

    if not wrong_qs:
        st.success("🎉 太棒了！你没有错题记录。")
        return

    st.markdown(f"共 **{len(wrong_qs)}** 道错题（去重后），按最近考试时间排列：")
    st.divider()

    for i, q in enumerate(wrong_qs):
        icon = "🔵" if q["qtype"] == "单选" else "🟢"
        with st.expander(f"{icon} {q['qtype']} - {q['question'][:60]}{'...' if len(q['question'])>60 else ''}"):
            st.markdown(f"**题目：**{q['question']}")
            if q["qtype"] == "单选":
                for label, key in [("A", "option_a"), ("B", "option_b"), ("C", "option_c"), ("D", "option_d")]:
                    if q.get(key):
                        mark = " ✅" if label == q["answer"] else (" ❌ 你的答案" if label == q.get("given_answer") else "")
                        st.markdown(f"　**{label}**) {q[key]}{mark}")
            else:
                st.markdown(f"　你的答案：**{q.get('given_answer', '未作答')}**")
                st.markdown(f"　正确答案：**{q['answer']}**")
            if q.get("explanation"):
                st.info(f"💡 **解析：**{q['explanation']}")


# ==================== 管理员：上传题库 ====================

def page_admin_upload():
    st.title("📤 上传题库")

    with st.expander("📋 CSV 文件格式说明", expanded=False):
        st.markdown("""
        **必需列名：** `序号,题型,题目,选项A,选项B,选项C,选项D,正确答案,解析`
        - **题型**：`单选` 或 `判断`
        - **正确答案**：单选填 A/B/C/D，判断填 对/错
        - **文件编码**：UTF-8
        """)

    col1, col2 = st.columns([2, 1])
    with col1:
        # 模板下载
        sm1, sm2 = st.columns([1, 2])
        with sm1:
            template_path = os.path.join(os.path.dirname(__file__), "sample_questions", "考试题库模板.csv")
            with open(template_path, "rb") as f:
                st.download_button("📄 下载 CSV 模板", f, "考试题库模板.csv", "text/csv")
        with sm2:
            st.caption("用 Excel 编辑后另存为 CSV")

        st.divider()
        st.markdown("##### 📤 上传题库文件")
        uploaded_file = st.file_uploader("选择 CSV 文件", type=["csv"])
        st.divider()
        st.markdown("##### 🏷️ 设置题库归属")

        sc1, sc2 = st.columns(2)
        with sc1:
            level_options = ["电子协会一级", "电子协会二级", "电子协会三级", "其他（自定义）"]
            level_select = st.selectbox("级别名称", level_options)
            if level_select == "其他（自定义）":
                level = st.text_input("输入自定义名称", placeholder="例如：自定义题库", key="custom_level")
            else:
                level = level_select
        with sc2:
            year_months = []
            for y in range(2010, 2027):
                for m in [3, 6, 9, 12]:
                    year_months.append(f"{y}年{m}月")
            year_months.reverse()
            year = st.selectbox("年月", year_months)

        import_btn = st.button("📥 导入题库", type="primary", use_container_width=True)

    with col2:
        st.subheader("📚 已有题库")
        banks = db.get_all_banks()
        user = st.session_state.user
        is_super = user['role'] == 'admin' and user.get('campus_id') is None

        # 超级管理员：待审批删除
        if is_super:
            delete_reqs = db.get_delete_requests()
            if delete_reqs:
                st.warning(f"⏳ {len(delete_reqs)} 个删除申请待审批")
                for dr in delete_reqs:
                    with st.container():
                        st.markdown(f"🗑️ **{dr['name']}**")
                        st.caption(f"申请者: {dr.get('uploader_name','?')} ｜ {dr.get('campus_name','?')}")
                        ca, cb = st.columns(2)
                        with ca:
                            if st.button("✅ 同意删除", key=f"approve_{dr['id']}"):
                                db.approve_delete_bank(dr['id'])
                                st.rerun()
                        with cb:
                            if st.button("❌ 拒绝", key=f"reject_{dr['id']}"):
                                db.reject_delete_bank(dr['id'])
                                st.rerun()
                        st.divider()
                st.divider()

        if banks:
            for b in banks:
                count = db.get_question_count(b["id"])
                status = ""
                if b.get('delete_requested') == 1:
                    status = " ⏳(待审批删除)"
                st.markdown(f"**{b['name']}**  [{count}题]{status}")
                st.caption(f"上传者: {b.get('uploader_name','?')} ｜ 校区: {b.get('campus_name','?')} ｜ {b['created_at']}")

                # 删除 / 申请删除
                if is_super:
                    if st.button("🗑️ 删除", key=f"del_{b['id']}"):
                        db.delete_bank(b["id"])
                        st.rerun()
                else:
                    if b.get('delete_requested', 0) == 0:
                        if st.button("📩 申请删除", key=f"req_del_{b['id']}"):
                            db.request_delete_bank(b['id'])
                            st.success("已提交删除申请，等待超级管理员审批")
                            time.sleep(1)
                            st.rerun()
                st.divider()
        else:
            st.info("还没有题库")

    if import_btn:
        if uploaded_file is None:
            st.error("请先选择 CSV 文件。")
            return
        questions, errors = csv_import.parse_csv(uploaded_file)
        for err in errors:
            if err.startswith("❌"):
                st.error(err)
            else:
                st.warning(err)
        if not questions:
            return
        existing = db.get_bank_by_level_year(level.strip(), year)
        bank_name = f"{level.strip()} {year}"
        uid = user['id']
        cid = user.get('campus_id')
        if existing:
            st.warning(f"题库「{bank_name}」已存在，将替换原有题目。")
            c_a, c_b = st.columns(2)
            with c_a:
                if st.button("✅ 确认替换", type="primary"):
                    db.replace_bank(existing["id"], bank_name, level.strip(), year, uid, cid)
                    _do_import(existing["id"], questions, bank_name)
            with c_b:
                if st.button("❌ 取消"):
                    st.rerun()
        else:
            bank_id = db.create_bank(bank_name, level.strip(), year, uid, cid)
            if bank_id:
                _do_import(bank_id, questions, bank_name)
            else:
                st.error("创建题库失败")


def _do_import(bank_id, questions, bank_name):
    batch = [(q["seq"], q["qtype"], q["question"], q["option_a"], q["option_b"],
              q["option_c"], q["option_d"], q["answer"], q["explanation"]) for q in questions]
    db.insert_questions_batch(bank_id, batch)
    qtype_counts = {}
    for q in questions:
        qtype_counts[q["qtype"]] = qtype_counts.get(q["qtype"], 0) + 1
    detail = "、".join([f"{k} {v}道" for k, v in qtype_counts.items()])
    st.success(f"✅ 题库「{bank_name}」导入成功！共 {len(questions)} 道题（{detail}）")
    st.balloons()
    time.sleep(2)
    st.rerun()


# ==================== 管理员：仪表盘 ====================

def page_admin_dashboard():
    st.title("📊 管理员仪表盘")
    campus_id = st.session_state.user.get('campus_id')
    stats = db.get_admin_stats(campus_id)

    # 概览指标
    st.subheader("📈 整体概览")
    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.metric("👨‍🎓 学生总数", stats['total_students'])
    with mc2:
        st.metric("📝 考试总次数", stats['total_exams'])
    with mc3:
        st.metric("📊 平均正确率", f"{stats['avg_score']}%" if stats['avg_score'] else "N/A")
    with mc4:
        active_students = len([s for s in stats['student_stats'] if s['exam_count'] > 0])
        st.metric("✅ 活跃学生", active_students)

    st.divider()

    # 学生统计表
    st.subheader("👥 学生考试统计")
    if stats['student_stats']:
        student_data = []
        for s in stats['student_stats']:
            avg = round(s['avg_score'], 1) if s['avg_score'] else 0
            student_data.append({
                "学生": s['display_name'],
                "用户名": s['username'],
                "考试次数": s['exam_count'],
                "平均正确率": f"{avg}%",
                "最近考试": s['last_exam'] or "暂无",
            })
        st.dataframe(student_data, use_container_width=True, hide_index=True)
    else:
        st.info("还没有学生数据。")

    st.divider()

    # 错因统计
    st.subheader("🔍 错因分布统计")
    error_stats = db.get_error_reason_stats(campus_id)
    if error_stats:
        error_data = [{"错误原因": e['error_reason'], "次数": e['cnt']} for e in error_stats]
        st.dataframe(error_data, use_container_width=True, hide_index=True)
        # 简易柱状图
        total_errors = sum(e['cnt'] for e in error_stats)
        for e in error_stats:
            pct = round(e['cnt'] / total_errors * 100, 1) if total_errors > 0 else 0
            st.markdown(f"**{e['error_reason']}**：{e['cnt']} 次 ({pct}%)")
            st.progress(e['cnt'] / total_errors if total_errors > 0 else 0)
    else:
        st.info("暂无错因数据（学生尚未完成错题订正）")

    st.divider()

    # 题库统计
    st.subheader("📚 题库使用统计")
    if stats['exam_stats']:
        exam_data = []
        for e in stats['exam_stats']:
            avg = round(e['avg_score'], 1) if e['avg_score'] else 0
            best = round(e['best_score'], 1) if e['best_score'] else 0
            worst = round(e['worst_score'], 1) if e['worst_score'] else 0
            exam_data.append({
                "题库": e['bank_name'],
                "考试人次": e['attempt_count'],
                "平均分": f"{avg}%",
                "最高分": f"{best}%",
                "最低分": f"{worst}%",
            })
        st.dataframe(exam_data, use_container_width=True, hide_index=True)
    else:
        st.info("还没有考试记录。")


# ==================== 管理员：学生管理 ====================

def page_admin_students():
    st.title("👥 学生管理")
    students = db.get_all_students(st.session_state.user.get('campus_id'))

    if not students:
        st.info("还没有注册的学生账号。")
        return

    for s in students:
        detail = db.get_student_detail(s['id'])
        attempts = detail['attempts']
        exam_count = len(attempts)
        avg_pct = round(sum(a['score'] / max(a['total'], 1) * 100 for a in attempts) / exam_count, 1) if exam_count > 0 else 0

        with st.container():
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
            with c1:
                st.markdown(f"**{s['display_name']}**  (@{s['username']})")
                st.caption(f"注册时间：{s['created_at']}")
            with c2:
                st.metric("考试次数", exam_count)
            with c3:
                st.metric("平均分", f"{avg_pct}%")
            with c4:
                last = attempts[0]['submitted_at'] if attempts else "暂无"
                st.caption(f"最近：{last}")
            with c5:
                if st.button("📋 查看详情", key=f"stu_{s['id']}", use_container_width=True):
                    st.session_state.admin_view_student = s['id']
                    st.session_state.page = "👤 学生详情"
                    st.rerun()
            st.divider()


def page_admin_student_detail():
    st.title("👤 学生详情")
    sid = st.session_state.admin_view_student
    if not sid:
        st.info("请从学生列表中选择。")
        return

    detail = db.get_student_detail(sid)
    user = detail['user']
    attempts = detail['attempts']

    if not user:
        st.error("学生不存在。")
        return

    st.markdown(f"## {user['display_name']} (@{user['username']})")
    st.caption(f"注册时间：{user['created_at']}")

    exam_count = len(attempts)
    avg_pct = round(sum(a['score'] / a['total'] * 100 for a in attempts) / exam_count, 1) if exam_count > 0 else 0
    best_pct = round(max(a['score'] / max(a['total'], 1) * 100 for a in attempts), 1) if exam_count > 0 else 0

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.metric("考试次数", exam_count)
    with mc2:
        st.metric("平均正确率", f"{avg_pct}%")
    with mc3:
        st.metric("最高正确率", f"{best_pct}%")
    st.divider()

    if not attempts:
        st.info("该学生还没有考试记录。")
    else:
        for a in attempts:
            pct = round(a["score"] / a["total"] * 100, 1) if a["total"] > 0 else 0
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 2])
                with c1:
                    st.markdown(f"**{a['bank_name']}**")
                    st.caption(a.get("submitted_at", ""))
                with c2:
                    st.metric("得分", f"{a['score']}/{a['total']}")
                with c3:
                    st.metric("正确率", f"{pct}%")
                with c4:
                    st.metric("用时", format_time(a.get("time_sec", 0)))
                with c5:
                    if st.button("🔍 查看", key=f"as_{a['id']}", use_container_width=True):
                        st.session_state.review_attempt_id = a["id"]
                        st.session_state.last_result = None
                        st.session_state.page = "📊 考试结果"
                        st.rerun()
                st.divider()

    if st.button("↩️ 返回学生列表", use_container_width=True):
        st.session_state.admin_view_student = None
        st.session_state.page = "👥 学生管理"
        st.rerun()


def page_admin_records():
    """管理员查看所有考试记录"""
    st.title("📜 全部考试记录")
    attempts = db.get_attempts(campus_id=st.session_state.user.get('campus_id'))

    if not attempts:
        st.info("还没有考试记录。")
        return

    total = len(attempts)
    avg_pct = round(sum(a["score"] / max(a["total"], 1) * 100 for a in attempts) / total, 1) if total > 0 else 0
    mc1, mc2 = st.columns(2)
    with mc1:
        st.metric("总考试次数", total)
    with mc2:
        st.metric("总平均分", f"{avg_pct}%")
    st.divider()

    for a in attempts:
        pct = round(a["score"] / a["total"] * 100, 1) if a["total"] > 0 else 0
        icon = "🟢" if pct >= 90 else ("🟡" if pct >= 60 else "🔴")
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 2])
            with c1:
                st.markdown(f"{icon} **{a.get('user_name', '?')}** — {a['bank_name']}")
                st.caption(a.get("submitted_at", ""))
            with c2:
                st.metric("得分", f"{a['score']}/{a['total']}")
            with c3:
                st.metric("正确率", f"{pct}%")
            with c4:
                st.metric("用时", format_time(a.get("time_sec", 0)))
            with c5:
                if st.button("🔍", key=f"ar_{a['id']}", use_container_width=True):
                    st.session_state.review_attempt_id = a["id"]
                    st.session_state.last_result = None
                    st.session_state.page = "📊 考试结果"
                    st.rerun()
            st.divider()


# ==================== 超级管理员：用户管理 ====================

def page_admin_users():
    st.title("🔧 用户管理")
    st.caption("查看所有用户、重置密码")

    try:
        recovery_key = st.secrets["recovery_key"]
    except KeyError:
        st.error("⚠️ 未配置恢复密钥。请在 Streamlit Cloud → Settings → Secrets 中设置 recovery_key")
        recovery_key = ""

    # 用户列表
    st.subheader("👁️ 所有用户")
    users = db.get_all_users()
    if users:
        data = [{
            "用户名": u['username'], "显示名": u['display_name'],
            "角色": "超级管理员" if (u['role']=='admin' and u.get('campus_id') is None)
                    else ("校区管理员" if u['role']=='admin' else "学生"),
            "校区ID": u.get('campus_id', '全部'),
            "注册时间": u['created_at']
        } for u in users]
        st.dataframe(data, use_container_width=True, hide_index=True)
    else:
        st.info("还没有用户")

    st.divider()

    # 重置密码
    st.subheader("🔄 重置用户密码")
    st.caption("忘记密码时，超级管理员可在此重置")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        reset_user = st.text_input("用户名", key="admin_reset_user")
    with col_b:
        reset_pwd = st.text_input("新密码", type="password", key="admin_reset_pwd")
    with col_c:
        st.caption("")  # spacer
        st.caption("")
        if st.button("🔄 重置密码", use_container_width=True, type="primary"):
            if reset_user and reset_pwd:
                ok, msg = auth.reset_password(reset_user, reset_pwd, recovery_key, recovery_key)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.error("请输入用户名和新密码")


# ==================== 超级管理员：校区管理 ====================

def page_admin_campuses():
    st.title("🏫 校区管理")

    user = st.session_state.user
    if not (user['role'] == 'admin' and user.get('campus_id') is None):
        st.error("仅超级管理员可访问")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        new_campus = st.text_input("新建校区名称", placeholder="例如：北京校区、上海校区")
        if st.button("➕ 创建校区", type="primary"):
            if new_campus.strip():
                cid = db.create_campus(new_campus.strip())
                if cid:
                    st.success(f"✅ 校区「{new_campus.strip()}」创建成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("校区名称已存在")
            else:
                st.error("请输入校区名称")

    st.divider()
    st.subheader("📋 已有校区")
    campuses = db.get_all_campuses()
    if not campuses:
        st.info("还没有校区，请创建第一个校区。")
    else:
        for c in campuses:
            # 统计该校区人数
            students = db.get_all_students(c['id'])
            admins = [u for u in db.get_all_users(c['id']) if u['role'] == 'admin']
            with st.container():
                cc1, cc2, cc3, cc4 = st.columns([3, 1, 1, 1])
                with cc1:
                    st.markdown(f"**🏫 {c['name']}**")
                    st.caption(f"创建于 {c['created_at']}")
                with cc2:
                    st.metric("👨‍🎓 学生", len(students))
                with cc3:
                    st.metric("👩‍🏫 管理员", len(admins))
                with cc4:
                    if st.button("🗑️ 删除", key=f"del_campus_{c['id']}", use_container_width=True):
                        db.delete_campus(c['id'])
                        st.rerun()
                st.divider()


# ==================== 主程序 ====================

def main():
    # ---- 确保默认超级管理员存在 ----
    default_user = st.secrets.get("default_admin_user", "admin")
    default_pass = st.secrets.get("default_admin_pass", "xuxuchang123")
    auth.ensure_default_admin(default_user, default_pass)

    # ---- 未登录 → 显示登录页 ----
    if not st.session_state.logged_in:
        page_login()
        return

    user = st.session_state.user
    is_admin = user['role'] == 'admin'
    is_super_admin = is_admin and user.get('campus_id') is None
    campus_id = user.get('campus_id')  # None for super admin, int for campus admin/student

    # ---- 侧边栏 ----
    with st.sidebar:
        st.markdown(f"# 🐍 考试系统")

        # 显示身份
        if is_super_admin:
            role_label = "🔑 超级管理员"
        elif is_admin:
            role_label = "👩‍🏫 校区管理员"
        else:
            role_label = "👨‍🎓 学生"
        st.markdown(f"**{role_label}**：{user['display_name']}")
        st.markdown(f"@{user['username']}")

        # 显示所属校区
        if campus_id:
            campus = db.get_campus_by_id(campus_id)
            if campus:
                st.caption(f"🏫 {campus['name']}")
        elif is_super_admin:
            st.caption("🏫 全部校区")

        st.markdown("---")

        # 导航菜单按角色
        if is_super_admin:
            pages = ["📊 仪表盘", "🏫 校区管理", "👥 学生管理", "🔧 用户管理", "📊 考试结果", "📤 上传题库", "📜 全部记录"]
        elif is_admin:
            pages = ["📊 仪表盘", "👥 学生管理", "📤 上传题库", "📜 全部记录"]
        else:
            pages = ["📝 参加考试", "📊 考试结果", "📜 历史记录", "❌ 错题本"]

        current_page = st.radio("导航菜单", pages,
                                index=pages.index(st.session_state.page) if st.session_state.page in pages else 0,
                                label_visibility="collapsed")

        if current_page != st.session_state.page:
            if st.session_state.exam_state == "in_progress" and not is_admin:
                st.warning("⚠️ 离开将丢失当前考试进度！")
                if st.button("确认离开"):
                    db.abandon_attempt(st.session_state.attempt_id)
                    reset_exam_state()
                    st.session_state.page = current_page
                    st.rerun()
            else:
                st.session_state.page = current_page
                st.rerun()

        # 管理员备份功能
        if is_admin:
            st.markdown("---")
            st.markdown("💾 **数据管理**")
            st.caption("定期备份，防止云端数据丢失")

            # 下载备份
            with open(db.DB_PATH, "rb") as f:
                st.download_button(
                    label="📥 下载数据库备份",
                    data=f,
                    file_name=f"exam_backup_{time.strftime('%Y%m%d_%H%M%S')}.db",
                    mime="application/octet-stream",
                    use_container_width=True,
                )

            # 上传恢复
            restore_file = st.file_uploader(
                "📤 恢复数据库备份",
                type=["db"],
                key="restore_db",
                label_visibility="collapsed",
            )
            if restore_file is not None:
                if st.button("⚠️ 确认恢复（将覆盖当前数据）", use_container_width=True, type="secondary"):
                    with open(db.DB_PATH, "wb") as f:
                        f.write(restore_file.read())
                    db.init_db()  # 确保表结构完整
                    st.success("✅ 数据已恢复！请刷新页面。")
                    time.sleep(1)
                    st.rerun()

        st.markdown("---")
        if st.button("🚪 退出登录", use_container_width=True):
            logout()

    # ---- 页面路由 ----
    page = st.session_state.page

    if page == "📝 参加考试":
        page_student_exam()
    elif page == "📊 考试结果":
        page_student_results()
    elif page == "📜 历史记录":
        page_student_history()
    elif page == "❌ 错题本":
        page_student_wrong()
    elif page == "📊 仪表盘":
        page_admin_dashboard()
    elif page == "👥 学生管理":
        page_admin_students()
    elif page == "👤 学生详情":
        page_admin_student_detail()
    elif page == "📤 上传题库":
        page_admin_upload()
    elif page == "🔧 用户管理":
        page_admin_users()
    elif page == "🏫 校区管理":
        page_admin_campuses()
    elif page == "📜 全部记录":
        page_admin_records()


if __name__ == "__main__":
    main()
