# -*- coding: utf-8 -*-
"""Generate thesis overview figure: core challenges vs improvement solutions."""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

out = Path(r"d:\citylearn-demo\thesis\images\pictures")
out.mkdir(parents=True, exist_ok=True)
path = out / "核心难题与改进方案.png"

fig, ax = plt.subplots(figsize=(11.8, 7.6), dpi=220)
ax.set_xlim(0, 118)
ax.set_ylim(0, 76)
ax.axis("off")
fig.patch.set_facecolor("white")


def box(x, y, w, h, face, edge, lw=1.5, radius=0.4):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.02,rounding_size={radius}",
        linewidth=lw,
        facecolor=face,
        edgecolor=edge,
    )
    ax.add_patch(patch)


def label(x, y, s, size=10.5, weight="normal", color="#1f2937"):
    ax.text(
        x,
        y,
        s,
        fontsize=size,
        fontweight=weight,
        color=color,
        ha="center",
        va="center",
        linespacing=1.38,
    )


def arrow(x1, y1, x2, y2, color="#4b5563", lw=1.7):
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=12),
    )


# Title
box(16, 67.5, 86, 6.5, "#eef6ff", "#2563eb", lw=1.9)
label(59, 70.75, "基于多智能体强化学习的建筑群节能控制", size=14.5, weight="bold", color="#1e3a8a")

# Subtitle
box(29, 61.8, 60, 4.2, "#f8fafc", "#94a3b8", lw=1.2)
label(59, 63.9, "改进前核心难题  →  对应改进方案", size=12, weight="bold", color="#334155")

# Column headers
box(5, 54.8, 50, 4.8, "#fff1f2", "#e11d48", lw=1.6)
label(30, 57.2, "三类核心难题", size=12.5, weight="bold", color="#9f1239")

box(63, 54.8, 50, 4.8, "#ecfdf5", "#059669", lw=1.6)
label(88, 57.2, "三类改进方案", size=12.5, weight="bold", color="#065f46")

challenges = [
    (
        "核心难题一",
        "基线稳健但自适应不足\nCHESCA参数相对静态，难以及时\n适应负荷漂移与极端天气",
        "#fff7ed",
        "#ea580c",
    ),
    (
        "核心难题二",
        "纯MARL难安全落地\n样本效率低、训练不稳定，\n易违反设备与舒适性约束",
        "#fef3c7",
        "#d97706",
    ),
    (
        "核心难题三",
        "难管理、难理解、难使用\n实验难复现，决策过程不透明，\n算法成果难工程化配置",
        "#fce7f3",
        "#db2777",
    ),
]
solutions = [
    (
        "改进方案一",
        "固化CHESCA分层基线\n复现预测/PID/电池树搜索链路，\n建立标准化状态动作与KPI接口",
        "#eff6ff",
        "#2563eb",
    ),
    (
        "改进方案二",
        "CHESCA-ResMARL残差学习\n在基准动作上学习安全残差修正，\n结合动作掩码与安全投影",
        "#ecfeff",
        "#0891b2",
    ),
    (
        "改进方案三",
        "可视化管理平台\n贯通数据、任务、KPI与决策轨迹，\n实现可复现、可解释、可用",
        "#f0fdf4",
        "#16a34a",
    ),
]

ys = [42.2, 26.8, 11.4]
for i, y in enumerate(ys):
    ct, cd, cf, ce = challenges[i]
    st, sd, sf, se = solutions[i]
    box(5, y, 50, 12.0, cf, ce, lw=1.6)
    label(30, y + 9.0, ct, size=11.5, weight="bold", color=ce)
    label(30, y + 4.4, cd, size=9.7, color="#374151")

    box(63, y, 50, 12.0, sf, se, lw=1.6)
    label(88, y + 9.0, st, size=11.5, weight="bold", color=se)
    label(88, y + 4.4, sd, size=9.7, color="#374151")

    arrow(55.2, y + 6.0, 62.7, y + 6.0, color=se, lw=1.8)

# Bottom synthesis
box(16, 1.6, 86, 7.5, "#f5f3ff", "#7c3aed", lw=1.9, radius=0.5)
label(
    59,
    6.55,
    "总体目标：CHESCA-ResMARL混合控制 + 可视化管理平台",
    size=12.2,
    weight="bold",
    color="#5b21b6",
)
label(
    59,
    3.55,
    "先验保安全、学习求增益，贯通“数据—训练—评估—解释”闭环",
    size=10.2,
    color="#4c1d95",
)

# Converging arrows into bottom box
arrow(30, 11.2, 42, 9.2, color="#7c3aed", lw=1.5)
arrow(59, 11.2, 59, 9.2, color="#7c3aed", lw=1.5)
arrow(88, 11.2, 76, 9.2, color="#7c3aed", lw=1.5)

fig.savefig(path, bbox_inches="tight", facecolor="white", edgecolor="none")
print(f"saved: {path}")
print(f"size: {path.stat().st_size}")
