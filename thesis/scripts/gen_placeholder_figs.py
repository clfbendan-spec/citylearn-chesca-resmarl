# -*- coding: utf-8 -*-
"""把论文里「文字占位」的图换成正式插图（与另两张图同一套风格）。

一次运行生成全部图；每张图的内容取自论文对应 \\begin{verbatim} 占位块的原文：
  · CHESCA三动作技术架构   chap2.tex:133-140
  · 功能模块图             chap3.tex:23-25
  · 系统架构图             chap3.tex:60-62（覆盖同名占位图片，先备份）
  · 数据库ER图             chap3.tex:95-97 + 3.4 节文字（覆盖同名占位图片，先备份）
  · 日志流水线图           chap4.tex:52-54
  · 任务调度图             chap4.tex:176-178
  · 残差合成图             chap4.tex:194-198
  · 算法实验流程图         chap5.tex:92-94
"""

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(r"d:\citylearn-demo\thesis\images\pictures")
OUT.mkdir(parents=True, exist_ok=True)

BLUE = ("#eff6ff", "#2563eb")
GREEN = ("#ecfdf5", "#059669")
VIOLET = ("#f5f3ff", "#7c3aed")
AMBER = ("#fff7ed", "#ea580c")
SLATE = ("#f8fafc", "#64748b")
YELLOW = ("#fefce8", "#ca8a04")
PINK = ("#fdf2f8", "#db2777")
WHITE = ("#ffffff", "#94a3b8")
INK = "#1f2937"
GREY = "#6b7280"


def new_canvas(w=13.6, h=8.4, xmax=136, ymax=84):
    fig, ax = plt.subplots(figsize=(w, h), dpi=220)
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    return fig, ax


def box(ax, x, y, w, h, colors, lw=1.5, radius=0.45, dashed=False):
    face, edge = colors
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0.02,rounding_size={radius}",
        linewidth=lw, facecolor=face, edgecolor=edge,
        linestyle="--" if dashed else "-"))


def text(ax, x, y, s, size=10.0, weight="normal", color=INK, ha="center", va="center"):
    ax.text(x, y, s, fontsize=size, fontweight=weight, color=color,
            ha=ha, va=va, linespacing=1.45)


def arrow(ax, x1, y1, x2, y2, color="#4b5563", lw=1.7, dashed=False):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=14,
                                linestyle="--" if dashed else "-"))


def save(fig, name):
    png = OUT / f"{name}.png"
    if png.is_file() and png.stat().st_size < 40000:      # 旧的小图 = 占位图，先备份
        bak = OUT / f"{name}_占位图备份.png"
        if not bak.is_file():
            shutil.copy2(png, bak)
            print(f"  占位图已备份: {bak.name}")
    path = png
    fig.savefig(path, bbox_inches="tight", facecolor="white", edgecolor="none")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"saved: {name}.png ({path.stat().st_size} bytes)")


