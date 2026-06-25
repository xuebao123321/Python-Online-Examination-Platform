"""
CSV 题库导入模块
支持 UTF-8（含 BOM）和 GBK 编码的 CSV 文件。
"""

import csv
import io

# 必需的 CSV 列名
REQUIRED_COLUMNS = ["序号", "题型", "题目", "选项A", "选项B", "选项C", "选项D", "正确答案", "解析"]

# 有效的题型
VALID_QTYPES = ["单选", "判断"]

# 单选题有效答案
VALID_CHOICE_ANSWERS = ["A", "B", "C", "D"]
# 判断题有效答案
VALID_TF_ANSWERS = ["对", "错"]


def parse_csv(file_obj):
    """
    解析 CSV 文件，返回题目列表。
    file_obj: 可以是文件路径(str) 或 Streamlit 的 UploadedFile 对象。

    返回:
        (questions_list, errors_list)
        questions_list: 每项是一个 dict，包含所有题目字段
        errors_list: 解析过程中的错误信息
    """
    errors = []

    # 读取文件内容
    if isinstance(file_obj, str):
        # 文件路径
        raw_bytes = _read_file_with_fallback(file_obj)
    else:
        # Streamlit UploadedFile 或类似对象
        raw_bytes = file_obj.read()

    # 尝试多种编码解析
    text = _decode_bytes(raw_bytes)
    if text is None:
        errors.append("❌ 无法识别文件编码，请使用 UTF-8 或 GBK 编码保存 CSV 文件。")
        return [], errors

    # 解析 CSV
    try:
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        errors.append(f"❌ CSV 格式错误：{e}")
        return [], errors

    # 验证列名
    if reader.fieldnames is None:
        errors.append("❌ CSV 文件为空，没有找到列名。")
        return [], errors

    # 清理列名（去除 BOM 和空白）
    cleaned_fields = [f.strip().lstrip("﻿") for f in reader.fieldnames]
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in cleaned_fields]
    if missing_cols:
        errors.append(f"❌ 缺少必需列：{', '.join(missing_cols)}")
        errors.append(f"   请确保 CSV 包含以下列：{', '.join(REQUIRED_COLUMNS)}")
        return [], errors

    # 建立列名映射（处理可能的 BOM 问题）
    field_map = {}
    for i, f in enumerate(reader.fieldnames):
        clean = f.strip().lstrip("﻿")
        field_map[clean] = i

    questions = []
    for row_num, row in enumerate(reader, start=2):  # 从第2行开始（第1行是标题）
        # 清理 row keys
        clean_row = {}
        for k, v in row.items():
            clean_key = k.strip().lstrip("﻿")
            clean_row[clean_key] = v.strip() if v else ""

        # 验证必填字段
        seq = clean_row.get("序号", "").strip()
        qtype = clean_row.get("题型", "").strip()
        question_text = clean_row.get("题目", "").strip()
        answer = clean_row.get("正确答案", "").strip()

        if not question_text:
            errors.append(f"⚠️ 第 {row_num} 行：题目为空，已跳过")
            continue

        if qtype not in VALID_QTYPES:
            errors.append(f"⚠️ 第 {row_num} 行：题型「{qtype}」无效，应为「单选」或「判断」，已跳过")
            continue

        # 验证答案格式
        if qtype == "单选" and answer not in VALID_CHOICE_ANSWERS:
            errors.append(f"⚠️ 第 {row_num} 行：单选题答案「{answer}」无效，应为 A/B/C/D，已跳过")
            continue
        elif qtype == "判断" and answer not in VALID_TF_ANSWERS:
            errors.append(f"⚠️ 第 {row_num} 行：判断题答案「{answer}」无效，应为「对」或「错」，已跳过")
            continue

        # 判断题：选项可以为空，单选题必须有至少两个选项
        option_a = clean_row.get("选项A", "")
        option_b = clean_row.get("选项B", "")
        option_c = clean_row.get("选项C", "")
        option_d = clean_row.get("选项D", "")
        explanation = clean_row.get("解析", "")

        if qtype == "单选":
            filled_options = [o for o in [option_a, option_b, option_c, option_d] if o]
            if len(filled_options) < 2:
                errors.append(f"⚠️ 第 {row_num} 行：单选题至少需要填写两个选项，已跳过")
                continue
            # 检查答案对应的选项是否存在
            answer_idx = ord(answer) - ord("A")
            answer_option = [option_a, option_b, option_c, option_d][answer_idx]
            if not answer_option:
                errors.append(f"⚠️ 第 {row_num} 行：正确答案 {answer} 对应的选项为空，已跳过")
                continue

        questions.append({
            "seq": seq,
            "qtype": qtype,
            "question": question_text,
            "option_a": option_a,
            "option_b": option_b,
            "option_c": option_c,
            "option_d": option_d,
            "answer": answer,
            "explanation": explanation,
        })

    if not questions:
        errors.append("⚠️ 没有解析到任何有效题目。")

    return questions, errors


def _read_file_with_fallback(filepath):
    """尝试读取文件，处理编码问题"""
    # 尝试 UTF-8
    try:
        with open(filepath, "rb") as f:
            return f.read()
    except Exception as e:
        raise IOError(f"无法读取文件 {filepath}: {e}")


def _decode_bytes(raw_bytes):
    """尝试多种编码解码字节内容"""
    # 尝试 UTF-8（含 BOM）
    for encoding in ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030", "latin-1"]:
        try:
            return raw_bytes.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def validate_bank_info(level, year):
    """验证题库的级别和年份信息"""
    errors = []
    if not level or not level.strip():
        errors.append("❌ 级别名称不能为空")
    if not year:
        errors.append("❌ 年份不能为空")
    elif not str(year).isdigit() or len(str(year)) != 4:
        errors.append("❌ 年份格式不正确，请输入4位数字（如 2024）")
    return errors
