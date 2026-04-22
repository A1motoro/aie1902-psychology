import json
import re
from pathlib import Path

src = Path("anotated/question1(1).txt")
dst = Path("anotated/1.json")

text = src.read_text(encoding="utf-8")

parts = re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL)

instruction = "在过去的两周里，以下问题困扰您的频率如何？感到紧张，焦虑或烦躁"
out = []
for p in parts:
    obj = json.loads(p)
    resp = obj.get("user_response", "")
    score = obj.get("annotator_score", "")
    conf = obj.get("annotator_confidence", "")
    out.append({
        "instruction": instruction,
        "input": resp,
        "output": str(score),
        "annotator_score": str(score),
        "annotator_confidence": str(conf),
    })

dst.write_text(
    json.dumps(out, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"wrote {len(out)} items to {dst}")