# ======================================================= 1. CHESCA 三动作技术架构
def fig_three_actions():
    fig, ax = new_canvas(w=13.6, h=8.6, xmax=136, ymax=86)

    box(ax, 8, 78.0, 120, 6.0, BLUE, lw=1.9)
    text(ax, 68, 81.0, "CHESCA 三动作技术架构（仅加残差，不改主链路）", size=14.5,
         weight="bold", color="#1e3a8a")

    # 预测层
    box(ax, 30, 66.6, 76, 9.8, AMBER, lw=1.7)
    text(ax, 68, 73.6, "ForecastAgent　时序预测（集成）", size=11.2, weight="bold", color="#9a3412")
    text(ax, 68, 70.4, "XGBoost 离线预训练　+　XGBoost 在线微调　+　同时段历史均值",
         size=9.2, color="#7c2d12")
    text(ax, 68, 67.6, "预测未来 τ 步：室外温度 · 光伏出力 · 不可调负荷 · 热水需求",
         size=9.0, color="#7c2d12")

    # 三动作通道
    CH = [
        (10, "动作一　DHW 生活热水", "需求规则 + 储罐约束\n低谷多储热 · 高峰少加热\n罐温上下限硬裁剪\n（最稳定，掩码默认小 α）"),
        (53, "动作二　ELE 电气储能", "电池树搜索（A* 最小代价）\n离散 SOC · 贴历史均值 · 电价规则\nSOC / min_soc 小时表硬约束\n（峰值与爬坡竞争力的来源）"),
        (96, "动作三　TMP 冷机", "PID 跟踪室温设定值\n积分 / 微分 + 室外温度缩放\n停电切换独立增益 Kp_outage\n辅助 PID 只做前馈估计"),
    ]
    for x, title, body in CH:
        box(ax, x, 40.5, 30, 19.5, GREEN if "ELE" in title else BLUE, lw=1.6)
        text(ax, x + 15, 57.0, title, size=10.6, weight="bold", color="#1e40af")
        text(ax, x + 15, 49.0, body, size=8.6, color="#374151")

    # 预测 → 三动作通道：先一条横向总线，再三条下行箭头（原来缺横向连线）
    arrow(ax, 68, 66.4, 68, 63.8, color="#ea580c", lw=1.8)
    ax.plot([25, 111], [63.8, 63.8], color="#ea580c", lw=1.6)
    for x in (25, 68, 111):
        arrow(ax, x, 63.8, x, 60.4, color="#ea580c", lw=1.5)

    # 社区协调
    box(ax, 26, 30.5, 84, 7.2, VIOLET, lw=1.7)
    text(ax, 68, 35.6, "社区协调：联动削减 / 增加 + 安全裁剪（SOC · 罐温 · 动作空间）",
         size=10.6, weight="bold", color="#5b21b6")
    text(ax, 68, 32.6, "三路动作在此汇合，得到基准动作 a_base", size=9.0, color="#4c1d95")
    for x in (25, 68, 111):
        arrow(ax, x, 40.3, x, 38.1, color="#059669", lw=1.5)

    box(ax, 44, 21.0, 48, 4.6, ("#dbeafe", "#2563eb"), lw=1.6, radius=0.35)
    text(ax, 68, 23.3, "a_base = [DHW, ELE, TMP] × N 栋", size=10.4, weight="bold", color="#1e3a8a")
    arrow(ax, 68, 30.3, 68, 25.9, color="#7c3aed", lw=1.8)

    box(ax, 26, 11.0, 84, 7.0, ("#f1f5f9", "#7c3aed"), lw=1.7, dashed=True)
    text(ax, 68, 16.2, "阶段 5　ResMARL 残差合成", size=10.8, weight="bold", color="#5b21b6")
    text(ax, 68, 13.0, "a_final = clip( (1-α)·a_base + α·mask(a_rl) )　　（α=0 → 恒等，退化为纯 CHESCA）",
         size=9.2, color="#4c1d95")
    arrow(ax, 68, 20.8, 68, 18.3, color="#7c3aed", lw=1.8, dashed=True)

    text(ax, 8, 5.6, "· 三路动作各自独立生成，社区协调负责联动与裁剪；偏差由硬约束兜底，因此基线动作安全、可解释",
         size=9.0, color="#334155", ha="left")
    text(ax, 8, 2.2, "· 残差只在阶段 5 介入，掩码按通道设计（DHW / ELE / TMP 可分别关闭），不改动任何规则参数",
         size=9.0, color="#334155", ha="left")
    save(fig, "CHESCA三动作技术架构")


