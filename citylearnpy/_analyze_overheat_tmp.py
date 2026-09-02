import csv
import json
import re
import statistics as st
from pathlib import Path

tid = "0519c619194248c78ac4bcff9430928b"
d = Path(r"d:/citylearn-demo/output/outkpis") / tid
data = json.loads((d / "decision_trace.json").read_text(encoding="utf-8"))

rows = []
for s in data["steps"]:
    for b in s.get("buildings") or []:
        cool = None
        for ln in b.get("narrative_lines") or []:
            if "[制冷" in ln or "[空调" in ln:
                cool = ln
                break
        if not cool:
            continue
        m1 = re.search(r"室内温度：([-\d.]+)", cool)
        m2 = re.search(r"设定温度：([-\d.]+)", cool)
        m3 = re.search(r"室外温度：([-\d.]+)", cool)
        m4 = re.search(r"(?:原始电需求|电需求)[:：为]\s*([-\d.]+)", cool)
        m5 = re.search(r"(?:TMP 动作|动作指令为)\s*([-\d.]+)", cool)
        acts = b.get("actions") or {}
        tmp = None
        if isinstance(acts.get("final"), dict):
            tmp = acts["final"].get("tmp")
        if tmp is None:
            tmp = acts.get("tmp")
        inn = float(m1.group(1)) if m1 else None
        sp = float(m2.group(1)) if m2 else None
        if inn is None or sp is None:
            continue
        rows.append(
            {
                "step": s.get("step"),
                "b": b.get("building"),
                "inn": inn,
                "sp": sp,
                "out": float(m3.group(1)) if m3 else None,
                "pid": float(m4.group(1)) if m4 else None,
                "tmp": float(tmp) if tmp is not None else (float(m5.group(1)) if m5 else None),
                "delta": inn - sp,
            }
        )

print("n", len(rows))
deltas = [r["delta"] for r in rows]
print(
    f"delta mean={st.mean(deltas):.3f} hot_share={sum(1 for x in deltas if x>0)/len(deltas):.3f} "
    f">1={sum(1 for x in deltas if x>1)/len(deltas):.3f} >2={sum(1 for x in deltas if x>2)/len(deltas):.3f} max={max(deltas):.3f}"
)

# when hot, what tmp?
hot = [r for r in rows if r["delta"] > 0.5 and r["tmp"] is not None]
print("hot>0.5 n", len(hot))
if hot:
    print(
        f"  tmp mean={st.mean(r['tmp'] for r in hot):.4f} max={max(r['tmp'] for r in hot):.4f} "
        f"delta mean={st.mean(r['delta'] for r in hot):.3f}"
    )

# buckets
for lo, hi in [(0, 0.5), (0.5, 1), (1, 2), (2, 5), (5, 20)]:
    sub = [r for r in rows if lo <= r["delta"] < hi and r["tmp"] is not None]
    if not sub:
        continue
    print(
        f"delta[{lo},{hi}): n={len(sub)} tmp_mean={st.mean(r['tmp'] for r in sub):.4f} "
        f"tmp_max={max(r['tmp'] for r in sub):.4f}"
    )

# from chesca_trace directly
with open(d / "chesca_trace.csv", encoding="utf-8-sig") as f:
    trows = list(csv.DictReader(f))
tmps = [float(r["action_tmp_final"]) for r in trows]
print("trace tmp>0.2", sum(1 for x in tmps if x > 0.2), "tmp>0.5", sum(1 for x in tmps if x > 0.5))
