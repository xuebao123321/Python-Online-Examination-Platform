"""
在线考试练习系统 — 多用户版
支持学生和管理员两种角色。
"""

import os

# ---- Turso 云数据库配置（在 Streamlit 启动前设置环境变量）----
# Streamlit Cloud 通过 secrets 设置，本地通过 .streamlit/secrets.toml
try:
    import streamlit as st
    if st.secrets.get("TURSO_URL"):
        os.environ["TURSO_URL"] = st.secrets["TURSO_URL"]
        os.environ["TURSO_TOKEN"] = st.secrets["TURSO_TOKEN"]
except Exception:
    pass  # 本地开发或无 secrets 时跳过

import streamlit as st
import time
import db
import csv_import
import grader
import auth
import code_runner

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="在线考试练习系统",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==================== 响应式 CSS ====================
st.markdown("""
<style>
    /* 全局响应式 */
    @media (max-width: 768px) {
        .stButton button {
            padding: 12px 8px !important;
            font-size: 14px !important;
            min-height: 44px !important;
        }
        .stRadio label {
            font-size: 15px !important;
            padding: 8px 0 !important;
        }
        .stTextInput input, .stTextArea textarea, .stSelectbox > div {
            font-size: 16px !important;  /* 防止iOS缩放 */
        }
        h2 { font-size: 20px !important; }
        h3 { font-size: 17px !important; }
        h4 { font-size: 15px !important; }
        .st-emotion-cache-1kyxreq {
            /* 移动端侧边栏更宽 */
            min-width: 200px !important;
        }
    }

    /* 平板适配 */
    @media (min-width: 769px) and (max-width: 1024px) {
        .stButton button {
            min-height: 40px !important;
        }
    }

    /* 所有端：表格横向滚动 */
    .stDataFrame {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }

    /* 按钮最小触控面积 */
    button {
        min-height: 44px !important;
        touch-action: manipulation;
    }

    /* 禁止iOS输入框自动缩放 */
    input, textarea, select {
        font-size: 16px !important;
    }

    /* 考试导航按钮等宽 */
    .stButton button {
        white-space: nowrap;
    }

    /* 侧边栏响应式 */
    [data-testid="stSidebar"] {
        min-width: 220px !important;
        max-width: 300px !important;
    }
    @media (max-width: 576px) {
        [data-testid="stSidebar"] {
            min-width: 180px !important;
            max-width: 250px !important;
        }
    }

    /* 倒计时醒目 */
    .timer-warning { color: #ff4b4b !important; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


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
        "total_time": 3600,
        "review_idx": 0,
        "review_answers": {},
        "review_reasons": {},
        "wrong_qids": [],
        "is_practice": False,
        "last_activity": time.time(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session()


# ==================== 辅助函数 ====================

def clean_text(text):
    """清理文本：规范化换行为markdown换行"""
    if not text:
        return ""
    import re
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 单换行加两个空格实现markdown软换行
    text = text.replace('\n', '  \n')
    return text.strip()


def format_time(seconds):
    if seconds is None:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def get_elapsed_seconds():
    if st.session_state.start_time is None:
        return 0
    return int(time.time() - st.session_state.start_time)


def log_operation(action, target="", detail=""):
    """记录管理操作日志"""
    user = st.session_state.get("user", {})
    uid = user.get("id") if user else None
    uname = user.get("username", "?") if user else "?"
    try:
        db.create_operation_log(uid, uname, action, target, detail)
    except Exception:
        pass  # 日志记录失败不影响主流程


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
    st.query_params.clear()  # 清除免登录
    init_session()
    st.rerun()


PAGE_SIZE = 20  # 全局每页条数


def pagination_bar(page_key, total_items, on_change=None):
    """通用分页控件。page_key 用于 st.session_state 存储当前页码。"""
    total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    current = st.session_state[page_key]

    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if st.button("← 上一页", key=f"{page_key}_prev", disabled=(current <= 0), use_container_width=True):
            st.session_state[page_key] = max(0, current - 1)
            st.rerun()
    with c2:
        st.caption(f"第 {current + 1} 页 / 共 {total_pages} 页（{total_items} 条）")
    with c3:
        if st.button("下一页 →", key=f"{page_key}_next", disabled=(current >= total_pages - 1), use_container_width=True):
            st.session_state[page_key] = min(total_pages - 1, current + 1)
            st.rerun()


# ==================== 登录 / 注册页 ====================

def page_login():
    """登录和注册页面"""
    st.markdown("<h1 style='text-align:center'>📝 在线考试练习系统</h1>", unsafe_allow_html=True)
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
                        st.query_params["user"] = username  # 刷新免登录
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
            reg_pwd = st.text_input("密码", type="password", placeholder="至少6个字符，需包含字母和数字", key="reg_pwd")
            st.caption("🔒 至少6个字符，必须同时包含字母和数字")
            reg_pwd2 = st.text_input("确认密码", type="password", placeholder="再次输入密码", key="reg_pwd2")
            reg_display = st.text_input("显示名称", placeholder="你的姓名或昵称", key="reg_display")
            # 用户协议
            with st.expander("📜 用户协议（必读）", expanded=False):
                st.markdown("""
在线考试练习系统用户协议

1. 版权承诺：用户承诺上传的试题内容不存在版权侵权，所有因上传内容引发的法律责任由用户独立承担。

2. 平台角色：平台仅提供考试练习工具和存储服务，不主动审核用户私有题库内容，不享有用户上传题库的任何著作权。

3. 侵权处理：平台收到版权方有效侵权通知后，有权立即删除对应题库、限制相关账号使用，由此产生的损失由用户自行承担。

4. 赔偿条款：用户因上传侵权内容给平台造成索赔、罚款、商誉损失的，需全额赔偿平台因此遭受的全部损失。

5. 免责声明：本系统为学习辅助工具，题库内容均由用户自行上传，平台不对题库内容的准确性、合法性负责。
                """)

            terms_agreed = st.checkbox(
                "我已阅读并同意《用户协议》全部条款",
                value=False,
                key="reg_terms"
            )

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
                        success, msg, uid = auth.register_user(reg_user, reg_pwd, role, reg_display, reg_campus_id, terms_agreed)
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
                st.warning(f"⚠️ 检测到一场未完成的考试：{bank['name']}")
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
    campus_id = user.get('campus_id')
    levels = db.get_all_levels(campus_id)
    if not levels:
        st.info("📚 还没有题库，请联系管理员上传。")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_level = st.selectbox("选择级别", levels)
    with col2:
        years = db.get_years_for_level(selected_level, campus_id)
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
        duration_min = bank.get("duration_minutes", 60) or 60
        st.markdown(f"📋 {selected_level} {selected_year} ｜ 共 {len(qs)} 道题（{qtype_text}）｜ ⏱️ {duration_min} 分钟")

        # 考试模式 + 出题顺序（管理员可控制是否对学生显示）
        show_mode_selector = bank.get("allow_practice_mode", 0) == 1
        show_order_selector = bank.get("allow_random_order", 0) == 1

        if show_mode_selector:
            cm1, cm2 = st.columns(2)
            with cm1:
                exam_mode = st.radio("模式", ["📝 考试模式", "📝 练习模式"],
                                     format_func=lambda x: x,
                                     horizontal=True, key="exam_mode_selector")
            with cm2:
                if exam_mode == "📝 考试模式" and show_order_selector:
                    order_mode = st.radio("出题顺序", ["顺序出题", "随机出题"],
                                          horizontal=True, key="order_mode_selector")
                else:
                    order_mode = "顺序出题"
        else:
            # 隐藏模式选择，默认考试模式
            exam_mode = "📝 考试模式"
            cm1, cm2 = st.columns(2)
            with cm1:
                st.markdown("📝 **考试模式**")
            with cm2:
                if show_order_selector:
                    order_mode = st.radio("出题顺序", ["顺序出题", "随机出题"],
                                          horizontal=True, key="order_mode_selector")
                else:
                    order_mode = "顺序出题"
                    st.markdown("**出题顺序：** 顺序出题")

        description = "⏱️ 逐题作答，提交后自动判分。" if exam_mode == "📝 考试模式" else "💡 每题答后立即显示解析，无倒计时，不记录成绩。"
        st.markdown(description)

        btn_label = "🚀 开始考试" if exam_mode == "📝 考试模式" else "📝 开始练习"
        if st.button(btn_label, type="primary", use_container_width=True):
            _start_exam(bank, user, is_practice=(exam_mode == "📝 练习模式"),
                        shuffle=(order_mode == "随机出题"))


def _start_exam(bank, user, is_practice=False, shuffle=False):
    import random
    questions = db.get_questions(bank["id"])
    if not questions:
        st.error("题库为空！")
        return

    # 随机出题
    if shuffle:
        random.shuffle(questions)

    # 考试时长从题库配置读取（默认60分钟）
    duration_min = bank.get("duration_minutes", 60) or 60
    total_seconds = duration_min * 60

    if is_practice:
        # 练习模式：不创建考试记录，不设倒计时
        st.session_state.exam_state = "in_progress"
        st.session_state.questions = questions
        st.session_state.current_idx = 0
        st.session_state.answers = {}
        st.session_state.start_time = None  # 无倒计时
        st.session_state.total_time = 0
        st.session_state.attempt_id = None
        st.session_state.is_practice = True
    else:
        attempt_id = db.create_attempt(user['id'], bank["id"], len(questions))
        st.session_state.exam_state = "in_progress"
        st.session_state.questions = questions
        st.session_state.current_idx = 0
        st.session_state.answers = {}
        st.session_state.start_time = time.time()
        st.session_state.total_time = total_seconds
        st.session_state.attempt_id = attempt_id
        st.session_state.is_practice = False
    st.rerun()


def _resume_exam(attempt):
    from datetime import datetime

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

    # 恢复已有的答案
    saved_answers = db.get_answers_by_attempt(attempt["id"])

    # 恢复正确的倒计时：根据 started_at 计算已用时间
    started_str = attempt.get("started_at", "")
    try:
        started_dt = datetime.strptime(started_str, "%Y-%m-%d %H:%M:%S")
        elapsed = (datetime.now() - started_dt).total_seconds()
    except (ValueError, TypeError):
        elapsed = 0
    start_time = time.time() - elapsed

    # 考试时长从题库配置读取
    duration_min = bank.get("duration_minutes", 60) or 60
    total_seconds = duration_min * 60

    st.session_state.exam_state = "in_progress"
    st.session_state.questions = questions
    st.session_state.current_idx = 0
    st.session_state.answers = saved_answers
    st.session_state.start_time = start_time
    st.session_state.total_time = total_seconds
    st.session_state.attempt_id = attempt["id"]
    st.session_state.is_practice = False
    st.rerun()


def _show_exam_questions():
    questions = st.session_state.questions
    total = len(questions)
    idx = st.session_state.current_idx
    current_q = questions[idx]
    is_practice = st.session_state.get("is_practice", False)
    is_timed_out = False

    if not is_practice:
        elapsed = get_elapsed_seconds()
        total_seconds = st.session_state.get("total_time", 3600)
        remaining = max(0, total_seconds - elapsed)
        if remaining <= 0:
            is_timed_out = True

    answered_count = len([a for a in st.session_state.answers.values() if a and a.strip() and a.strip() != '# 在此编写 Python 代码\n'])

    # 顶部：题号导航
    st.markdown(f"##### 📋 答题卡（点击题号跳转）")
    nav_cols = st.columns(min(total, 20))
    for i in range(total):
        col_idx = i % 20
        with nav_cols[col_idx]:
            qid = questions[i]["id"]
            answered = bool(st.session_state.answers.get(qid, "").strip().replace("# 在此编写 Python 代码\n", ""))
            if i == idx:
                label = f"{i+1}"
                btn_type = "primary"
            elif answered:
                label = f"✅{i+1}"
                btn_type = "secondary"
            else:
                label = f"○{i+1}"
                btn_type = "secondary"
            if st.button(label, key=f"nav_{i}", use_container_width=True, type=btn_type):
                st.session_state.current_idx = i
                st.rerun()

    # 时间/模式信息
    if is_practice:
        st.markdown(f"📝 练习模式 ｜ 已答 {answered_count}/{total}")
    else:
        if remaining <= 300:
            timer_color, timer_icon = "red", "🔴"
        elif remaining <= 600:
            timer_color, timer_icon = "orange", "🟡"
        else:
            timer_color, timer_icon = "green", "🟢"
        st.markdown(f":{timer_color}[{timer_icon} 剩余 {format_time(remaining)}] ｜ "
                    f"已答 {answered_count}/{total} ｜ 共 {format_time(total_seconds)}")

    st.divider()

    # 题目
    qtype = current_q["qtype"]
    if qtype == "单选":
        qtype_badge = "🔵 单选题"
    elif qtype == "判断":
        qtype_badge = "🟢 判断题"
    else:
        qtype_badge = "💻 编程题"
    st.markdown(f"### {qtype_badge} · 第 {idx + 1} 题")
    st.markdown(f"{clean_text(current_q['question'])}")

    qid = current_q["id"]
    current_answer = st.session_state.answers.get(qid, "")

    if qtype == "单选":
        choice_labels, choice_map = [], {}
        for label, key in [("A", "option_a"), ("B", "option_b"), ("C", "option_c"), ("D", "option_d")]:
            if current_q.get(key):
                text = f"{label}. {current_q[key]}"
                choice_labels.append(text)
                choice_map[text] = label
        current_text = next((t for t, l in choice_map.items() if l == current_answer), None)
        idx_default = choice_labels.index(current_text) if current_text in choice_labels else None
        selected = st.radio("请选择作答：", choice_labels, index=idx_default, key=f"q_{qid}")
        if selected:
            st.session_state.answers[qid] = choice_map[selected]
    elif qtype == "判断":
        tf_labels = ["对 ✅", "错 ❌"]
        tf_map = {"对 ✅": "对", "错 ❌": "错"}
        current_index = 1 if current_answer == "错" else (0 if current_answer == "对" else None)
        selected = st.radio("请判断：", tf_labels, index=current_index, key=f"q_{qid}", horizontal=True)
        if selected:
            st.session_state.answers[qid] = tf_map[selected]
    else:
        # 编程题：代码编辑器 + 运行按钮
        st.markdown("📝 编写你的 Python 代码：")
        code = st.text_area(
            "代码编辑器",
            value=current_answer if current_answer else "# 在此编写 Python 代码\n",
            height=200,
            key=f"code_{qid}",
            label_visibility="collapsed",
        )
        st.session_state.answers[qid] = code

        run_col1, run_col2 = st.columns([1, 3])
        with run_col1:
            if st.button("▶️ 运行代码", key=f"run_{qid}", use_container_width=True):
                st.session_state[f"show_run_{qid}"] = True
        with run_col2:
            st.caption("代码在浏览器中运行，无需服务器")

        if st.session_state.get(f"show_run_{qid}"):
            code_runner.show_code_runner(code, height=350)
        else:
            code_runner.code_runner_placeholder()

    # 练习模式：选择答案后即时显示对错和解析
    if is_practice and qtype != "编程" and st.session_state.answers.get(qid):
        student_ans = st.session_state.answers[qid]
        correct_ans = current_q.get("answer", "").strip()
        if qtype == "判断":
            # 判断对错（简单比较）
            is_correct = (student_ans == correct_ans)
        else:
            is_correct = (student_ans.upper() == correct_ans.upper())
        if is_correct:
            st.success(f"✅ 回答正确！")
        else:
            st.error(f"❌ 回答错误，正确答案是：{correct_ans}")
        if current_q.get("explanation"):
            st.info(f"💡 解析：{clean_text(current_q['explanation'])}")

    # 作答提示
    if qtype != "编程" and not st.session_state.answers.get(qid):
        st.caption("⚠️ 请选择一个答案")

    st.divider()

    # 时间到自动提交（仅考试模式）
    if is_timed_out and not is_practice:
        st.error("⏰ 时间到！系统自动提交试卷。")
        time.sleep(1)
        _submit_exam(questions, total_seconds)
        return

    # 底部导航
    if is_practice:
        nc1, nc2, nc3 = st.columns([1, 1, 2])
        with nc1:
            if st.button("⬅️ 上一题", use_container_width=True, disabled=(idx == 0)):
                st.session_state.current_idx -= 1
                st.rerun()
        with nc2:
            if st.button("下一题 ➡️", use_container_width=True, type="primary", disabled=(idx == total - 1)):
                st.session_state.current_idx += 1
                st.rerun()
        with nc3:
            if st.button("🚪 退出练习", use_container_width=True, type="secondary"):
                reset_exam_state()
                st.session_state.last_result = None
                st.success("练习已结束")
                time.sleep(0.5)
                st.rerun()
    else:
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
        (st.session_state.attempt_id, r["question"]["id"], r["given_answer"],
         1 if r["is_correct"] is True else 0)
        for r in result["results"]
    ]
    db.save_answers_batch(answers_batch)
    st.session_state.last_result = result
    st.session_state.last_time_sec = elapsed
    st.session_state.exam_state = "submitted"  # 首次提交，不展示解析
    st.session_state.wrong_qids = [r["question"]["id"] for r in result["results"] if r["is_correct"] is False]
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
                {"question": a, "given_answer": a["given_answer"],
                 "is_correct": None if a.get("qtype") == "编程" else bool(a["is_correct"])}
                for a in detail["answers"]
            ]}
            time_sec = detail.get("time_sec", 0)
            _render_result_full(result, time_sec, detail.get("bank_name", ""), detail.get("submitted_at", ""), is_admin_view)
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
        _render_result_full(result, time_sec, is_admin=is_admin_view)
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
        # 编程题显示 📝，答对 ✅，答错 ❌
        if r["is_correct"] is None:
            icon = "📝"
        else:
            icon = "✅" if r["is_correct"] else "❌"
        q = r["question"]
        if r["is_correct"] is False:
            wrong_count += 1
        with st.expander(f"{icon} 第 {i+1} 题 — {q['question'][:60]}{'...' if len(q['question'])>60 else ''}"):
            qtype_label = {'单选': '🔵 单选题', '判断': '🟢 判断题', '编程': '💻 编程题'}.get(q['qtype'], q['qtype'])
            st.markdown(f"题型：{qtype_label}")
            st.markdown(f"题目：{clean_text(q['question'])}")
            if q['qtype'] == '编程':
                code = r['given_answer'] or '# 未作答'
                st.code(code, language="python")
                st.info("📝 编程题需人工批改，提交后管理员会查看代码")
            else:
                st.markdown(f"学生作答：{r['given_answer'] or '未作答'}")
                if r["is_correct"]:
                    st.success("✅ 作答正确")
                    if q.get("explanation"):
                        st.markdown(f"💡 解析：{clean_text(q['explanation'])}")
                else:
                    st.error("❌ 作答错误（正确答案和解析需完成错题订正后解锁）")

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
    """错题订正模式 — 支持部分提交、循环订正"""
    st.subheader("📝 错题订正")

    attempt_id = st.session_state.attempt_id
    detail = db.get_attempt_detail(attempt_id)
    if not detail:
        st.error("考试记录不存在")
        if st.button("↩️ 返回"):
            st.session_state.exam_state = "idle"
            st.session_state.page = "📝 参加考试"
            st.rerun()
        return

    # 筛选仍需订正的题目：is_correct=0 且不是编程题
    wrong_answers = [a for a in detail["answers"]
                     if a["is_correct"] == 0 and a.get("qtype") != "编程"]
    programming_answers = [a for a in detail["answers"]
                           if a.get("qtype") == "编程"]

    # 全部订正完成 → 自动进入 reviewed
    if not wrong_answers:
        st.success("🎉 所有可订正题目已全部通过！")
        if programming_answers:
            st.info(f"📝 {len(programming_answers)} 道编程题待人工批改")
        if st.button("📊 查看完整解析", type="primary", use_container_width=True):
            st.session_state.exam_state = "reviewed"
            st.session_state.review_attempt_id = attempt_id
            st.session_state.last_result = None
            st.rerun()
        return

    total_remaining = len(wrong_answers)
    st.caption("💡 修改答案并选择错误原因后即可提交。已答对的题目会自动消失，"
               f"错误的可继续订正。还剩余 **{total_remaining}** 道。")

    if programming_answers:
        st.info(f"📝 {len(programming_answers)} 道编程题需人工批改，暂不参与订正")

    st.divider()

    # 所有待订正题目渲染为 expander 列表
    answered_this_round = 0
    for i, ans in enumerate(wrong_answers):
        q = ans  # ans 已 JOIN 了题目字段
        qid = q["question_id"]
        qtype = q.get("qtype", "")

        has_answer = bool(st.session_state.review_answers.get(qid, "").strip())
        has_reason = bool(st.session_state.review_reasons.get(qid, ""))
        is_complete = has_answer and has_reason
        if is_complete:
            answered_this_round += 1

        # 构建 expander 标题
        icon = "✅" if is_complete else "📝"
        q_text = (q.get("question") or "")[:60]
        title = f"{icon} 第{q.get('seq', i+1)}题 — {q_text}{'...' if len(q.get('question','') or '') > 60 else ''}"
        prev_reason = q.get("error_reason", "")
        if prev_reason:
            title += f"  [上次原因：{prev_reason}]"

        with st.expander(title, expanded=(not is_complete)):
            st.markdown(f"**题目：** {clean_text(q.get('question', ''))}")

            # 显示上次作答
            prev_ans = q.get("review_answer") or q.get("given_answer", "")
            st.caption(f"上次作答：{prev_ans or '未作答'} ❌")

            # 答题控件
            if qtype == "单选":
                choice_labels, choice_map = [], {}
                for label, key in [("A", "option_a"), ("B", "option_b"),
                                   ("C", "option_c"), ("D", "option_d")]:
                    if q.get(key):
                        text = f"{label}. {q[key]}"
                        choice_labels.append(text)
                        choice_map[text] = label
                prev = st.session_state.review_answers.get(qid, "")
                prev_text = next((t for t, l in choice_map.items() if l == prev), None)
                idx_default = choice_labels.index(prev_text) if prev_text in choice_labels else None
                selected = st.radio("你的新作答：", choice_labels,
                                    index=idx_default, key=f"review_q_{qid}")
                if selected:
                    st.session_state.review_answers[qid] = choice_map[selected]
            elif qtype == "判断":
                tf_labels = ["对 ✅", "错 ❌"]
                tf_map = {"对 ✅": "对", "错 ❌": "错"}
                prev = st.session_state.review_answers.get(qid, "")
                cur_idx = 1 if prev == "错" else (0 if prev == "对" else None)
                selected = st.radio("你的新作答：", tf_labels, index=cur_idx,
                                    key=f"review_q_{qid}", horizontal=True)
                if selected:
                    st.session_state.review_answers[qid] = tf_map[selected]

            # 错误原因
            reasons = ["粗心马虎", "知识点未掌握", "没有思路", "审题不清", "其他"]
            prev_reason_val = st.session_state.review_reasons.get(qid, "")
            reason_idx = reasons.index(prev_reason_val) if prev_reason_val in reasons else 0
            reason = st.selectbox(
                "错误原因：（必选）", reasons,
                index=reason_idx,
                key=f"reason_{qid}",
            )
            if reason:
                st.session_state.review_reasons[qid] = reason

    st.divider()

    # 底部按钮
    c1, c2 = st.columns([2, 1])
    with c1:
        submit_label = (f"📩 提交订正（已答 {answered_this_round} 题）"
                        if answered_this_round > 0 else "📩 提交订正")
        if st.button(submit_label, type="primary", use_container_width=True,
                     disabled=(answered_this_round == 0)):
            if answered_this_round == 0:
                st.warning("请至少完成一道题的订正（选择答案和错误原因）")
            else:
                _submit_review(wrong_answers)
    with c2:
        if st.button("🚪 退出订正，查看结果", use_container_width=True):
            st.session_state.exam_state = "reviewed"
            st.session_state.review_attempt_id = attempt_id
            st.session_state.last_result = None
            st.rerun()


def _submit_review(wrong_answers):
    """部分提交订正 — 只提交已填写的题目，支持循环订正"""
    review_answers = st.session_state.review_answers
    review_reasons = st.session_state.review_reasons
    attempt_id = st.session_state.attempt_id

    # 只收集已填写答案和原因的题目
    review_list = []
    for ans in wrong_answers:
        qid = ans["question_id"]
        ra = review_answers.get(qid, "").strip()
        rr = review_reasons.get(qid, "")
        if not ra or not rr:
            continue  # 跳过本轮未填写的题目

        # 判分
        q_data = {"qtype": ans.get("qtype"), "answer": ans.get("answer", "")}
        is_correct = grader.grade_single(q_data, ra)
        review_list.append((attempt_id, qid, ra, 1 if is_correct else 0, rr))

    if review_list:
        db.save_review_answers(review_list)

        # 重新计算总分
        detail = db.get_attempt_detail(attempt_id)
        if detail:
            new_score = sum(1 for a in detail["answers"] if a["is_correct"])
            db.submit_attempt(attempt_id, new_score, st.session_state.last_time_sec)

    # 清空本轮作答（为下一轮订正准备）
    st.session_state.review_answers = {}
    st.session_state.review_reasons = {}

    # 检查是否还有剩余错题（排除编程题）
    detail = db.get_attempt_detail(attempt_id)
    if detail:
        remaining = [a for a in detail["answers"]
                     if a["is_correct"] == 0 and a.get("qtype") != "编程"]
        if not remaining:
            # 全部订正完成
            st.session_state.exam_state = "reviewed"
            st.session_state.review_attempt_id = attempt_id
            st.session_state.last_result = None
        # 否则保持在 reviewing 状态，重新渲染剩余错题

    st.rerun()


def _render_result_full(result, time_sec, bank_name="", submitted_at="", is_admin=False):
    """渲染完整结果。管理员始终可见全部解析。"""
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
        if r["is_correct"] is None:
            icon = "📝"
        else:
            icon = "✅" if r["is_correct"] else "❌"
        # 如果有订正答案则显示订正后的，否则显示首次答案
        review_ans = q.get("review_answer", "")
        given = review_ans if review_ans else (r["given_answer"] or "（未作答）")
        error_reason = q.get("error_reason", "")

        title = f"{icon} 第 {i+1} 题 — {q['question'][:50]}{'...' if len(q['question'])>50 else ''}"
        if error_reason:
            title += f"  [{error_reason}]"

        with st.expander(title):
            qtype_label = {'单选': '🔵 单选题', '判断': '🟢 判断题', '编程': '💻 编程题'}.get(q['qtype'], q['qtype'])
            st.markdown(f"题型：{qtype_label}")
            st.markdown(f"题目： {clean_text(q['question'])}")

            # 显示首次答题和订正状态
            phase = q.get("phase", "first")
            first_ans = r.get("given_answer") or q.get("given_answer", "")
            review_ans = q.get("review_answer", "")
            first_correct = r.get("is_correct")  # 当前最终是否正确

            if phase == "review" and review_ans:
                st.markdown(f"首次学生作答：{first_ans or '未作答'}")
                status_icon = "📝" if first_correct is None else ("✅" if first_correct else "❌")
                st.markdown(f"订正学生作答：{review_ans} {status_icon}")
            elif q["qtype"] == "编程":
                # 编程题只显示代码，不显示 ✅/❌
                pass
            else:
                st.markdown(f"学生作答：{first_ans or given or '未作答'} {'✅' if first_correct else '❌'}")

            if q["qtype"] == "编程":
                if given:
                    st.code(given, language="python")
                if q.get("explanation") and is_admin:
                    st.markdown("💡 解析/参考代码：")
                    st.code(q['explanation'], language="python")
            elif q["qtype"] == "单选":
                # 管理员或答对时显示正确选项标记
                for label, key in [("A", "option_a"), ("B", "option_b"), ("C", "option_c"), ("D", "option_d")]:
                    if q.get(key):
                        mark = ""
                        if is_admin or r["is_correct"]:
                            if label == q["answer"]:
                                mark = " ✅（正确答案）"
                            elif label == given:
                                mark = " ❌（学生作答）"
                        elif label == given:
                            mark = " ← 学生作答"
                        st.markdown(f"{label}) {q[key]}{mark}")
            else:
                if is_admin or r["is_correct"]:
                    st.markdown(f"正确答案：{q['answer']}")

            if error_reason:
                st.markdown(f"错误原因：{error_reason}")

            # 管理员始终可见解析
            if is_admin and q.get("explanation"):
                st.markdown(f"💡 解析：{clean_text(q['explanation'])}")
            # 学生：答对显示解析，答错引导订正，编程题待批改
            elif not is_admin:
                if r["is_correct"] and q.get("explanation"):
                    st.markdown(f"💡 解析：{clean_text(q['explanation'])}")
                elif r["is_correct"] is False:
                    st.warning("📝 请先完成错题订正，订正后即可查看正确答案和解析")
                elif r["is_correct"] is None:
                    st.info("📝 编程题待人工批改")


# ==================== 学生：历史记录 ====================

def page_student_history():
    st.title("📜 历史记录")
    user = st.session_state.user

    total = db.get_attempts_count(user_id=user['id'])
    if total == 0:
        st.info("还没有考试记录。去「参加考试」完成第一次考试吧！🚀")
        return

    # 汇总统计（只用基本字段，不加 review stats JOIN 以提升速度）
    all_attempts = db.get_attempts(user_id=user['id'])
    total_exams = len(all_attempts)
    avg_pct = round(sum(a["score"] / max(a["total"], 1) * 100 for a in all_attempts) / total_exams, 1) if total_exams > 0 else 0
    best_pct = round(max(a["score"] / max(a["total"], 1) * 100 for a in all_attempts), 1) if total_exams > 0 else 0

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        st.metric("考试次数", total_exams)
    with sc2:
        st.metric("平均正确率", f"{avg_pct}%")
    with sc3:
        st.metric("最高正确率", f"{best_pct}%")
    st.divider()

    page_key = "history_page"
    page = st.session_state.get(page_key, 0)
    attempts = db.get_attempts_with_review_stats(user_id=user['id'], limit=PAGE_SIZE, offset=page * PAGE_SIZE)

    for a in attempts:
        pct = round(a["score"] / a["total"] * 100, 1) if a["total"] > 0 else 0
        icon = "🟢" if pct >= 90 else ("🟡" if pct >= 60 else "🔴")

        wrong_count = int(a.get("wrong_count") or 0)
        corrected_count = int(a.get("corrected_count") or 0)
        uncorrected_count = int(a.get("uncorrected_count") or 0)

        with st.container():
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 2])
            with c1:
                st.markdown(f"{icon} {a['bank_name']}")
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

            # 订正状态行
            if wrong_count == 0:
                st.markdown("🎉 全部正确，无需订正")
            elif uncorrected_count == 0 and corrected_count > 0:
                st.markdown(f"✅ 错题已全部订正通过（原始 {wrong_count} 题 → 当前全部正确）")
            elif uncorrected_count > 0 and corrected_count > 0:
                st.markdown(f"⏳ 已订正 {corrected_count} 题，还有 **{uncorrected_count}** 题待订正")
            elif uncorrected_count > 0 and corrected_count == 0:
                st.markdown(f"📝 **{uncorrected_count}** 道错题未订正")

            st.divider()

    pagination_bar(page_key, total)


# ==================== 学生：错题本 ====================

def page_student_wrong():
    st.title("❌ 错题本")
    user = st.session_state.user

    total = db.get_wrong_questions_count(user['id'])
    if total == 0:
        st.success("🎉 太棒了！你没有错题记录。")
        return

    st.markdown(f"共 {total} 道错题（去重后），按最近考试时间排列：")
    st.caption("💡 已订正正确的题目显示全部解析；未订正的题目需先完成订正才能查看正确答案")
    st.divider()

    page_key = "wrong_page"
    page = st.session_state.get(page_key, 0)
    wrong_qs = db.get_wrong_questions(user['id'], limit=PAGE_SIZE, offset=page * PAGE_SIZE)

    for i, q in enumerate(wrong_qs):
        was_corrected = q.get("was_corrected", 0) == 1
        qtype = q.get("qtype", "")

        # 图标 + 状态标签
        icon = "🔵" if qtype == "单选" else ("🟢" if qtype == "判断" else "💻")
        status_badge = " ✅已订正" if was_corrected else " ⏳待订正"

        with st.expander(f"{icon} {qtype}{status_badge} — {q['question'][:50]}{'...' if len(q.get('question','') or '') > 50 else ''}"):
            st.markdown(f"题目：{clean_text(q.get('question', ''))}")

            if qtype == "单选":
                # 显示选项
                for label, key in [("A", "option_a"), ("B", "option_b"), ("C", "option_c"), ("D", "option_d")]:
                    if q.get(key):
                        marks = []
                        correct_ans = q.get("answer", "")
                        given_ans = q.get("given_answer", "")
                        review_ans = q.get("review_answer", "")

                        if was_corrected:
                            # 已订正正确 → 完整显示
                            if label == correct_ans:
                                marks.append("✅ 正确答案")
                            if label == given_ans:
                                marks.append("❌ 原作答")
                            if review_ans and label == review_ans and review_ans != given_ans:
                                marks.append("📝 订正作答")
                        else:
                            # 未订正 → 只显示学生作答，隐藏正确答案
                            if label == given_ans:
                                marks.append("❌ 你的作答")

                        mark = (" " + " / ".join(marks)) if marks else ""
                        st.markdown(f"　{label}) {q[key]}{mark}")
            elif qtype == "判断":
                if was_corrected:
                    st.markdown(f"　原作答：{q.get('given_answer', '未作答')} ❌")
                    review_ans = q.get("review_answer", "")
                    if review_ans:
                        st.markdown(f"　订正作答：{review_ans} ✅")
                    st.markdown(f"　正确答案：{q.get('answer', '')}")
                else:
                    st.markdown(f"　你的作答：{q.get('given_answer', '未作答')} ❌")
            else:
                # 编程题
                code = q.get("given_answer") or ""
                if code and code.strip() and code.strip() != "# 在此编写 Python 代码":
                    st.code(code, language="python")
                else:
                    st.caption("（未作答）")
                st.info("📝 编程题需人工批改")

            # 错误原因
            error_reason = q.get("error_reason", "")
            if error_reason:
                st.caption(f"📌 错误原因：{error_reason}")

            # 解析：仅已订正正确的题目显示
            if was_corrected and q.get("explanation"):
                st.info(f"💡 解析：{clean_text(q['explanation'])}")
                st.success("🎉 已通过订正掌握本题！")
            elif not was_corrected and qtype != "编程":
                st.warning("🔒 完成错题订正后可解锁正确答案和解析")

    pagination_bar(page_key, total)


# ==================== 题库预览与编辑 ====================

def _show_question_editor(bank_id, q, qtype_icon=""):
    """单题展示+编辑。点击编辑后可修改题目字段。"""
    qid = q['id']
    edit_key = f"edit_{bank_id}_{qid}"
    is_editing = st.session_state.get(edit_key, False)

    if not is_editing:
        # 只读展示
        st.markdown(f"{qtype_icon} **第{q['seq']}题** — {q['question'][:50]}{'...' if len(q.get('question','')) > 50 else ''} ｜ 答案: `{q['answer']}`")
        if st.button("✏️ 编辑", key=f"edit_btn_{bank_id}_{qid}"):
            st.session_state[edit_key] = True
            st.rerun()
    else:
        # 编辑模式
        with st.container():
            st.markdown(f"{qtype_icon} **编辑第{q['seq']}题**")
            new_q = st.text_area("题目", value=q.get('question', ''), key=f"eq_{qid}")
            new_a = st.text_input("选项A", value=q.get('option_a', ''), key=f"ea_{qid}")
            new_b = st.text_input("选项B", value=q.get('option_b', ''), key=f"eb_{qid}")
            new_c = st.text_input("选项C", value=q.get('option_c', ''), key=f"ec_{qid}")
            new_d = st.text_input("选项D", value=q.get('option_d', ''), key=f"ed_{qid}")
            new_ans = st.text_input("正确答案", value=q.get('answer', ''), key=f"eans_{qid}")
            new_exp = st.text_area("解析", value=q.get('explanation', ''), key=f"eexp_{qid}", height=80)

            ce1, ce2 = st.columns(2)
            with ce1:
                if st.button("💾 保存修改", key=f"save_{bank_id}_{qid}", use_container_width=True, type="primary"):
                    db.update_question(qid,
                        question=new_q, option_a=new_a, option_b=new_b,
                        option_c=new_c, option_d=new_d, answer=new_ans, explanation=new_exp)
                    st.session_state[edit_key] = False
                    st.success("✅ 已保存")
                    time.sleep(0.5)
                    st.rerun()
            with ce2:
                if st.button("❌ 取消", key=f"cancel_edit_{bank_id}_{qid}", use_container_width=True):
                    st.session_state[edit_key] = False
                    st.rerun()
        st.divider()


# ==================== 管理员：上传题库 ====================

def page_admin_upload():
    st.title("📤 上传题库")

    with st.expander("📋 CSV 文件格式说明", expanded=False):
        st.markdown("""
        必需列名： `序号,题型,题目,选项A,选项B,选项C,选项D,正确答案,解析`
        - 题型：`单选` / `判断` / `编程`
        - 正确作答：单选填 A/B/C/D，判断填 对/错，编程题留空或填参考代码
        - 解析：编程题可填解题思路或参考代码
        - 文件编码：UTF-8
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

        user = st.session_state.user
        is_super = user['role'] == 'admin' and user.get('campus_id') is None

        sc1, sc2 = st.columns(2)
        with sc1:
            level_options = ["电子协会一级", "电子协会二级", "电子协会三级", "其他（自定义）"]
            level_select = st.selectbox("级别名称", level_options)
            if level_select == "其他（自定义）":
                level = st.text_input("输入自定义名称", placeholder="例如：自定义题库", key="custom_level")
            else:
                level = level_select
        with sc2:
            # 动态年份：当前年往前20年到往后1年
            import datetime as dt_module
            current_year = dt_module.datetime.now().year
            year_months = []
            for y in range(current_year - 20, current_year + 2):
                for m in [3, 6, 9, 12]:
                    year_months.append(f"{y}年{m}月")
            year_months.reverse()
            year = st.selectbox("年月", year_months)

        # 考试时长设置
        duration_minutes = st.number_input("⏱️ 考试时长（分钟）", min_value=1, max_value=180, value=60, step=5,
                                           help="学生在考试模式下的倒计时时长，练习模式不受此限制")

        # 学生界面显示控制（防作弊）
        st.divider()
        st.markdown("##### 🔒 学生界面显示控制")
        sc3, sc4 = st.columns(2)
        with sc3:
            allow_practice_mode = 1 if st.checkbox("允许练习模式", value=False,
                                                    help="勾选后学生可以看到并选择「练习模式」；不勾选则隐藏，学生只能考试") else 0
        with sc4:
            allow_random_order = 1 if st.checkbox("允许随机出题", value=False,
                                                   help="勾选后学生可以看到并选择「随机出题」；不勾选则隐藏，学生只能顺序出题") else 0

        # 超级管理员需要选择目标校区
        if is_super:
            campuses = db.get_all_campuses()
            if campuses:
                campus_options = {c['name']: c['id'] for c in campuses}
                target_campus_name = st.selectbox("目标校区（题库归属）", list(campus_options.keys()))
                cid = campus_options[target_campus_name]
            else:
                st.warning("⚠️ 还没有校区，请先在「校区管理」中创建校区")
                cid = None
        else:
            cid = user.get('campus_id')

        # 版权免责声明
        st.markdown("---")
        copyright_agreed = st.checkbox(
            "⚖️ 版权声明：我确认上传的试题文件拥有完整著作权或合法授权，未上传未经授权的考试真题。"
            "如上传内容侵犯他人知识产权，由上传方承担全部法律责任。平台有权核查、删除侵权文件并封禁账号。",
            value=False,
            key="copyright_agree"
        )

        import_btn = st.button("📥 导入题库", type="primary", use_container_width=True, disabled=not copyright_agreed)
        if not copyright_agreed:
            st.caption("⚠️ 请先阅读并同意版权声明")

    with col2:
        st.subheader("📚 已有题库")

        # 超级管理员：待审批删除
        if is_super:
            delete_reqs = db.get_delete_requests()
            if delete_reqs:
                st.warning(f"⏳ {len(delete_reqs)} 个删除申请待审批")
                for dr in delete_reqs:
                    with st.container():
                        st.markdown(f"🗑️ {dr['name']}")
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

        banks = db.get_all_banks(None if is_super else cid)

        if banks:
            for b in banks:
                count = db.get_question_count(b["id"])
                status = ""
                if b.get('delete_requested') == 1:
                    status = " ⏳(待审批删除)"
                st.markdown(f"{b['name']}  [{count}题]{status}")
                st.caption(f"上传者: {b.get('uploader_name','?')} ｜ 校区: {b.get('campus_name','?')} ｜ {b['created_at']}")

                btn_col1, btn_col2, btn_col3 = st.columns(3)
                with btn_col1:
                    # 删除 / 申请删除
                    if is_super:
                        if st.button("🗑️ 删除", key=f"del_{b['id']}", use_container_width=True):
                            log_operation("删除题库", b['name'], f"level={b['level']} year={b['year']}")
                            db.delete_bank(b["id"])
                            st.rerun()
                    else:
                        if b.get('delete_requested', 0) == 0:
                            if st.button("📩 申请删除", key=f"req_del_{b['id']}", use_container_width=True):
                                db.request_delete_bank(b['id'])
                                st.success("已提交删除申请，等待超级管理员审批")
                                time.sleep(1)
                                st.rerun()
                with btn_col2:
                    # 预览按钮
                    preview_key = f"preview_{b['id']}"
                    if st.button("👁️ 预览", key=preview_key, use_container_width=True):
                        st.session_state[preview_key] = not st.session_state.get(preview_key, False)

                # 展开预览
                if st.session_state.get(preview_key, False):
                    with st.container():
                        qs = db.get_questions(b["id"])[:10]
                        for q in qs:
                            qtype_icon = {'单选': '🔵', '判断': '🟢', '编程': '💻'}.get(q['qtype'], '')
                            _show_question_editor(b["id"], q, qtype_icon)

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
        # cid 已在上面设置（超管从下拉框选，校区管理员从 user 取），不要覆盖！
        if existing:
            st.warning(f"题库「{bank_name}」已存在，将替换原有题目。")
            c_a, c_b = st.columns(2)
            with c_a:
                if st.button("✅ 确认替换", type="primary"):
                    db.replace_bank(existing["id"], bank_name, level.strip(), year, uid, cid, duration_minutes,
                                    allow_practice_mode=allow_practice_mode, allow_random_order=allow_random_order)
                    _do_import(existing["id"], questions, bank_name, user, uploaded_file.name)
            with c_b:
                if st.button("❌ 取消"):
                    st.rerun()
        else:
            bank_id = db.create_bank(bank_name, level.strip(), year, uid, cid, duration_minutes,
                                      allow_practice_mode=allow_practice_mode, allow_random_order=allow_random_order)
            if bank_id:
                _do_import(bank_id, questions, bank_name, user, uploaded_file.name)
            else:
                st.error("创建题库失败")


def _do_import(bank_id, questions, bank_name, user=None, filename=""):
    batch = [(q["seq"], q["qtype"], q["question"], q["option_a"], q["option_b"],
              q["option_c"], q["option_d"], q["answer"], q["explanation"]) for q in questions]
    db.insert_questions_batch(bank_id, batch)

    # 记录上传审计日志
    if user:
        db.create_upload_log(
            user['id'], user.get('campus_id'),
            filename, 0, len(questions), bank_name
        )

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
        st.metric("📊 平均正确率", f"{stats['avg_score']}%" if stats.get('avg_score') else "N/A")
    with mc4:
        active_students = len([s for s in stats['student_stats'] if (s.get('exam_count') or 0) > 0])
        st.metric("✅ 活跃学生", active_students)

    st.divider()

    # 学生统计表
    st.subheader("👥 学生考试统计")
    if stats['student_stats']:
        student_data = []
        for s in stats['student_stats']:
            avg = round(s.get('avg_score') or 0, 1)
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
            st.markdown(f"{e['error_reason']}：{e['cnt']} 次 ({pct}%)")
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

    # 搜索框
    search_key = "student_search"
    search = st.text_input("🔍 搜索学生（用户名或显示名）", key=search_key, placeholder="输入关键词筛选...")

    campus_id = st.session_state.user.get('campus_id')
    total = db.get_all_students_count(campus_id, search)
    if total == 0:
        st.info("没有匹配的学生账号。" if search else "还没有注册的学生账号。")
        return

    page_key = "students_page"
    if search and st.session_state.get(f"{page_key}_prev_search") != search:
        st.session_state[page_key] = 0  # 搜索变化时重置到第一页
    st.session_state[f"{page_key}_prev_search"] = search

    page = st.session_state.get(page_key, 0)
    students = db.get_all_students(campus_id, limit=PAGE_SIZE, offset=page * PAGE_SIZE, search=search)

    for s in students:
        detail = db.get_student_detail(s['id'])
        attempts = detail['attempts']
        exam_count = len(attempts)
        avg_pct = round(sum(a['score'] / max(a['total'], 1) * 100 for a in attempts) / exam_count, 1) if exam_count > 0 else 0

        with st.container():
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
            with c1:
                st.markdown(f"{s['display_name']}  (@{s['username']})")
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

    pagination_bar(page_key, total)


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
                    st.markdown(f"{a['bank_name']}")
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
    campus_id = st.session_state.user.get('campus_id')
    total = db.get_attempts_count(campus_id=campus_id)

    if total == 0:
        st.info("还没有考试记录。")
        return

    mc1, mc2 = st.columns(2)
    with mc1:
        st.metric("总考试次数", total)
    with mc2:
        st.metric("每页显示", f"{PAGE_SIZE} 条")
    st.divider()

    page_key = "records_page"
    page = st.session_state.get(page_key, 0)
    attempts = db.get_attempts(campus_id=campus_id, limit=PAGE_SIZE, offset=page * PAGE_SIZE)

    for a in attempts:
        pct = round(a["score"] / a["total"] * 100, 1) if a["total"] > 0 else 0
        icon = "🟢" if pct >= 90 else ("🟡" if pct >= 60 else "🔴")
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 2])
            with c1:
                st.markdown(f"{icon} {a.get('user_name', '?')} — {a['bank_name']}")
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

    pagination_bar(page_key, total)


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
                    log_operation("重置密码", reset_user)
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.error("请输入用户名和新密码")