# ======================================================= 2. 功能模块图
def fig_modules():
    fig, ax = new_canvas(w=13.6, h=7.6, xmax=136, ymax=76)

    box(ax, 8, 68.0, 120, 6.0, BLUE, lw=1.9)
    text(ax, 68, 71.0, "系统功能模块划分", size=14.5, weight="bold", color="#1e3a8a")

    MODS = [
        (10, "系统管理", "用户 / 角色 / 权限 / 通知\n菜单可见性按权限控制\n（反馈管理列为后续工作）", VIOLET),
        (41, "数据管理", "社区 / 建筑 / 设备\n数据集 schema 与版本\n兼容校验 + CSV 导出复核", GREEN),
        (72, "算法与实验管理", "算法登记 · 参数配置 · 任务提交\n状态跟踪 · 结果归档\n流水线任务串联训练与评估", BLUE),
        (103, "可视化分析", "KPI 对比（柱状 / 雷达）\n时序曲线（负荷/电价/SOC/室温）\n决策轨迹（基线/残差/掩码/投影）", AMBER),
    ]
    for x, title, body, colors in MODS:
        box(ax, x, 38.0, 27, 24.0, colors, lw=1.7)
        text(ax, x + 13.5, 58.0, title, size=11.6, weight="bold", color=colors[1])
        text(ax, x + 13.5, 47.0, body, size=8.8, color="#374151")

    box(ax, 14, 26.0, 108, 7.6, ("#f1f5f9", "#64748b"), lw=1.8)
    text(ax, 68, 31.4, "统一以任务 id 串起「配置 — 运行 — 结果」全链路", size=11.6,
         weight="bold", color="#334155")
    text(ax, 68, 28.4, "配置快照 · 仿真输出 · KPI 入库 · 决策轨迹 均可按同一任务 ID 回溯",
         size=9.2, color="#475569")
    for x in (23.5, 54.5, 85.5, 116.5):
        arrow(ax, x, 37.8, x, 34.0, color="#64748b", lw=1.5)

    text(ax, 14, 20.0, "· 四个模块共享同一套权限体系与任务 ID 规范；算法以独立脚本 + 键值配置接入，新增策略无需改后端",
         size=9.0, color="#334155", ha="left")
    text(ax, 14, 16.6, "· 长耗时仿真由后端线程池异步调度，前端轮询任务状态，避免 HTTP 超时",
         size=9.0, color="#334155", ha="left")
    text(ax, 14, 13.2, "· 日志按任务 ID 隔离归档，解析失败保留原始行并标注原因，保证可追溯",
         size=9.0, color="#334155", ha="left")
    save(fig, "功能模块图")


# ======================================================= 3. 系统架构图
def fig_architecture():
    fig, ax = new_canvas(w=13.6, h=9.0, xmax=136, ymax=90)

    box(ax, 8, 82.0, 120, 6.0, BLUE, lw=1.9)
    text(ax, 68, 85.0, "系统架构（B/S 四层 + Python 算法组件）", size=14.5,
         weight="bold", color="#1e3a8a")

    LAYERS = [
        (64.0, "浏览器层", "解析 HTML/CSS/JS · 页面渲染与交互 · 图表交互 · 轮询任务状态", SLATE),
        (52.0, "前端 Web 服务层", "Vue + Element UI 单页应用 · ECharts 绘图 · 路由与响应封装 · 安全与缓存", BLUE),
        (40.0, "后端应用层", "Spring Boot RESTful：鉴权 / 查询 / 任务提交 / 状态跟踪 · 线程池异步调度", GREEN),
        (28.0, "数据存储层", "MySQL：业务数据与 KPI 聚合 · 明细 CSV/JSON 按任务 id 落盘（数据库仅存索引）", VIOLET),
    ]
    for y, title, body, colors in LAYERS:
        box(ax, 8, y, 84, 9.0, colors, lw=1.7)
        text(ax, 50, y + 5.9, title, size=11.0, weight="bold", color=colors[1])
        text(ax, 50, y + 2.7, body, size=8.5, color="#374151")
    for y in (64.0, 52.0, 40.0):
        arrow(ax, 50, y, 50, y - 1.9, color="#64748b", lw=1.6)

    box(ax, 96, 39.0, 32, 22.0, YELLOW, lw=1.7)
    text(ax, 112, 57.4, "Python 算法组件", size=10.6, weight="bold", color="#854d0e")
    text(ax, 112, 49.6, "CityLearn 仿真（独立进程）\nCHESCA / CHESCA-ResMARL 入口\n接收任务、写回结果\n经任务目录文件交换，与后端解耦",
         size=8.4, color="#7c2d12")
    text(ax, 112, 42.4, "长任务异步执行　短请求同步返回", size=8.2, color="#9a3412")
    arrow(ax, 92.6, 47.0, 95.4, 47.0, color="#ca8a04", lw=1.6, dashed=True)
    arrow(ax, 95.4, 43.0, 92.6, 43.0, color="#ca8a04", lw=1.6, dashed=True)

    text(ax, 8, 22.4, "· HTTP 只承载短请求（查询 / 提交 / 轮询）；仿真走异步队列 + 轮询，避免请求超时",
         size=9.0, color="#334155", ha="left")
    text(ax, 8, 18.8, "· 仿真所需配置与结果数据经任务目录交换（每个任务一个目录），实现后端与算法模块解耦",
         size=9.0, color="#334155", ha="left")
    text(ax, 8, 15.2, "· 结果文件按任务 id 隔离，数据库只保存索引，兼顾查询效率与原始数据可追溯性",
         size=9.0, color="#334155", ha="left")
    save(fig, "系统架构图")


