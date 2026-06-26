#!/usr/bin/env python3
"""生成6套Python二级真题CSV（含答案+详细解析）"""
import zipfile, xml.etree.ElementTree as ET, os, glob, csv, re, json

files = sorted(glob.glob("/Users/andy/Desktop/雪豹/儿子学习/英杰编程/二级题库/*.docx"))
output_dir = "/Users/andy/Desktop/二级题库CSV_v2"
os.makedirs(output_dir, exist_ok=True)

# === 答案库 ===
KEYS = {}
KEYS['202203'] = {}
# ... (答案库内容较长，从已保存的 answer_keys.json 加载)

# Load answer keys
ak_path = os.path.join(os.path.dirname(__file__), "answer_keys.json")
with open(ak_path) as f:
    KEYS = json.load(f)

for f in files:
    basename = os.path.splitext(os.path.basename(f))[0]
    year_key = basename[:6]
    answer_key = KEYS.get(year_key, {})
    print(f"处理: {basename}...")

    z = zipfile.ZipFile(f)
    xml = z.read("word/document.xml")
    tree = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines = []
    for p in tree.findall(".//w:p", ns):
        txt = "".join(t.text or "" for t in p.findall(".//w:t", ns)).strip()
        if txt: lines.append(txt)

    qs, codes = [], []
    i, sec = 0, None
    while i < len(lines):
        l = lines[i]
        if "选择题" in l: sec = "c"; i += 1; continue
        if "判断题" in l: sec = "t"; i += 1; continue
        if "编程题" in l: sec = "p"; i += 1; continue

        if sec == "p":
            m = re.match(r"^(\d{2})(.*)", l)
            if m:
                txt = m.group(2).strip(); i += 1
                while i < len(lines) and not re.match(r"^\d{2}", lines[i]) and not any(k in lines[i] for k in ["选择题","判断题","编程题"]):
                    txt += "\n" + lines[i]; i += 1
                codes.append((int(m.group(1)), txt))
                continue
            i += 1; continue

        m = re.match(r"^(\d{2})(.*)", l)
        if not m: i += 1; continue
        n = int(m.group(1)); t = m.group(2).strip()

        if sec == "c":
            fq, op = t, {}
            i += 1
            while i < len(lines) and not re.match(r"^\d{2}", lines[i]) and not any(k in lines[i] for k in ["选择题","判断题","编程题"]):
                om = re.match(r"^([A-D])\s*(.*)", lines[i])
                if om: op[om.group(1)] = om.group(2).strip()
                else: fq += "\n" + lines[i]
                i += 1
            a = answer_key.get(str(n), ["?"])
            qs.append([str(n),"单选",fq[:500],op.get("A",""),op.get("B",""),op.get("C",""),op.get("D",""),a[0],a[1] if len(a)>1 else ""])
        elif sec == "t":
            a = answer_key.get(str(n), ["?"])
            qs.append([str(n),"判断",t[:500],"","","","",a[0],a[1] if len(a)>1 else ""])
            i += 1

    for cn, ct in codes:
        a = answer_key.get(str(cn), ["", ""])
        qs.append([str(cn),"编程",ct[:1000],"","","","",a[0],a[1] if len(a)>1 else ""])
    qs.sort(key=lambda x: int(x[0]))

    with open(os.path.join(output_dir, f"{basename}.csv"), "w", encoding="utf-8-sig", newline="") as cf:
        w = csv.writer(cf)
        w.writerow(["序号","题型","题目","选项A","选项B","选项C","选项D","正确答案","解析"])
        w.writerows(qs)

    ans_c = sum(1 for q in qs if q[7] and q[7] != "?")
    print(f"  ✅ {len(qs)}题 ({sum(1 for q in qs if q[1]=='单选')}单选+{sum(1 for q in qs if q[1]=='判断')}判断+{sum(1 for q in qs if q[1]=='编程')}编程) 已答{ans_c}")

print(f"\n🎉 完成！文件在: {output_dir}")
