# -*- coding: utf-8 -*-
"""生成论文用图：CHESCA-ResMARL 两层控制框架（替换原占位图）。

依据代码实测：
  · 第 1 层 CHESCA 规则基线 = 单步流程 ①–④（预测 / 初稿 / 未来用电 / 电池 refine），
    硬约束（min_soc、容量·DoD、复电与过热禁充）内嵌其中 ⇒ 输出 a_base
    见 checa/agent.py:405 / 1075（详见图「CHESCA单步流程图」）
  · 第 2 层 Multi-Agent SAC 残差：逐栋 agent，输入 CHESCA 状态 + 环境观测，
    输出绝对动作 a_rl；离线由 Multi-agent.py 训练，评估阶段冻结加载 checkpoint
  · 融合层 = 单步流程阶段 5：a_final = clip((1-α)·a_base + α·mask(a_rl))
    见 checa/agent.py:351-399（docstring 明写 a_final = clip((1−α)·a_base + α·a_rl_masked)）
  · α=0 / 未启用 ⇒ 原样返回 a_base；ELE 残差生效时会同步重算 predicted_battery_demand
"""

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(r"d:\citylearn-demo\thesis\images\pictures")
OUT.mkdir(parents=True, exist_ok=True)
PNG = OUT / "CHESCA-ResMARL框架.png"
PDF = OUT / "CHESCA-ResMARL框架.pdf"
BACKUP = OUT / "CHESCA-ResMARL框架_占位图备份.png"

if PNG.is_file() and not BACKUP.is_file():
    shutil.copy2(PNG, BACKUP)
    print(f"占位图已备份: {BACKUP}")

C_IO = ("#fefce8", "#ca8a04")
C_L1 = ("#eff6ff", "#2563eb")
C_L2 = ("#ecfdf5", "#059669")
C_FUSE = ("#f5f3ff", "#7c3aed")
C_ENV = ("#f8fafc", "#64748b")
C_TRAIN = ("#ffffff", "#94a3b8")
GREY = "#6b7280"
INK = "#1f2937"

fig, ax = plt.subplots(figsize=(14.6, 10.6), dpi=220)
ax.set_xlim(0, 146)
ax.set_ylim(0, 106)
ax.axis("off")
fig.patch.set_facecolor("white")


def box(x, y, w, h, colors, lw=1.5, radius=0.45, dashed=False):
    face, edge = colors
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0.02,rounding_size={radius}",
        linewidth=lw, facecolor=face, edgecolor=edge,
        linestyle="--" if dashed else "-"))


def text(x, y, s, size=10.0, weight="normal", color=INK, ha="center", va="center"):
    ax.text(x, y, s, fontsize=size, fontweight=weight, color=color,
            ha=ha, va=va, linespacing=1.5)


def arrow(x1, y1, x2, y2, color="#4b5563", lw=1.7, dashed=False, rad=0.0):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=14,
                                linestyle="--" if dashed else "-",
                                connectionstyle=f"arc3,rad={rad}"))


# ------------------------------------------------------------------ 标题
box(10, 99.0, 126, 5.6, ("#eef6ff", "#2563eb"), lw=1.9)
text(73, 101.8, "CHESCA-ResMARL 两层控制框架", size=15.5, weight="bold", color="#1e3a8a")
text(73, 97.2, "第 1 层固定安全基线，第 2 层只学习有限残差修正；训练与推理解耦",
     size=10.2, color="#334155")

# ------------------------------------------------------------------ 观测
box(9, 89.4, 128, 5.6, C_IO, lw=1.6)
text(73, 92.2, "环境观测 o(t)：电价 / 净负荷 / 电池 SOC / 室内外温度 / 小时",
     size=10.2, weight="bold", color="#854d0e")
text(73, 90.3, "由 CityLearn 环境逐步给出（逐建筑）", size=8.4, color="#a16207")