# ======================================================= 4. 数据库 E-R 图
def fig_er():
    fig, ax = new_canvas(w=13.6, h=8.6, xmax=136, ymax=86)

    box(ax, 8, 78.0, 120, 6.0, BLUE, lw=1.9)
    text(ax, 68, 81.0, "数据库关系（E-R 概念图）", size=14.5, weight="bold", color="#1e3a8a")

    box(ax, 10, 58.0, 30, 10.0, GREEN, lw=1.7)
    text(ax, 25, 64.6, "py_file", size=11.4, weight="bold", color="#065f46")
    text(ax, 25, 60.6, "算法脚本登记\n（train / eval / both）", size=8.4, color="#374151")

    box(ax, 52, 58.0, 32, 10.0, BLUE, lw=1.7)
    text(ax, 68, 64.6, "py_task", size=11.4, weight="bold", color="#1e40af")
    text(ax, 68, 60.6, "任务状态 / 展示名 / 配置快照\n（子任务带 -train / -eval 后缀）", size=8.4, color="#374151")

    box(ax, 96, 58.0, 30, 10.0, VIOLET, lw=1.7)
    text(ax, 111, 64.6, "kpis", size=11.4, weight="bold", color="#5b21b6")
    text(ax, 111, 60.6, "按名称 + 类型聚合\n（District / 建筑级）", size=8.4, color="#374151")

    arrow(ax, 40, 63.0, 51.6, 63.0, color="#4b5563", lw=1.6)
    text(ax, 46, 65.8, "1 : N", size=8.6, color="#4b5563")
    arrow(ax, 84, 63.0, 95.6, 63.0, color="#4b5563", lw=1.6)
    text(ax, 90, 65.8, "1 : N", size=8.6, color="#4b5563")

    box(ax, 52, 43.6, 32, 8.6, YELLOW, lw=1.6)
    text(ax, 68, 49.2, "结果文件目录（按任务 id）", size=9.6, weight="bold", color="#854d0e")
    text(ax, 68, 46.0, "KPI 记录 · 决策轨迹 · 逐步明细", size=8.3, color="#7c2d12")
    arrow(ax, 68, 57.8, 68, 52.6, color="#ca8a04", lw=1.6)

    box(ax, 10, 43.6, 30, 8.6, GREEN, lw=1.6)
    text(ax, 25, 49.2, "citylearn_dataset", size=9.8, weight="bold", color="#065f46")
    text(ax, 25, 46.0, "schema_key 唯一 · 建筑数 · 步数", size=8.2, color="#374151")
    arrow(ax, 25, 52.4, 25, 57.8, color="#059669", lw=1.6)
    text(ax, 27.4, 55.0, "1 : N", size=8.4, color="#059669", ha="left")

    box(ax, 10, 29.4, 116, 9.4, PINK, lw=1.6)
    text(ax, 68, 35.8, "algorithm_config（键值表）", size=11.0, weight="bold", color="#9d174d")
    text(ax, 68, 32.6, "min_soc_per_hour · residual_alpha · residual_action_mask · resmarl_after_safety · train / eval_schema",
         size=8.3, color="#831843")

    text(ax, 8, 24.0, "· 脚本与任务为 1:N；任务与 KPI / 结果文件为 1:N；数据集与任务为 1:N", size=9.0,
         color="#334155", ha="left")
    text(ax, 8, 20.0, "· 数据库仅保存索引与聚合结果，原始明细保留在任务目录文件中，便于离线复核", size=9.0,
         color="#334155", ha="left")
    text(ax, 8, 16.0, "· 外键约束较少，一致性由服务层保证：提交前校验存在性，完成后以事务写入并更新状态", size=9.0,
         color="#334155", ha="left")
    save(fig, "数据库ER图")