# ==================== 超级管理员：校区管理 ====================

def page_admin_audit_log():
    """上传审计日志 + 操作日志（仅超级管理员可见）"""
    st.title("📋 审计日志")

    tab1, tab2 = st.tabs(["📤 上传日志", "🔧 操作日志"])

    with tab1:
        st.caption("记录所有题库上传操作，用于版权溯源")
        total = db.get_upload_logs_count()
        if total == 0:
            st.info("暂无上传记录")
        else:
            page_key = "audit_page"
            page = st.session_state.get(page_key, 0)
            logs = db.get_upload_logs(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
            data = []
            for l in logs:
                data.append({
                    "时间": l['uploaded_at'],
                    "上传者": l.get('uploader_name', '?'),
                    "账号": l.get('username', '?'),
                    "校区": l.get('campus_name', '全部'),
                    "文件名": l['filename'],
                    "题库名": l.get('bank_name', ''),
                    "题目数": l['question_count'],
                })
            st.dataframe(data, use_container_width=True, hide_index=True)
            pagination_bar(page_key, total)

    with tab2:
        st.caption("记录管理操作：删除题库、删除校区、重置密码、恢复备份等")
        op_total = db.get_operation_logs_count()
        if op_total == 0:
            st.info("暂无操作记录")
        else:
            op_page_key = "oplog_page"
            op_page = st.session_state.get(op_page_key, 0)
            logs = db.get_operation_logs(limit=PAGE_SIZE, offset=op_page * PAGE_SIZE)
            op_data = []
            for l in logs:
                op_data.append({
                    "时间": l['created_at'],
                    "操作人": l.get('username', '?'),
                    "操作": l['action'],
                    "目标": l.get('target', ''),
                    "详情": l.get('detail', ''),
                })
            st.dataframe(op_data, use_container_width=True, hide_index=True)
            pagination_bar(op_page_key, op_total)


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
                    st.markdown(f"🏫 {c['name']}")
                    st.caption(f"创建于 {c['created_at']}")
                with cc2:
                    st.metric("👨‍🎓 学生", len(students))
                with cc3:
                    st.metric("👩‍🏫 管理员", len(admins))
                with cc4:
                    delete_key = f"del_campus_{c['id']}"
                    confirm_key = f"confirm_del_campus_{c['id']}"
                    if st.session_state.get(confirm_key):
                        st.error(f"⚠️ 确认删除「{c['name']}」？此操作不可撤销，将删除该校区所有学生、考试记录和题库！")
                        cc_a, cc_b = st.columns(2)
                        with cc_a:
                            if st.button("✅ 确认删除", key=f"do_{c['id']}", use_container_width=True, type="primary"):
                                log_operation("删除校区", c['name'])
                                db.delete_campus(c['id'])
                                st.session_state[confirm_key] = False
                                st.rerun()
                        with cc_b:
                            if st.button("❌ 取消", key=f"cancel_{c['id']}", use_container_width=True):
                                st.session_state[confirm_key] = False
                                st.rerun()
                    else:
                        if st.button("🗑️ 删除", key=delete_key, use_container_width=True):
                            st.session_state[confirm_key] = True
                            st.rerun()
                st.divider()


# ==================== 主程序 ====================

def main():
    # ---- 会话超时检测（2小时无操作自动退出）----
    SESSION_TIMEOUT = 2 * 60 * 60  # 2小时
    if st.session_state.get("logged_in"):
        last_active = st.session_state.get("last_activity", 0)
        now = time.time()
        if now - last_active > SESSION_TIMEOUT:
            logout()
            st.warning("⏰ 会话已超时，请重新登录。")
            st.stop()
        st.session_state["last_activity"] = now

    # ---- 确保默认超级管理员存在 ----
    # 仅在 secrets 中显式配置了管理员账号密码时才自动创建，不再使用硬编码默认值
    try:
        default_user = st.secrets.get("default_admin_user", "")
        default_pass = st.secrets.get("default_admin_pass", "")
    except Exception:
        default_user = ""
        default_pass = ""

    if default_user and default_pass:
        auth.ensure_default_admin(default_user, default_pass)
    else:
        # 检查是否已存在管理员，若没有则提示配置
        existing = db.get_user_by_username(default_user or "admin")
        if not existing:
            print("[系统提示] 未检测到默认管理员账号。请在 Streamlit Cloud → Settings → Secrets 中配置 default_admin_user 和 default_admin_pass。")

    # ---- 刷新免登录：URL中有用户参数则自动恢复 ----
    if not st.session_state.logged_in and st.query_params.get("user"):
        saved_user = db.get_user_by_username(st.query_params["user"])
        if saved_user:
            st.session_state.logged_in = True
            st.session_state.user = saved_user
            st.session_state.page = "📝 参加考试" if saved_user['role'] == 'student' else "📊 仪表盘"

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
        st.markdown(f"# 📝 在线考试")

        # 显示身份
        if is_super_admin:
            role_label = "🔑 超级管理员"
        elif is_admin:
            role_label = "👩‍🏫 校区管理员"
        else:
            role_label = "👨‍🎓 学生"
        st.markdown(f"{role_label}：{user['display_name']}")
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
            pages = ["📊 仪表盘", "🏫 校区管理", "👥 学生管理", "🔧 用户管理", "📊 考试结果", "📤 上传题库", "📋 上传日志", "📜 全部记录"]
        elif is_admin:
            pages = ["📊 仪表盘", "👥 学生管理", "📊 考试结果", "📤 上传题库", "📜 全部记录"]
        else:
            pages = ["📝 参加考试", "📊 考试结果", "📜 历史记录", "❌ 错题本"]

        current_page = st.radio("导航菜单", pages,
                                index=pages.index(st.session_state.page) if st.session_state.page in pages else 0,
                                label_visibility="collapsed")

        if current_page != st.session_state.page:
            if st.session_state.exam_state == "in_progress" and not is_admin:
                is_practice = st.session_state.get("is_practice", False)
                if is_practice:
                    st.info("📝 练习模式，退出不会保存记录。")
                    if st.button("确认退出练习"):
                        reset_exam_state()
                        st.session_state.page = current_page
                        st.rerun()
                else:
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
            st.markdown("💾 数据管理")
            st.caption("定期备份，防止云端数据丢失")

            # 下载备份（懒加载：点击按钮后才生成）
            backup_key = "backup_ready"
            if not st.session_state.get(backup_key):
                if st.button("📦 生成备份文件", use_container_width=True):
                    with st.spinner("正在导出数据..."):
                        try:
                            backup_path = db.ensure_local_backup(campus_id=campus_id)
                            st.session_state[backup_key] = True
                            st.session_state["backup_path"] = backup_path
                            st.rerun()
                        except Exception as e:
                            st.warning(f"⚠️ 导出备份失败：{e}")
            else:
                try:
                    backup_path = st.session_state.get("backup_path", db.DB_PATH)
                    with open(backup_path, "rb") as f:
                        st.download_button(
                            label="📥 下载数据库备份",
                            data=f,
                            file_name=f"exam_backup_{time.strftime('%Y%m%d_%H%M%S')}.db",
                            mime="application/octet-stream",
                            use_container_width=True,
                        )
                    if st.button("🔄 重新生成", use_container_width=True):
                        st.session_state[backup_key] = False
                        st.rerun()
                except Exception as e:
                    st.warning(f"⚠️ 下载失败：{e}")
                    st.session_state[backup_key] = False

            # 上传恢复
            restore_file = st.file_uploader(
                "📤 恢复数据库备份",
                type=["db"],
                key="restore_db",
                label_visibility="collapsed",
            )
            if restore_file is not None:
                if st.button("⚠️ 确认恢复（将覆盖当前数据）", use_container_width=True, type="secondary"):
                    try:
                        # 将上传的文件临时保存到本地
                        uploaded_bytes = restore_file.read()
                        with open(db.DB_PATH, "wb") as f:
                            f.write(uploaded_bytes)
                        # 从 SQLite 文件恢复到当前数据库（Turso 或本地）
                        db.restore_from_sqlite(db.DB_PATH)
                        db.init_db()  # 确保表结构完整
                        log_operation("恢复数据库备份")
                        st.success("✅ 数据已恢复！请刷新页面。")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 恢复失败：{e}")

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
    elif page == "📋 上传日志":
        page_admin_audit_log()
    elif page == "🏫 校区管理":
        page_admin_campuses()
    elif page == "📜 全部记录":
        page_admin_records()


if __name__ == "__main__":
    main()