# ------------------------------------------------------------------ 第 1 层
L1Y, L1H = 64.0, 22.4
box(9, L1Y, 90, L1H, C_L1, lw=1.9)
text(54, L1Y + L1H - 2.4, "第 1 层　CHESCA 规则基线（先验知识，无学习参数，评估阶段冻结）",
     size=11.2, weight="bold", color="#1e40af")

CHIPS = [
    ("① 预测", "电价 / 负荷 / 温度\n多模型集成"),
    ("② 动作初稿", "冷机 PID + DHW 规则\n（正常 / 停电分支）"),
    ("③ 未来用电", "未来制冷与热水\n负荷估计"),
    ("④ 电池 refine", "min_soc 下界 → 树搜索 →\n电价感知 → 复电限流 → 阈值"),
]
cx = 11.5
for i, (title, body) in enumerate(CHIPS):
    box(cx, L1Y + 7.4, 20.8, 9.4, ("#ffffff", "#3b82f6"), lw=1.3)
    text(cx + 10.4, L1Y + 14.6, title, size=9.0, weight="bold", color="#1d4ed8")
    text(cx + 10.4, L1Y + 10.6, body, size=7.8, color="#374151")
    if i < len(CHIPS) - 1:
        arrow(cx + 20.8, L1Y + 12.1, cx + 21.9, L1Y + 12.1, color="#60a5fa", lw=1.4)
    cx += 21.9

text(54, L1Y + 5.4, "硬约束内嵌：SOC 上下限 · 电池容量 / DoD · 复电缓充与过热禁充 · 动作裁剪",
     size=8.8, color="#1e3a8a")
box(21.0, L1Y + 0.9, 66.0, 3.6, ("#dbeafe", "#2563eb"), lw=1.4, radius=0.35)
text(54, L1Y + 2.7, "输出基准动作 a_base = [DHW, ELE, TMP] × N 栋（安全、可解释）",
     size=9.2, weight="bold", color="#1e3a8a")

# ------------------------------------------------------------------ 右侧：离线训练
box(103, 68.6, 34, 17.8, C_TRAIN, lw=1.5, dashed=True)
text(120, 84.2, "离线训练（一次性）", size=10.0, weight="bold", color="#475569")
text(120, 78.4, "Multi-agent.py\n逐栋 SAC 独立训练\n（train-schema 数据集）",
     size=8.4, color="#475569")
text(120, 72.4, "产出 checkpoint\n评估时只加载、不更新", size=8.4, color="#475569")
arrow(120, 68.4, 120, 60.2, color="#94a3b8", lw=1.6, dashed=True)

# ------------------------------------------------------------------ 第 2 层
L2Y, L2H = 42.0, 16.2
box(9, L2Y, 90, L2H, C_L2, lw=1.9)
text(54, L2Y + L2H - 2.3, "第 2 层　Multi-Agent SAC 残差策略（推理阶段冻结，不更新参数）",
     size=11.2, weight="bold", color="#065f46")

CHIPS2 = [
    ("逐栋策略 π_i", "每个建筑一个 SAC agent\n仅使用本地观测"),
    ("输入状态", "小时 · 预测值\n电池 / 热水 SOC · 净负荷均值"),
    ("输出残差动作", "绝对动作 a_rl\n= [DHW, ELE, TMP] × N 栋"),
]
cx = 11.5
for title, body in CHIPS2:
    box(cx, L2Y + 2.0, 28.0, 10.0, ("#ffffff", "#10b981"), lw=1.3)
    text(cx + 14.0, L2Y + 9.4, title, size=9.2, weight="bold", color="#047857")
    text(cx + 14.0, L2Y + 5.4, body, size=8.0, color="#374151")
    cx += 29.5

# ------------------------------------------------------------------ 右侧：关键参数
box(103, 42.0, 34, 16.2, ("#ffffff", "#7c3aed"), lw=1.5)
text(120, 55.6, "关键参数（评估时可调）", size=9.6, weight="bold", color="#5b21b6")
text(120, 49.6, "α　残差强度\n掩码 m　DHW / ELE / TMP 逐维开关\ncheckpoint　模型目录",
     size=8.3, color="#4c1d95")