# ======================================================= 5. 日志流水线图
def fig_log_pipeline():
    fig, ax = new_canvas(w=14.0, h=7.4, xmax=146, ymax=74)

    box(ax, 8, 66.0, 124, 6.0, BLUE, lw=1.9)
    text(ax, 70, 69.0, "日志流水线（当前方案 + 后续扩展）", size=14.2, weight="bold", color="#1e3a8a")

    STEPS = [
        (9, "Python stdout", "标准输出重定向\n到任务目录", SLATE),
        (36, "正则解析", "提取配置 / 奖励 / KPI\n失败保留原始行 + 原因", AMBER),
        (63, "CSV / JSON 落盘", "字段名与数据库一致\n时间步连续编号", YELLOW),
        (90, "MySQL 事务入库", "聚合写入 kpis 表\n明细保留在文件", VIOLET),
        (117, "前端按任务 id 查", "任务列表 / 分析页\nstdout 与错误日志", BLUE),
    ]
    for x, title, body, colors in STEPS:
        box(ax, x, 42.0, 24, 14.0, colors, lw=1.6)
        text(ax, x + 12, 52.6, title, size=10.2, weight="bold", color=colors[1])
        text(ax, x + 12, 46.6, body, size=8.4, color="#374151")
    for x in (33, 60, 87, 114):
        arrow(ax, x, 49.0, x + 2.6, 49.0, color="#4b5563", lw=1.6)

    box(ax, 9, 22.0, 132, 14.0, ("#f8fafc", "#94a3b8"), lw=1.5, dashed=True)
    text(ax, 75, 33.0, "后续扩展（当前未部署）：集中式日志检索", size=10.6, weight="bold", color="#475569")
    text(ax, 75, 28.4, "Filebeat 采集 → Elasticsearch / Loki 存储 → Kibana / Grafana 检索",
         size=9.4, color="#475569")
    text(ax, 75, 24.6, "按任务 id / 算法类型 / 数据集打标签，可查单任务全链路日志；字段规范已固化，接入无需返工",
         size=8.3, color=GREY)

    text(ax, 8, 16.4, "· 解析失败不静默丢弃：保留原始行并标注原因；并发任务异步写入，互不阻塞", size=9.0,
         color="#334155", ha="left")
    save(fig, "日志流水线图")


