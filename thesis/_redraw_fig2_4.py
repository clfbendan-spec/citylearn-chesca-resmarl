"""重画 thesis/images/pictures/残差合成图.pdf

v2 修订（2026-10-18）：
  原图 2-4 标题写凸组合 `a_final = clip((1-α)·a_base + α·mask(a_rl))`，
  与论文式 (2-X) 残差加法 `a_最终 = a_基线 + δ, |δ| ≤ α` 不一致。
  现改为残差加法 + 三层安全包络的形式（与正文 §2.3.3 三层包络完全对应）：
    1) 通道掩码 mask(·)：屏蔽空调/热水，仅保留电池充放电维度
    2) 幅度夹断：|δ| ≤ α
    3) 电池低电量门控：SOC < SOC_min 时断路
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams["font.sans-serif"] = ["SimHei", "SimSun", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

W, H = 13.0, 7.2
fig, ax = plt.subplots(figsize=(W, H), dpi=120)
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("white")


def box(x, y, w, h, fill, edge, lw=1.6, radius=0.18, alpha=0.55):
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.02,rounding_size={radius}",
        linewidth=lw, edgecolor=edge, facecolor=fill, alpha=alpha,
    )
    ax.add_patch(p)


def text(x, y, s, fontsize=11, weight="normal", color="black",
         ha="center", va="center"):
    ax.text(x, y, s, fontsize=fontsize, weight=weight, color=color,
            ha=ha, va=va)


def arrow(x1, y1, x2, y2, color="#444", lw=1.6, style="-|>"):
    a = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, mutation_scale=18,
        linewidth=lw, color=color, shrinkA=2, shrinkB=2,
    )
    ax.add_patch(a)


# ----- 顶部公式条 -----
box(0.4, H - 1.0, W - 0.8, 0.7, "#efe4ff", "#6a3eb4", lw=1.6)
text(W / 2, H - 0.55,
     r"残差合成：$a_{\mathrm{final}} = a_{\mathrm{base}} + \delta,\quad |\delta| \leq \alpha$",
     fontsize=18, weight="bold", color="#4d2480")
text(W / 2, H - 0.95,
     "「基线保底 + 残差微调」——$\\alpha \\in [0,1]$ 为残差夹断上限，"
     "$\\alpha{=}0$ 退化为纯规则基线，$\\alpha{=}1$ 残差幅度上限为 1",
     fontsize=10.5, color="#3b1e63")

# ----- 左：基线动作 a_base -----
LBLUE = "#cfe5ff"; EBLUE = "#1f4e9c"
box(0.4, 2.0, 3.6, 2.6, LBLUE, EBLUE, lw=1.6)
text(2.2, 4.30, "分层先验基线", fontsize=13, weight="bold", color=EBLUE)
text(2.2, 4.00, "$a_{\\mathrm{base}}$", fontsize=15, weight="bold", color=EBLUE)
text(2.2, 3.55, "DHW 热水规则", fontsize=10.5, color="#1d3d52")
text(2.2, 3.25, "ELE 电池 A* 树搜索", fontsize=10.5, color="#1d3d52")
text(2.2, 2.95, "TMP 本地 PID", fontsize=10.5, color="#1d3d52")
text(2.2, 2.60, "（含 SOC/键温/动作空间约束）", fontsize=9.5, color="#335")
text(2.2, 2.25, "输出三动作张量", fontsize=9.5, color="#335")

# ----- 左下：各建筑独立 SAC 策略 → 输出残差 δ -----
LGREEN = "#d4f1de"; EGREEN = "#2c8f5a"
box(0.4, 0.2, 3.6, 1.55, LGREEN, EGREEN, lw=1.6)
text(2.2, 1.45, "各建筑独立 SAC 策略", fontsize=12, weight="bold", color=EGREEN)
text(2.2, 1.13, "$\\delta \\in [\\mathrm{DHW}, \\mathrm{ELE}, \\mathrm{TMP}]$",
     fontsize=12, color=EGREEN)
text(2.2, 0.75, "仅学习叠加在基线之上的微小修正量", fontsize=9.5, color="#1d4d33")
text(2.2, 0.42, "不对空调/热水维直接输出", fontsize=9.5, color="#1d4d33")

# ----- 中：三层安全包络 -----
LPURPLE = "#e3d6ff"; EPURPLE = "#6a3eb4"
box(4.5, 1.2, 3.6, 3.6, LPURPLE, EPURPLE, lw=1.8)
text(6.3, 4.55, "三层安全包络（顺序裁剪）", fontsize=12, weight="bold", color=EPURPLE)

# 第 1 层：通道掩码
text(6.3, 4.10, "① 通道掩码", fontsize=11, weight="bold", color=EPURPLE)
text(6.3, 3.78, "$\\mathrm{TMP}\\!=\\!0,\\ \\mathrm{DHW}\\!=\\!0$",
     fontsize=10.5, color="#3b1e63")
text(6.3, 3.50, "仅保留 ELE 电池充放电维", fontsize=9.5, color="#3b1e63")

# 第 2 层：幅度夹断
text(6.3, 3.10, "② 幅度夹断", fontsize=11, weight="bold", color=EPURPLE)
text(6.3, 2.80, "$|\\delta| \\leq \\alpha$", fontsize=11, color="#3b1e63")
text(6.3, 2.50, "硬上限 $\\alpha$（默认 0.05）", fontsize=9.5, color="#3b1e63")

# 第 3 层：低电量门控
text(6.3, 2.10, "③ 低电量门控", fontsize=11, weight="bold", color=EPURPLE)
text(6.3, 1.80, "若 $\\mathrm{SOC} < \\mathrm{SOC}_{\\min}$", fontsize=10, color="#3b1e63")
text(6.3, 1.50, "则断路 $\\delta\\!=\\!0$（防提前放空）", fontsize=9.5, color="#3b1e63")

# ----- 右：a_final -----
LORG = "#ffe4b3"; EORG = "#c4640d"
box(8.6, 2.2, 4.0, 1.9, LORG, EORG, lw=1.8)
text(10.6, 3.80, "最终动作", fontsize=13, weight="bold", color=EORG)
text(10.6, 3.45, "$a_{\\mathrm{final}}$", fontsize=20, weight="bold", color=EORG)
text(10.6, 2.92, "$[\\mathrm{ELE}] \\times N$", fontsize=11, color="#5b3500")
text(10.6, 2.55, "（仅电池充放电）", fontsize=10, color="#5b3500")
text(10.6, 2.25, "送 CityLearn 环境执行", fontsize=10, color="#5b3500")

# ----- 连线 -----
# 基线 → 三层包络
arrow(4.0, 3.30, 4.5 - 0.02, 3.20, color=EBLUE, lw=1.8)
# SAC 策略 → 三层包络
arrow(4.0, 1.00, 4.5 - 0.02, 1.70, color=EGREEN, lw=1.8)
# 三层包络 → 最终动作
arrow(8.1, 3.10, 8.6 - 0.02, 3.10, color=EPURPLE, lw=1.8)

# ----- 底部说明 -----
note_y = 0.05
ax.text(W / 2, note_y,
        "· 残差公式严格对应正文式 (2-?): a_最终 = a_基线 + δ；三层包络顺序裁剪后送入仿真环境。\n"
        "· 残差只在第 5 阶段介入，不改任何基线规则参数；α 与掩码 m 均可在评估任务里配置，"
        "无需重新训练。\n"
        "· 纯基线入口关闭残差，a_final = a_base，用于对照实验。",
        fontsize=9.0, color="#333", ha="center", va="bottom")

# 输出
out_pdf = r"D:\citylearn-demo\thesis\images\pictures\残差合成图.pdf"
out_png = r"D:\citylearn-demo\thesis\images\pictures\残差合成图.png"
plt.savefig(out_pdf, bbox_inches="tight", facecolor="white", pad_inches=0.10)
plt.savefig(out_png, dpi=240, bbox_inches="tight", facecolor="white", pad_inches=0.10)
plt.close(fig)
print("SAVED:", out_pdf)
print("SAVED:", out_png)
