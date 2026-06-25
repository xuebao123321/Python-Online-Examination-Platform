# 🐍 Python 在线考试系统

一个为学习 Python 的小学生设计的在线考试练习工具。

## 🚀 快速启动

```bash
# 1. 安装依赖（只需要 streamlit）
pip install -r requirements.txt

# 2. 启动考试系统
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`，考试系统就启动了！

## 📖 功能说明

| 功能 | 说明 |
|------|------|
| 📤 上传题库 | 家长通过 CSV 文件导入题库，按级别和年份管理 |
| 📝 参加考试 | 选择级别和年份，逐题作答，系统自动计时 |
| 📊 考试结果 | 提交后自动出分，逐题显示答案解析 |
| 📜 历史记录 | 查看历次考试成绩，点击可回顾详细答题情况 |

## 📋 题库 CSV 格式

用 Excel 或 WPS 编辑题库，保存为 CSV 文件。**第一行必须是列名：**

```
序号,题型,题目,选项A,选项B,选项C,选项D,正确答案,解析
```

**填写规则：**

- **题型**：`单选` 或 `判断`
- **单选题**：选项A~D 至少填两个，正确答案写 `A`/`B`/`C`/`D`
- **判断题**：选项A~D 可以留空，正确答案写 `对` 或 `错`
- **解析**：答案说明，考试结束后展示给学生

**参考示例：** `sample_questions/电子协会一级_2023_示例.csv`

## 📁 文件结构

```
python study/
├── app.py              # Streamlit 主程序（UI 和页面逻辑）
├── db.py               # 数据库操作（SQLite 的增删改查）
├── csv_import.py       # CSV 题库导入和验证
├── grader.py           # 判分引擎（判断答案对错）
├── requirements.txt    # Python 依赖
├── data/
│   └── exam.db         # SQLite 数据库（自动生成）
├── sample_questions/   # 示例题库
└── README.md           # 本文件
```

## 🛠️ 自定义修改

这个系统代码很简单，你可以自己动手修改：

- **修改配色**：在 `app.py` 中找到 `percentage >= 90` 等分数段，改成你喜欢的颜色
- **增加题目类型**：在 `grader.py` 中添加新的判分逻辑
- **调整时间限制**：在 `app.py` 中搜索 `total * 60`（默认每题 60 秒）
- **导出成绩**：在 `db.py` 中添加导出 CSV 的函数

## 🔧 技术栈

- **UI 框架**：Streamlit（纯 Python，无需 HTML/CSS）
- **数据库**：SQLite（文件存储，零配置）
- **依赖**：仅需 `streamlit` 一个包
