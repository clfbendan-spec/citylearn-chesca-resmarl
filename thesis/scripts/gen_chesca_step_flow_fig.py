# -*- coding: utf-8 -*-
"""生成论文用图：CHESCA 单步决策流程（每个仿真时间步）。

内容依据代码实测（行号取自实际被加载的 CHESCA-copy/checa/）：
  · 入口循环        CHESCA.detailed.py:468（env.step → agent.predict 五阶段）
  · ① 预测          checa/forecast_agent/forecasting_agent.py:147
  · ② 动作初稿      checa/agent.py:405（正常 542-613 / 停电 476-540）
                    冷机 PID      checa/cooling_device_controller/cooling_device_controller.py:231
  · ③ 未来用电      checa/agent.py:641 / 666
  · ④ 电池 refine   checa/agent.py:1075（min_soc 916 / 树搜索 battery_controller.py:126 /
                    电价 981 / 复电限流 813 / 阈值 1125-1182 / 最终裁剪 1217）
  · ⑤ 残差修正      checa/agent.py:351（纯 CHESCA 恒等；ResMARL 按 α 混合）
  · 动作维度        checa/agent.py:49-55 / 616 → [DHW, ELE, TMP] × 建筑数
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(r"d:\citylearn-demo\thesis\images\pictures")
OUT.mkdir(parents=True, exist_ok=True)
PNG = OUT / "CHESCA单步流程图.png"
PDF = OUT / "CHESCA单步流程图.pdf"

C_ENV = ("#f8fafc", "#94a3b8")
C_PRED = ("#fff7ed", "#ea580c")
C_RULE = ("#eff6ff", "#2563eb")
C_BATT = ("#ecfdf5", "#059669")
C_RES = ("#f5f3ff", "#7c3aed")
C_IO = ("#fefce8", "#ca8a04")
GREY = "#6b7280"
INK = "#1f2937"

fig, ax = plt.subplots(figsize=(14.6, 10.6), dpi=220)
ax.set_xlim(0, 146)
ax.set_ylim(0, 102)
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
            ha=ha, va=va, linespacing=1.45)


def arrow(x1, y1, x2, y2, color="#4b5563", lw=1.6, dashed=False):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=13,
                                linestyle="--" if dashed else "-"))


# ------------------------------------------------------------------ 标题
box(12, 94.6, 122, 5.6, ("#eef6ff", "#2563eb"), lw=1.9)
text(73, 97.4, "CHESCA 单步决策流程（每个仿真时间步）", size=15.0, weight="bold", color="#1e3a8a")

# ------------------------------------------------------------------ 图例
legend = [(14, C_ENV, "环境 / 输入输出"), (15, C_PRED, "① 预测"), (19, C_RULE, "②③ 规则动作"),
          (16, C_BATT, "④ 电池优化"), (15, C_RES, "⑤ 残差修正")]
lx = 21.0
for w, colors, name in legend:
    box(lx, 89.6, w, 3.2, colors, lw=1.2, radius=0.3)
    text(lx + w / 2, 91.2, name, size=8.8, color=colors[1], weight="bold")
    lx += w + 3.0

# ------------------------------------------------------------------ 左列：单步主链
LX, LW = 7.0, 64.0
MAIN = [
    (81.5, 5.6, C_ENV, "环境执行：env.step(a_t) → 取回观测 o(t+1)"),
    (73.4, 6.2, C_PRED, "① 预测 ForecastAgent.compute_forecast(o)\n电价 / 负荷 / 温度多模型集成"),
    (63.2, 7.6, C_RULE, "② 动作初稿 initial_actions()（逐栋生成候选动作）\n非停电：冷机 PID + DHW 规则；停电：保冷 + 优先储热"),
    (56.0, 5.6, C_RULE, "③ 未来用电需求：未来制冷 / 热水负荷估计"),
    (44.6, 9.4, C_BATT, "④ 电池 refine refine_actions_with_battery_controller()\nmin_soc 下界 → 树搜索 → 电价感知 → 复电限流\n→ B_high / B_low 阈值增减负荷 → 动作裁剪"),
    (36.4, 6.4, C_RES, "⑤ 残差修正 apply_residual_correction()\na=(1-α)·a_base+α·a_rl（纯 CHESCA：α=0，恒等）"),
    (28.2, 6.4, C_IO, "输出动作 a_t = [DHW, ELE, TMP] × N 栋 → 交环境执行\ntrace 落盘 + 奖励与 KPI 计算"),
]
for y, h, colors, main in MAIN:
    box(LX, y, LW, h, colors, lw=1.6)
    text(LX + LW / 2, y + h / 2, main, size=9.5)

for i in range(len(MAIN) - 1):
    y_top = MAIN[i][0]
    y_bottom = MAIN[i + 1][0] + MAIN[i + 1][1]
    arrow(LX + LW / 2, y_top, LX + LW / 2, y_bottom + 0.3)

# 左列底部说明
text(LX, 24.0, "• 动作空间：每栋 3 维 [DHW, ELE, TMP]（热水储热 / 电池充放 / 冷机开度），按栋顺序拼接",
     size=8.8, color="#334155", ha="left")
text(LX, 20.6, "• ①–⑤ 在同一个仿真步内按序执行；纯 CHESCA 时 α=0，⑤ 为恒等映射",
     size=8.8, color="#334155", ha="left")
text(LX, 17.2, "• 停电 / 非停电由环境 outage 信号逐栋给出；树搜索与电价策略只作用于非停电工况",
     size=8.8, color="#334155", ha="left")

# ------------------------------------------------------------------ 右列上：② 细节
RX, RW = 77.0, 62.0
box(RX, 57.2, RW, 29.8, ("#ffffff", "#2563eb"), lw=1.7, radius=0.5)
text(RX + RW / 2, 84.4, "② 动作初稿内部：正常 / 停电 两分支 + 冷机子流程", size=10.4,
     weight="bold", color="#1e40af")

box(RX + 2.0, 69.2, 28.0, 13.6, ("#eff6ff", "#2563eb"), lw=1.4)
text(RX + 16.0, 80.6, "非停电（每栋）", size=9.4, weight="bold", color="#1d4ed8")
text(RX + 16.0, 75.0,
     "冷机 PID：CASE1 输出\n→ 可用电量上限截断 → 过热保底\n→ 室外开环保底 → 冷负荷前馈\n→ min_cool 保底 → clip[0,1]\n→ 复电 TMP 帽 / 斜坡",
     size=8.0, color="#374151")

box(RX + 32.0, 69.2, 28.0, 13.6, ("#eff6ff", "#2563eb"), lw=1.4)
text(RX + 46.0, 80.6, "停电（每栋）", size=9.4, weight="bold", color="#1d4ed8")
text(RX + 46.0, 75.4,
     "冷机保冷（CASE2 / CASE3）\n→ DHW 优先储热\n→ 光伏 / 电池三档平衡\n→ 三通道动作裁剪",
     size=8.0, color="#374151")

text(RX + RW / 2, 66.6, "DHW 规则：按热需求与储热状态判定是否加热；ELE 初稿固定 0，留给阶段 ④",
     size=8.6, color="#334155")
text(RX + RW / 2, 62.0, "两个分支最终都裁剪到动作空间上下限，输出基准动作 a_base",
     size=8.4, color="#334155")

# ------------------------------------------------------------------ 右列下：④ 细节
box(RX, 7.6, RW, 46.0, ("#ffffff", "#059669"), lw=1.7, radius=0.5)
text(RX + RW / 2, 50.6, "④ 电池 refine 内部顺序（仅非停电栋）", size=10.4,
     weight="bold", color="#065f46")

STEPS = [
    ("①", "min_soc 逐小时下界构造", "复电豁免 / 韧性地板 / 低价时段补电增强"),
    ("②", "电池树搜索", "把 min_soc 与容量·DoD 硬约束带入转移模型，搜索最优充放"),
    ("③", "电价感知调整", "高价禁充 → 高 SOC 强制放电 → 低价补电 → 全局地板裁剪"),
    ("④", "复电充电帽 + 过热禁充", "复电窗口内限制充电幅度；过热时禁止充电"),
    ("⑤", "B_high 阈值", "净负荷 > 均值 + B_high×σ → 削减 DHW / 降低 TMP 开度"),
    ("⑥", "B_low 阈值", "净负荷 < 均值 - B_low×σ → 增加 DHW 加热以消纳低价电"),
    ("⑦", "最终动作裁剪", "三通道 clip 到动作空间上下限，得到基准动作 a_base"),
]
y = 46.0
for tag, name, detail in STEPS:
    box(RX + 2.6, y - 1.35, 2.6, 2.7, ("#d1fae5", "#059669"), lw=1.0, radius=0.25)
    text(RX + 3.9, y, tag, size=8.6, weight="bold", color="#047857")
    text(RX + 6.4, y, f"{name}：{detail}", size=8.4, color="#374151", ha="left")
    y -= 5.3

text(RX + RW / 2, 10.6, "①→⑦ 按序施加；min_soc / 容量 / DoD 等硬约束在 ② 电池树搜索内生效",
     size=8.4, color="#334155")

# 连线：左列 ② / ④ → 右侧细节
arrow(LX + LW, 67.0, RX - 0.8, 72.0, color="#2563eb", lw=1.5, dashed=True)
arrow(LX + LW, 49.3, RX - 0.8, 44.0, color="#059669", lw=1.5, dashed=True)

fig.savefig(PNG, bbox_inches="tight", facecolor="white", edgecolor="none")
fig.savefig(PDF, bbox_inches="tight", facecolor="white", edgecolor="none")
print(f"saved: {PNG}  ({PNG.stat().st_size} bytes)")
print(f"saved: {PDF}  ({PDF.stat().st_size} bytes)")
