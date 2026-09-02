import csv
import json
import re
import statistics as st
from pathlib import Path

tid = "0519c619194248c78ac4bcff9430928b"
d = Path(r"d:/citylearn-demo/output/outkpis") / tid

print("=== files ===")
print([p.name for p in d.iterdir()])

cfg = json.loads((d / "chesca_agent_config.json").read_text(encoding="utf-8"))
print("TMP_max", cfg.get("TMP_max_reduction_percent"), "B_high", cfg.get("B_high"), "resmarl", cfg.get("resmarl_enabled"))

print("\n=== KPIs ===")
with open(d / "exported_kpis.csv", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
for r in rows:
    k = r["KPI"]
    if any(x in k.lower() for x in ["discomfort", "cost", "carbon", "electricity", "thermal", "unmet"]):
        print(f"{k}: D={r['District']} B1={r['Building_1']} B2={r['Building_2']} B3={r['Building_3']}")

with open(d / "chesca_trace.csv", encoding="utf-8-sig") as f:
    trows = list(csv.DictReader(f))


def fnum(x):
    try:
        return float(x)
    except Exception:
        return None


tmps = [fnum(r["action_tmp_final"]) for r in trows]
tmps = [x for x in tmps if x is not None]
tmps_s = sorted(tmps)
print("\n=== TMP final ===")
print(
    f"n={len(tmps)} mean={st.mean(tmps):.4f} median={st.median(tmps):.4f} "
    f"max={max(tmps):.4f} p90={tmps_s[int(0.9*len(tmps))]:.4f} "
    f"nonzero={sum(1 for x in tmps if abs(x)>1e-6)}/{len(tmps)} "
    f"zero_share={sum(1 for x in tmps if abs(x)<1e-6)/len(tmps):.3f}"
)
inits = [fnum(r["action_tmp_init"]) for r in trows]
inits = [x for x in inits if x is not None]
print(
    f"TMP init nonzero={sum(1 for x in inits if abs(x)>1e-6)}/{len(inits)} mean={st.mean(inits):.4f} max={max(inits):.4f}"
)

# check if task copy of cooling controller has our fix
for cand in [
    d / "checa" / "cooling_device_controller" / "cooling_device_controller.py",
    d / "CHESCA-copy" / "checa" / "cooling_device_controller" / "cooling_device_controller.py",
]:
    if cand.exists():
        txt = cand.read_text(encoding="utf-8", errors="ignore")
        print("task copy", cand, "added_temp=0", "added_temp_to_setpoint = 0.0" in txt or "added_temp_to_setpoint = 0" in txt)
        print("  has min_cool", "min_cool_per_c_overheat" in txt)

# source tree used by run - check local_evaluation and import path
lec = d / "local_evaluation_copy.py"
if lec.exists():
    t = lec.read_text(encoding="utf-8", errors="ignore")
    for line in t.splitlines():
        if "CHESCA" in line or "sys.path" in line or "checa" in line:
            if "import" in line or "path" in line.lower() or "CHESCA" in line:
                print("lec:", line[:160])

# narrative parse indoor/set/pid/tmp
data = json.loads((d / "decision_trace.json").read_text(encoding="utf-8"))
pids, tmps_n, deltas, outdoors = [], [], [], []
for s in data["steps"]:
    for b in s.get("buildings") or []:
        for ln in b.get("narrative_lines") or []:
            if "[制冷" not in ln and "[空调" not in ln:
                continue
            m = re.search(r"室内温度：([-\d.]+)", ln)
            inn = float(m.group(1)) if m else None
            m = re.search(r"设定温度：([-\d.]+)", ln)
            sp = float(m.group(1)) if m else None
            m = re.search(r"室外温度：([-\d.]+)", ln)
            if m:
                outdoors.append(float(m.group(1)))
            m = re.search(r"(?:PID 原始电需求|原始电需求)：([-\d.]+)", ln)
            if not m:
                m = re.search(r"电需求为\s*([-\d.]+)", ln)
            if m:
                pids.append(float(m.group(1)))
            m = re.search(r"(?:clip 后 TMP 动作|经裁剪后 TMP 动作|TMP 动作)\s*([-\d.]+)", ln)
            if not m:
                m = re.search(r"动作指令为\s*([-\d.]+)", ln)
            if m:
                tmps_n.append(float(m.group(1)))
            if inn is not None and sp is not None:
                deltas.append(inn - sp)

print("\n=== from narratives ===")
print("n cool lines deltas", len(deltas), "pids", len(pids), "tmps", len(tmps_n))
if deltas:
    print(
        f"indoor-set mean={st.mean(deltas):.3f} hot_share={sum(1 for x in deltas if x>0)/len(deltas):.3f} "
        f"hot>1={sum(1 for x in deltas if x>1)/len(deltas):.3f} max={max(deltas):.3f}"
    )
if pids:
    print(
        f"pid mean={st.mean(pids):.3f} max={max(pids):.3f} pos_share={sum(1 for x in pids if x>0)/len(pids):.3f}"
    )
if tmps_n:
    print(
        f"narr tmp mean={st.mean(tmps_n):.4f} max={max(tmps_n):.4f} nonzero={sum(1 for x in tmps_n if abs(x)>1e-6)}"
    )
if outdoors:
    print(f"outdoor mean={st.mean(outdoors):.2f} max={max(outdoors):.2f}")

# sample lines when hot
print("\n=== sample when indoor>set+1 ===")
nshow = 0
for s in data["steps"]:
    for b in s.get("buildings") or []:
        for ln in b.get("narrative_lines") or []:
            if "[制冷" not in ln and "[空调" not in ln:
                continue
            m1 = re.search(r"室内温度：([-\d.]+)", ln)
            m2 = re.search(r"设定温度：([-\d.]+)", ln)
            if not m1 or not m2:
                continue
            if float(m1.group(1)) - float(m2.group(1)) > 1.0:
                print(f"step={s.get('step')} b={b.get('building')}: {ln[:200]}")
                nshow += 1
                if nshow >= 8:
                    break
        if nshow >= 8:
            break
    if nshow >= 8:
        break

# compare previous broken run
print("\n=== compare prev TMP=0 run ===")
for tid2, label in [
    ("10546838002a4af98a20ea52718987e3", "before_fix"),
    ("0519c619194248c78ac4bcff9430928b", "latest"),
]:
    with open(Path(r"d:/citylearn-demo/output/outkpis") / tid2 / "exported_kpis.csv", encoding="utf-8-sig") as f:
        m = {r["KPI"]: r["District"] for r in csv.DictReader(f)}
    print(
        label,
        "discomfort",
        m.get("discomfort_proportion"),
        "hot",
        m.get("discomfort_hot_proportion"),
        "hot_delta",
        m.get("discomfort_hot_delta_average"),
        "cost",
        m.get("cost_total"),
        "elec",
        m.get("electricity_consumption_total"),
    )