# ======================================================= 6. 任务调度图
def fig_scheduling():
    fig, ax = new_canvas(w=13.8, h=8.2, xmax=138, ymax=82)

    box(ax, 9, 75.0, 120, 6.0, BLUE, lw=1.9)
    text(ax, 69, 78.0, "任务调度流程（提交 → 异步执行 → 结果归档）", size=14.2,
         weight="bold", color="#1e3a8a")

    ROW1 = [
        (11, "① 前端提交", "表单校验：脚本 / 数据集 /\n参数 / 必填项", SLATE),
        (56, "② 生成任务 id 并写快照", "Spring Boot 生成任务 ID\n写入配置快照（可回溯）", BLUE),
        (101, "③ 线程池异步调度", "长任务不阻塞 HTTP\n前端轮询任务状态", GREEN),
    ]
    for x, title, body, colors in ROW1:
        box(ax, x, 57.0, 26, 12.0, colors, lw=1.6)
        text(ax, x + 13, 65.2, title, size=10.0, weight="bold", color=colors[1])
        text(ax, x + 13, 60.4, body, size=8.3, color="#374151")
    arrow(ax, 37.4, 63.0, 55.6, 63.0, color="#4b5563", lw=1.6)
    arrow(ax, 82.4, 63.0, 100.6, 63.0, color="#4b5563", lw=1.6)
    arrow(ax, 114, 56.8, 114, 47.4, color="#4b5563", lw=1.6)

    ROW2 = [
        (11, "⑥ 前端展示", "KPI 对比 / 时序曲线\n决策轨迹 · 标准输出与 stderr", BLUE),
        (56, "⑤ 解析入库", "KPI 事务写入 kpis 表\n任务状态更新为已完成", VIOLET),
        (101, "④ Python 仿真", "CHESCA / CHESCA-ResMARL\n结果写入本任务目录", YELLOW),
    ]
    for x, title, body, colors in ROW2:
        box(ax, x, 35.4, 26, 12.0, colors, lw=1.6)
        text(ax, x + 13, 43.6, title, size=10.0, weight="bold", color=colors[1])
        text(ax, x + 13, 38.8, body, size=8.3, color="#374151")
    arrow(ax, 100.4, 41.4, 82.6, 41.4, color="#4b5563", lw=1.6)
    arrow(ax, 55.6, 41.4, 37.4, 41.4, color="#4b5563", lw=1.6)

    box(ax, 11, 21.0, 116, 10.0, ("#fef2f2", "#dc2626"), lw=1.6, dashed=True)
    text(ax, 69, 28.0, "失败分支", size=10.4, weight="bold", color="#b91c1c")
    text(ax, 69, 24.2, "脚本异常 / 解析失败 → 任务标为失败并保留 stderr 与日志路径，前端展示错误原因，不静默丢弃",
         size=8.6, color="#991b1b")

    text(ax, 11, 15.6, "· 编排任务：一次提交可串联「训练子任务 → 评估子任务」，评估可复用历史成功训练任务的模型（只跑评估）",
         size=9.0, color="#334155", ha="left")
    text(ax, 11, 12.0, "· 全流程以任务 id 为主键：配置快照、仿真输出、KPI 与轨迹文件均可按同一 ID 回溯",
         size=9.0, color="#334155", ha="left")
    save(fig, "任务调度图")


def fig_residual_fusion():
    fig, ax = new_canvas(w=13.8, h=7.6, xmax=138, ymax=76)
    box(ax, 9, 69.0, 120, 6.0, VIOLET, lw=1.9)
    text(ax, 69, 72.0, "残差合成：a_final = clip( (1-α)·a_base + α·mask(a_rl) )", size=13.6,
         weight="bold", color="#5b21b6")

    box(ax, 10, 46.0, 42, 15.0, BLUE, lw=1.7)
    text(ax, 31, 58.0, "基线动作 a_base", size=11.0, weight="bold", color="#1e40af")
    text(ax, 31, 51.6, "DHW 规则　|　ELE 电池树搜索　|　TMP-PID\n（含 SOC / 罐温 / 动作空间硬约束）",
         size=8.5, color="#374151")

    box(ax, 10, 24.0, 42, 15.0, GREEN, lw=1.7)
    text(ax, 31, 36.0, "各建筑独立 SAC 策略", size=11.0, weight="bold", color="#065f46")
    text(ax, 31, 29.6, "离线训练（RLlib）· 本地观测 o_b\n输出绝对动作 a_rl = [DHW, ELE, TMP] × N",
         size=8.5, color="#374151")

    box(ax, 60, 35.0, 28, 26.0, ("#faf5ff", "#7c3aed"), lw=1.8)
    text(ax, 74, 57.0, "融合", size=12.0, weight="bold", color="#5b21b6")
    text(ax, 74, 49.6, "掩码 m\nDHW / ELE / TMP\n逐通道开关", size=9.0, color="#4c1d95")
    text(ax, 74, 40.4, "强度 α\nα=0 → 恒等\n退化为纯 CHESCA", size=9.0, color="#4c1d95")

    box(ax, 96, 41.0, 32, 14.0, YELLOW, lw=1.7)
    text(ax, 112, 51.4, "安全投影 + 裁剪", size=10.4, weight="bold", color="#854d0e")
    text(ax, 112, 45.6, "clip 到动作空间上下限\n基线硬约束始终成立", size=8.4, color="#7c2d12")

    box(ax, 96, 22.0, 32, 12.0, ("#ede9fe", "#7c3aed"), lw=1.7)
    text(ax, 112, 30.4, "a_final", size=13.0, weight="bold", color="#4c1d95")
    text(ax, 112, 25.6, "[DHW, ELE, TMP] × N\n交 CityLearn 环境执行", size=8.6, color="#4c1d95")

    arrow(ax, 52.4, 53.5, 59.4, 51.0, color="#2563eb", lw=1.7)
    arrow(ax, 52.4, 31.5, 59.4, 40.0, color="#059669", lw=1.7)
    arrow(ax, 88.6, 48.0, 95.4, 48.0, color="#7c3aed", lw=1.7)
    arrow(ax, 112, 40.8, 112, 34.4, color="#7c3aed", lw=1.7)

    text(ax, 10, 17.6, "· 掩码关闭的通道保持 a_base 原值（不学习）；ELE 残差生效时会同步重算电池预测电耗",
         size=9.0, color="#334155", ha="left")
    text(ax, 10, 14.0, "· 残差只在阶段 5 介入，不改动任何基线规则参数；α 与掩码均可在评估任务里配置，无需重新训练",
         size=9.0, color="#334155", ha="left")
    text(ax, 10, 10.4, "· 纯基线入口关闭该阶段，a_final = a_base，用于对照实验", size=9.0,
         color="#334155", ha="left")
    save(fig, "残差合成图")