# ------------------------------------------------------------------ 融合层
FY, FH = 27.0, 12.0
box(9, FY, 128, FH, C_FUSE, lw=1.9)
text(73, FY + FH - 2.4, "融合层（CHESCA 单步流程的阶段 5）", size=11.2,
     weight="bold", color="#5b21b6")
box(16, FY + 2.2, 52, 5.2, ("#ede9fe", "#7c3aed"), lw=1.5, radius=0.35)
text(42, FY + 4.8, "a_final = clip( (1-α)·a_base + α·mask(a_rl) )",
     size=11.0, weight="bold", color="#4c1d95")
text(96, FY + 4.8, "掩码关掉的维度保持 a_base 原值；α=0 → 严格退化为纯 CHESCA\n"
                   "安全投影：裁剪到动作空间上下限，基线硬约束始终成立",
     size=8.5, color="#4c1d95")

# 第 1 层 → 融合层：走左侧空白通道，竖线不压第 2 层
ax.plot([13.5, 5.0, 5.0], [64.0, 64.0, 33.6], color="#2563eb", lw=1.7)
arrow(5.0, 33.6, 8.6, 33.6, color="#2563eb", lw=1.7)
# 第 2 层 → 融合层：走右侧空白通道
ax.plot([99.0, 141.0, 141.0], [40.4, 40.4, 33.6], color="#059669", lw=1.7)
arrow(141.0, 33.6, 137.4, 33.6, color="#059669", lw=1.7)

# ------------------------------------------------------------------ 环境 + 输出
box(9, 12.4, 90, 12.0, C_ENV, lw=1.7)
text(54, 21.4, "CityLearn 环境执行 a_final → 返回下一步观测 o(t+1)",
     size=10.6, weight="bold", color="#334155")
text(54, 17.4, "奖励 = 电费 + 制冷电费 + 电池套利 + 电池损耗 + 热舒适（权重可配置）",
     size=8.8, color="#475569")
text(54, 14.4, "停电等极端工况由第 1 层规则兜底，残差仅在非停电工况生效",
     size=8.4, color=GREY)

box(103, 12.4, 34, 12.0, ("#f1f5f9", "#64748b"), lw=1.5)
text(120, 21.4, "输出与可追溯", size=9.8, weight="bold", color="#334155")
text(120, 17.0, "KPI：成本 / 碳排 / 峰值 / 不适 / 零净能\n决策轨迹与 KPI 记录\n（可复现、可解释）",
     size=8.2, color="#475569")

arrow(54, FY - 0.4, 54, 24.9, color="#7c3aed", lw=1.8)
arrow(99.5, 18.4, 102.6, 18.4, color="#64748b", lw=1.6)
arrow(9.6, 18.4, 2.6, 18.4, color="#ca8a04", lw=1.5, rad=0.0)
arrow(2.6, 18.4, 2.6, 92.2, color="#ca8a04", lw=1.5)
arrow(2.6, 92.2, 8.6, 92.2, color="#ca8a04", lw=1.5)

# ------------------------------------------------------------------ 底部说明
text(9, 8.6, "· 两层分工：第 1 层给出安全可解释的基准动作；第 2 层只学习「相对基线的有限修正」，不改变主链路",
     size=8.8, color="#334155", ha="left")
text(9, 5.4, "· 训练与推理解耦：SAC 离线训练一次并保存 checkpoint，评估阶段仅前向推理即可复用",
     size=8.8, color="#334155", ha="left")
text(9, 2.2, "· 消融友好：α=0 或掩码全关时严格等于纯 CHESCA，可直接作为对照基线",
     size=8.8, color="#334155", ha="left")

fig.savefig(PNG, bbox_inches="tight", facecolor="white", edgecolor="none")
fig.savefig(PDF, bbox_inches="tight", facecolor="white", edgecolor="none")
print(f"saved: {PNG}  ({PNG.stat().st_size} bytes)")
print(f"saved: {PDF}  ({PDF.stat().st_size} bytes)")
