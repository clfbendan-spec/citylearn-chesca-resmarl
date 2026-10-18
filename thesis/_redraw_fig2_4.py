"""重画 thesis/images/pictures/残差合成图

v3 修订（2026-10-18 晚）：
  1) 公式改为与论文式 (2-6) 完全一致的展开形式：
       delta = alpha * s * (m ⊙ a_RL) * g
       a_final = clip(a_base + delta)
     并给出 |delta| <= alpha 的可推导依据（s=1, |a_RL|<=1, m,g ∈ {0,1}）。
  2) 修掉旧版的「式 (2-?)」未解析占位符。
  3) 修掉底部三行说明与左下绿框文字重叠（重排版：画布加高、绿框上移、说明独占底部带）。
  4) 术语按全文统一口径：
       分层先验基线 -> 分层规则基线
       三层安全包络 -> 三层安全防护
       幅度夹断     -> 幅度上限裁剪
       残差夹断上限 -> 残差幅度上限
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams["font.sans-serif"] = ["SimHei", "SimSun", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

W, H = 13.0, 7.9
fig, ax = plt.subplots(figsize=(W, H), dpi=120)
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("white")


def box(x, y, w, h, fill, edge, lw=1.6, radius=0.18, alpha=0.55):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.02,rounding_size={radius}",
        linewidth=lw, edgecolor=edge, facecolor=fill, alpha=alpha,
    ))


def text(x, y, s, fontsize=11, weight="normal", color="black",
         ha="center", va="center"):
    ax.text(x, y, s, fontsize=fontsize, weight=weight, color=color,
            ha=ha, va=va)


def arrow(x1, y1, x2, y2, color="#444", lw=1.6):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=18,
        linewidth=lw, color=color, shrinkA=2, shrinkB=2,
    ))


# ----- 顶部公式条 -----
box(0.4, H - 1.12, W - 0.8, 0.86, "#efe4ff", "#6a3eb4", lw=1.6)
text(W / 2, H - 0.48,
     r"残差合成：$a_{\mathrm{final}} = "
     r"\mathrm{clip}\!\left(a_{\mathrm{base}} + \alpha\cdot s\cdot"
     r"(m\odot a_{\mathrm{RL}})\cdot g\right),\quad |\delta|\leq\alpha$",
     fontsize=16.5, weight="bold", color="#4d2480")
text(W / 2, H - 0.92,
     r"「基线保底 + 残差微调」—— $\alpha \in [0,1]$ 为残差幅度上限，"
     r"$\alpha{=}0$ 时 $\delta\equiv 0$，严格退化为纯分层规则基线",
     fontsize=10.5, color="#3b1e63")

# ----- 左：分层规则基线 -----
LBLUE = "#cfe5ff"; EBLUE = "#1f4e9c"
box(0.4, 3.55, 3.6, 2.45, LBLUE, EBLUE, lw=1.6)
text(2.2, 5.68, "分层规则基线", fontsize=13, weight="bold", color=EBLUE)
text(2.2, 5.38, r"$a_{\mathrm{base}}$", fontsize=15, weight="bold", color=EBLUE)
text(2.2, 4.96, "DHW 热水规则", fontsize=10.5, color="#1d3d52")
text(2.2, 4.66, "ELE 电池 A* 树搜索", fontsize=10.5, color="#1d3d52")
text(2.2, 4.36, "TMP 本地 PID", fontsize=10.5, color="#1d3d52")
text(2.2, 4.02, "（含 SOC / 键温 / 动作空间约束）", fontsize=9.5, color="#335")
text(2.2, 3.75, "输出三动作张量", fontsize=9.5, color="#335")

# ----- 左下：各建筑独立残差策略 -----
LGREEN = "#d4f1de"; EGREEN = "#2c8f5a"
box(0.4, 1.35, 3.6, 1.95, LGREEN, EGREEN, lw=1.6)
text(2.2, 3.00, "各建筑独立残差策略", fontsize=12, weight="bold", color=EGREEN)
text(2.2, 2.66, r"$a_{\mathrm{RL}} \in [-1,\,1]^3$", fontsize=12, color=EGREEN)
text(2.2, 2.30, "逐维对应 [DHW, ELE, TMP]", fontsize=9.5, color="#1d4d33")
text(2.2, 2.02, "只学相对基线的微小修正量", fontsize=9.5, color="#1d4d33")
text(2.2, 1.72, "空调温控维由掩码强制归零", fontsize=9.5, color="#1d4d33")

# ----- 中：三层安全防护 -----
LPURPLE = "#e3d6ff"; EPURPLE = "#6a3eb4"
box(4.5, 2.05, 3.6, 4.0, LPURPLE, EPURPLE, lw=1.8)
text(6.3, 5.72, "三层安全防护（按顺序裁剪）", fontsize=11.8, weight="bold", color=EPURPLE)

text(6.3, 5.28, "① 通道掩码 $m$", fontsize=11, weight="bold", color=EPURPLE)
text(6.3, 4.98, r"$\mathrm{TMP}\!=\!0,\ \ \mathrm{DHW}\!=\!0$", fontsize=10.5, color="#3b1e63")
text(6.3, 4.72, "仅保留 ELE 电池充放电维", fontsize=9.5, color="#3b1e63")

text(6.3, 4.26, "② 幅度上限裁剪 $\\alpha$", fontsize=11, weight="bold", color=EPURPLE)
text(6.3, 3.96, r"$|\delta| \leq \alpha$", fontsize=11, color="#3b1e63")
text(6.3, 3.70, "消融四档 0.05 / 0.10 / 0.20 / 0.50", fontsize=9.5, color="#3b1e63")

text(6.3, 3.22, "③ 电量安全门控 $g$", fontsize=11, weight="bold", color=EPURPLE)
text(6.3, 2.92, "SOC 越上界余量带 或 " + r"$< \mathrm{SOC}_{\min}$", fontsize=10, color="#3b1e63")
text(6.3, 2.66, "该栋该步断路，$\\delta \\!=\\! 0$", fontsize=9.5, color="#3b1e63")
text(6.3, 2.30, "（防提前放空 / 过度充电）", fontsize=9, color="#5b3a8a")

# ----- 右：a_final -----
LORG = "#ffe4b3"; EORG = "#c4640d"
box(8.6, 3.20, 4.0, 2.65, LORG, EORG, lw=1.8)
text(10.6, 5.48, "最终动作", fontsize=13, weight="bold", color=EORG)
text(10.6, 5.10, r"$a_{\mathrm{final}}$", fontsize=19, weight="bold", color=EORG)
text(10.6, 4.62, r"$[\,\mathrm{ELE}\,] \times N$", fontsize=11, color="#5b3500")
text(10.6, 4.28, "（仅电池充放电）", fontsize=10, color="#5b3500")
text(10.6, 3.95, "其余两维逐位等于 $a_{\\mathrm{base}}$", fontsize=9.5, color="#5b3500")
text(10.6, 3.58, "送 CityLearn 环境执行", fontsize=10, color="#5b3500")

# ----- 连线 -----
arrow(4.0, 4.70, 4.48, 4.55, color=EBLUE, lw=1.8)
arrow(4.0, 2.45, 4.48, 3.15, color=EGREEN, lw=1.8)
arrow(8.1, 4.30, 8.58, 4.30, color=EPURPLE, lw=1.8)

# ----- 底部说明（独占底部带，不再与绿框重叠）-----
NOTE_TOP = 1.02
ax.text(0.4, NOTE_TOP,
        "· 严格对应正文式 (2-6)："
        r"$\delta=\alpha\cdot s\cdot(m\odot a_{\mathrm{RL}})\cdot g$，"
        r"$a_{\mathrm{final}}=\mathrm{clip}(a_{\mathrm{base}}+\delta)$；"
        r"$s$ 取 $1.0$、$|a_{\mathrm{RL}}|\leq 1$、$m,g\in\{0,1\}$，故 $|\delta|\leq\alpha$。",
        fontsize=8.8, color="#333", ha="left", va="top")
ax.text(0.4, NOTE_TOP - 0.30,
        "· 残差只在第 5 阶段介入，不改任何基线规则参数；$\\alpha$ 与掩码 $m$ 均可在评估任务里配置，无需重新训练。",
        fontsize=8.8, color="#333", ha="left", va="top")
ax.text(0.4, NOTE_TOP - 0.58,
        "· 纯基线入口关闭残差，$a_{\\mathrm{final}} = a_{\\mathrm{base}}$，用于对照实验。",
        fontsize=8.8, color="#333", ha="left", va="top")

# 输出
out_pdf = r"D:\citylearn-demo\thesis\images\pictures\残差合成图.pdf"
out_png = r"D:\citylearn-demo\thesis\images\pictures\残差合成图.png"
plt.savefig(out_pdf, bbox_inches="tight", facecolor="white", pad_inches=0.10)
plt.savefig(out_png, dpi=240, bbox_inches="tight", facecolor="white", pad_inches=0.10)
plt.close(fig)
print("SAVED:", out_pdf)
print("SAVED:", out_png)