def fig_experiment_pipeline():
    fig, ax = new_canvas(w=14.0, h=7.2, xmax=146, ymax=72)
    box(ax, 8, 65.0, 130, 6.0, BLUE, lw=1.9)
    text(ax, 73, 68.0, "算法实验流程（从参考值到显著性检验）", size=14.2, weight="bold", color="#1e3a8a")

    STEPS = [
        (8, "NOCONTROL", "无控制参考值\n作为 KPI 分母", SLATE),
        (36, "纯 CHESCA", "基线链路验证", BLUE),
        (64, "ResMARL α=0", "退化正确性验证\n须与基线完全一致", GREEN),
        (92, "α × 掩码 × 安全开关", "每组 ≥5 个随机种子\n均值 / 标准差 / 置信区间", VIOLET),
        (120, "KPI 归一化 + 检验", "成本 / 碳排 / 峰值 / 不适\n配对显著性检验", AMBER),
    ]
    for x, title, body, colors in STEPS:
        box(ax, x, 42.0, 24, 14.0, colors, lw=1.6)
        text(ax, x + 12, 52.2, title, size=9.8, weight="bold", color=colors[1])
        text(ax, x + 12, 46.6, body, size=8.3, color="#374151")
    for x in (32, 60, 88, 116):
        arrow(ax, x, 49.0, x + 3.6, 49.0, color="#4b5563", lw=1.6)

    box(ax, 8, 25.0, 136, 11.0, ("#fef2f2", "#dc2626"), lw=1.6, dashed=True)
    text(ax, 76, 32.6, "失败分支：舒适越界 / 峰值恶化", size=10.4, weight="bold", color="#b91c1c")
    text(ax, 76, 28.4, "查决策轨迹三列定位来源 —— 基线列（规则与约束）· 残差列（SAC 输出）· 投影列（掩码与裁剪）",
         size=8.6, color="#991b1b")

    text(ax, 8, 19.4, "· 顺序要求：先确认基线与 α=0 退化正确，再开展参数扫描；退化不一致则先修基线，不做后续比较",
         size=9.0, color="#334155", ha="left")
    text(ax, 8, 15.8, "· 固定随机种子即可复现 KPI 与决策轨迹，保证跨场景结果可比", size=9.0,
         color="#334155", ha="left")
    save(fig, "算法实验流程图")


if __name__ == "__main__":
    print("== CHESCA 三动作技术架构 ==")
    fig_three_actions()
    print("== 功能模块图 ==")
    fig_modules()
    print("== 系统架构图 ==")
    fig_architecture()
    print("== 数据库ER图 ==")
    fig_er()
    print("== 日志流水线图 ==")
    fig_log_pipeline()
    print("== 任务调度图 ==")
    fig_scheduling()
    print("== 残差合成图 ==")
    fig_residual_fusion()
    print("== 算法实验流程图 ==")
    fig_experiment_pipeline()
