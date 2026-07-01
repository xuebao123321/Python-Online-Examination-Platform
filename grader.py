"""
判分引擎
纯逻辑模块，不依赖数据库或 UI。
"""


def grade_single(question, given_answer):
    """
    判断单道题是否正确。
    编程题返回 None 表示需人工批改。

    参数:
        question: dict，包含 'qtype' 和 'answer' 字段
        given_answer: 学生的答案 (str)

    返回:
        bool | None: 是否正确；编程题返回 None
    """
    if not given_answer:
        # 编程题未作答也返回 None
        if question.get("qtype") == "编程":
            return None
        return False

    # 标准化比较：去除首尾空格
    qtype = question.get("qtype", "")
    correct = question.get("answer", "").strip()
    student = given_answer.strip()

    # 编程题：不自动判分，返回 None 表示需人工批改
    if qtype == "编程":
        return None

    # 判断题：统一处理 "对"/"正确"/"True" → 对, "错"/"错误"/"False" → 错
    if qtype == "判断":
        student = _normalize_tf_answer(student)
        correct = _normalize_tf_answer(correct)

    # 多选题：排序后比较（"BAC" 等价于 "ABC"）
    if qtype == "多选":
        return "".join(sorted(student.upper())) == "".join(sorted(correct.upper()))

    return student.upper() == correct.upper()


def grade_all(questions, answers_dict):
    """
    批改所有题目。编程题不计入总分。

    参数:
        questions: 题目列表，每项含 id, qtype, answer, question, explanation 等
        answers_dict: dict {question_id: given_answer}

    返回:
        dict: {
            "score": 得分（不含编程题）,
            "total": 可自动评分的题目总数（不含编程题）,
            "results": [
                {
                    "question": {...},
                    "given_answer": 学生答案,
                    "is_correct": True/False/None (None=编程题待批改)
                },
                ...
            ]
        }
    """
    results = []
    score = 0

    for q in questions:
        qid = q["id"]
        given = answers_dict.get(qid, "")
        is_correct = grade_single(q, given)

        if is_correct is True:
            score += 1

        results.append({
            "question": q,
            "given_answer": given,
            "is_correct": is_correct,
        })

    # total 只统计可自动评分的题目（排除编程题）
    total = sum(1 for q in questions if q.get("qtype") != "编程")

    return {
        "score": score,
        "total": total,
        "results": results,
    }


def _normalize_tf_answer(answer):
    """
    标准化判断题答案。
    "对", "正确", "True", "true", "√", "✓" → "对"
    "错", "错误", "False", "false", "×", "✗" → "错"
    """
    if not answer:
        return ""
    a = answer.strip()
    if a in ("对", "正确", "True", "true", "√", "✓", "T", "t"):
        return "对"
    if a in ("错", "错误", "False", "false", "×", "✗", "F", "f"):
        return "错"
    return a
