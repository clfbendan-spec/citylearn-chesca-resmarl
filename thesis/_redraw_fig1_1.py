"""重画 thesis/images/pictures/核心难题与改进方案.png

v2: 文字精简、显式 \\n 换行、字号 9.5、行高拉宽，
避免 v1 中文字被框边界截断。
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams["font.sans-serif"] = ["SimHei", "SimSun", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

# 画布
W, H = 13.0, 13.0
fig, ax = plt.subplots(figsize=(W, H), dpi=120)
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("white")


def box(x, y, w, h, fill, edge, lw=1.6, radius=0.12, alpha=0.55):
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


# ----- 顶部标题（蓝） -----
box(0.4, 11.95, W - 0.8, 0.85, "#e3edfb", "#1f4e9c", lw=2.0)
text(W / 2, 12.37, "基于多智能体强化学习的建筑群节能控制",
     fontsize=18, weight="bold", color="#1f4e9c")

# ----- 副标题条 -----
box(0.4, 11.00, W - 0.8, 0.55, "#f3f7fc", "#1f4e9c", lw=1.2)
text(W / 2, 11.27, "四个核心难题      →      两类互补改进方案",
     fontsize=14, weight="bold", color="#1f4e9c")

# ----- 左侧四个难题（4 行） -----
LX = 0.4
LW = 5.4
ROW_H = 1.55
GAP = 0.10
# 顶 y：副标题条底 = 11.00，留 0.45 间距 → 难题一顶 = 10.45
# LY1 = 难题一底（y坐标），实际 LY1 是底
LY1 = 10.45 - ROW_H  # = 8.90
LY2 = LY1 - ROW_H - GAP
LY3 = LY2 - ROW_H - GAP
LY4 = LY3 - ROW_H - GAP

problems = [
    (LY1, "#ffd6b3", "#d96f33", "核心难题一",
     "分层先验基线自适应能力受限：\n"
     "参数相对静态，缺乏连续分级调节；\n"
     "生活热水储罐状态更新未闭环，\n"
     "热水储热移峰通道闲置冻结。"),
    (LY2, "#fff3b0", "#e0a800", "核心难题二",
     "纯多智能体区域协同削峰受限：\n"
     "单楼局部观测，无法感知社区总负荷；\n"
     "易在高价时段套利耗电，\n"
     "晚间真正尖峰时无电可放。"),
    (LY3, "#ffd1dc", "#d96b95", "核心难题三",
     "实验复现与真实经济性缺失：\n"
     "PYTHONHASHSEED 随机化致轨迹分岔；\n"
     "历史最低峰值挑选放大偏差；\n"
     "忽略电池折旧与两部制需量电价。"),
    (LY4, "#e6d7ff", "#8a4cb4", "核心难题四",
     "算法实验与工程平台脱节、\n"
     "决策过程不透明：参数、训练进度、\n"
     "指标、逐时动作四散无统一管理，\n"
     "运维难以信任采纳。"),
]
for y, fill, edge, title, body in problems:
    box(LX, y, LW, ROW_H, fill, edge, lw=1.6)
    text(LX + LW / 2, y + ROW_H - 0.22, title,
         fontsize=12.5, weight="bold", color=edge)
    ax.text(LX + LW / 2, y + ROW_H / 2 - 0.18, body,
            fontsize=9.5, color="#222", ha="center", va="center")

# ----- 右侧两个方案（各覆盖两难题） -----
RX = 6.85
RW = 5.75
# 方案一：覆盖难题一+难题二
SOL1_TOP = LY1 + ROW_H
SOL1_BOTTOM = LY2
SOL1_H = SOL1_TOP - SOL1_BOTTOM
# 方案二：覆盖难题三+难题四
SOL2_TOP = LY3 + ROW_H
SOL2_BOTTOM = LY4
SOL2_H = SOL2_TOP - SOL2_BOTTOM

box(RX, SOL1_BOTTOM, RW, SOL1_H, "#c8efd9", "#2c8f5a", lw=1.8)
text(RX + RW / 2, SOL1_TOP - 0.30,
     "改进方案一：先验引导残差混合控制（回应难题一、二）",
     fontsize=12.5, weight="bold", color="#2c8f5a")
s1_body = (
    "1) 修复分层先验控制器内部生活热水储罐状态更新闭环，\n"
    "    释放热水储热移峰通道；\n"
    "2) 引入基于当步不可调负荷脉冲比的连续分级软门控\n"
    "   （下限 m=5、上限 m=6），越尖锐越深挖电池调节；\n"
    "3) 各建筑智能体输出受限残差修正量，动作通道屏蔽掩码\n"
    "    + 幅度上限约束 + 低电量门控构成三层安全包络，\n"
    "    确保热舒适越界代价为零。"
)
ax.text(RX + RW / 2, SOL1_BOTTOM + SOL1_H / 2 - 0.15, s1_body,
        fontsize=9.5, color="#1d4d33", ha="center", va="center")

box(RX, SOL2_BOTTOM, RW, SOL2_H, "#c8e9f7", "#2c7a9c", lw=1.8)
text(RX + RW / 2, SOL2_TOP - 0.30,
     "改进方案二：端到端区域协同 MARL + 可视化管理平台（回应难题二、三、四）",
     fontsize=12.5, weight="bold", color="#2c7a9c")
s2_body = (
    "1) 非侵入式环境包装器注入 9 维区域协同特征\n"
    "   （社区净负荷比例 + 本楼相对电量排名），不动仿真器源码；\n"
    "2) 正向购电责任分摊 + 历史峰值锚定奖励，强制协同大于自利；\n"
    "3) 大容量经验回放（20 万）+ 多步回报引导，\n"
    "   配合 PYTHONHASHSEED=0 锁定哈希种子 + 末段多检查点均值\n"
    "   抑制训练分岔与评估波动；\n"
    "4) 两部制电价（电度 + 最大需量）+ 锂电池循环折旧核算；\n"
    "5) 基于 Vue + Spring Boot + MySQL + Python 异步进程池\n"
    "    的可视化管理平台贯通数据/任务/KPI/白盒轨迹全流程。"
)
ax.text(RX + RW / 2, SOL2_BOTTOM + SOL2_H / 2 - 0.25, s2_body,
        fontsize=9.5, color="#1d3d52", ha="center", va="center")

# ----- 中间连线 -----
arrow(LX + LW + 0.05, LY1 + ROW_H * 0.7,
      RX - 0.05, SOL1_BOTTOM + SOL1_H * 0.82,
      color="#2c8f5a")
arrow(LX + LW + 0.05, LY2 + ROW_H * 0.7,
      RX - 0.05, SOL1_BOTTOM + SOL1_H * 0.42,
      color="#2c8f5a")
# 难题二 → 方案二（细）
arrow(LX + LW + 0.05, LY2 + ROW_H * 0.30,
      RX - 0.05, SOL2_TOP - 0.55,
      color="#2c7a9c", lw=1.0)
arrow(LX + LW + 0.05, LY3 + ROW_H * 0.7,
      RX - 0.05, SOL2_TOP - 1.6,
      color="#2c7a9c")
arrow(LX + LW + 0.05, LY4 + ROW_H * 0.7,
      RX - 0.05, SOL2_TOP - 2.5,
      color="#2c7a9c")

# ----- 底部紫色总体目标 -----
GB_TOP = 1.65
GB_BOTTOM = 0.55
GB_LEFT = 0.4
GB_RIGHT = W - 0.4
box(GB_LEFT, GB_BOTTOM, GB_RIGHT - GB_LEFT, GB_TOP - GB_BOTTOM,
    "#dcc6ff", "#6a3eb4", lw=2.0)
text((GB_LEFT + GB_RIGHT) / 2, GB_TOP - 0.35,
     "总体目标：CHESCA-ResMARL 混合控制 + 可视化管理平台",
     fontsize=14, weight="bold", color="#4d2480")
text((GB_LEFT + GB_RIGHT) / 2, GB_BOTTOM + 0.30,
     "规则共主（保安全底线） + MARL 可学习增补（求协同上限） + "
     "可视化平台（贯工程闭环）",
     fontsize=11.0, color="#3b1e63")

# 输出
out_path = r"D:\citylearn-demo\thesis\images\pictures\核心难题与改进方案.png"
plt.savefig(out_path, dpi=240, bbox_inches="tight", facecolor="white",
            pad_inches=0.15)
plt.close(fig)
print("SAVED:", out_path)