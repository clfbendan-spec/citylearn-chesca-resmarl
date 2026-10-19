# CityLearn 建筑群节能控制平台

> 基于多智能体强化学习（MARL）的建筑群节能控制策略及其可视化管理平台
>
> 配套学位论文：《基于多智能体强化学习的建筑群节能控制策略及可视化研发》

本项目将 **可解释、强约束的规则基线（CHESCA）** 与 **轻量残差多智能体强化学习（CHESCA-ResMARL）** 结合，
并配套一套贯通「数据 — 训练 — 评估 — 解释」的可视化管理平台，解决建筑群控制中
"基线稳健但自适应不足、纯学习方法难安全落地、实验难管理／决策难理解／成果难复用" 三类问题。

---

## 一、核心思路

本项目的工作分两条线，对应论文中"不同工程先验条件该用哪种控制方法"的判据：

- **A 线（有规则先验的社区）**：以 CHESCA 规则为骨架，在其上叠加**轻量残差强化学习**（CHESCA-ResMARL）。
  规则承担绝大部分收益与全部安全约束，学习只负责有限的增补，因此样本需求低、可逐位退化回基线。
- **B 线（没有可信规则先验的社区）**：不引入任何规则，直接做**端到端多智能体削峰**（District-MARL，
  逐栋 SAC，以社区级归一化峰值比为目标）。这条线用来量化"纯学习方法与规则先验之间还差多远"，
  是论文中"范式差距"结论的实证来源。

A 线（残差叠加）的分层结构：

| 层次 | 做法 | 作用 |
|------|------|------|
| 第 1 层：安全基线 | 固化 CHESCA 链路（预测集成 + DHW 规则 + ELE 电池树搜索 + TMP-PID） | 输出安全、可解释的基准动作 `a_base`，硬约束（SOC / 罐温 / 动作空间）内嵌 |
| 第 2 层：残差学习 | 逐栋 SAC 智能体输出残差动作 `a_rl ∈ [-1, 1]`，按 `a_final = clip(a_base + α·(m ⊙ a_rl)·g)` 叠加到基线 | 只在基线之上学习"有限修正"，单步改动幅度上界为 α，样本需求低、可安全落地 |
| 退化保证 | `α = 0`、掩码 `m` 全关或门控 `g = 0` 时严格退化为纯 CHESCA | 可直接作为对照基线，支持消融实验 |
| 支撑平台 | Vue 前端 + Spring Boot 后端 + MySQL + Python 算法组件的四层 B/S 架构 | 任务调度、配置快照、KPI 对比、决策过程完整可追溯 |

> 符号说明：`a_base` 为规则基线动作，`a_rl` 为智能体输出的残差动作，`α` 为残差幅度系数，
> `m ⊙` 为逐动作维度的掩码（0/1），`g` 为安全门控（0/1）。三者串联构成「掩码 → 幅度 → 门控」三层防护。


---

## 二、系统架构

```
浏览器层        解析 HTML/CSS/JS · 图表交互 · 轮询任务状态
    │
前端 Web 服务层  Vue 2 + Element UI 单页应用 · ECharts 绘图 · 路由与响应封装
    │  HTTP 短请求（查询 / 提交 / 轮询）
后端应用层      Spring Boot RESTful：鉴权 / 查询 / 任务提交 / 状态跟踪 · 线程池异步调度
    │  任务目录文件交换（每个任务一个目录，按 taskId 隔离）
数据存储层      MySQL：业务数据与 KPI 聚合 ｜ 明细 CSV/JSON 落盘（数据库仅存索引）
    │
算法组件层      Python 独立进程运行 CityLearn 仿真：CHESCA / CHESCA-ResMARL 入口
```

要点：**HTTP 只承载短请求**，长耗时仿真走异步队列 + 前端轮询；仿真配置与结果经任务目录交换，
后端与算法模块解耦；全流程以 **任务 ID（taskId）** 为主键，配置快照、仿真输出、KPI 与轨迹文件均可回溯。

---

## 三、目录结构

```
citylearn-demo/
├── citylearnjava/            后端：Spring Boot + MyBatis-Plus + MySQL（端口 8088）
│   ├── src/main/java/        Controller / Service / Dao / Entity
│   ├── src/main/resources/   application.yml、MyBatis mapper XML、数据库脚本
│   ├── citylearn.sql         数据库结构与初始化脚本
│   └── pom.xml
├── citylearnvue/             前端：Vue 2 + Element UI + ECharts + Monaco Editor
│   ├── src/                  页面、组件、路由、状态、样式
│   ├── vue.config.js         devServer 代理：/api → http://localhost:8088
│   └── package.json
├── citylearnpy/              Python 算法组件：CityLearn 仿真与强化学习
│   ├── NOCONTROL.py                  无控制参考值入口
│   ├── CHESCA.py / *.detailed.py     CHESCA 基线入口
│   ├── CHESCA_ResMARL.py             残差叠加策略入口
│   ├── Multi-agent-train.py          MARL 训练入口
│   ├── Multi-agent-eval.py           MARL 评估入口
│   ├── Multi-agent.py                MARL 主流程
│   ├── Single-agent.py / DISAC.py / CentralizedRBC.py / Decentralized*.py   对照算法
│   ├── train_chesca_resmarl.py       残差策略训练脚本
│   ├── local_evaluation.py / ablation_resmarl.py / action_safety_projection.py
│   ├── district_marl/                纯 MARL 削峰线（端到端 SAC，无规则先验）
│   │   ├── district_train.py         训练入口（DRL 环境 + 可复现指纹 + 学习健康埋点）
│   │   ├── district_eval.py          评估入口
│   │   ├── district_acceptance.py    验收判据（mean_last3，缺省回退 best_score）
│   │   ├── district_env.py / district_reward.py / district_features.py
│   │   ├── _hashseed.py              进程哈希种子护栏（锁定 PYTHONHASHSEED）
│   │   └── _fingerprint.py           环境/依赖/git/源码摘要指纹
│   ├── agents/ rewards/ utils/ configs/ scripts/ tests/   模块化源码
│   ├── rla_config.yaml               运行与算法参数配置
│   ├── KPI_Explanation.md / DECISIONS.md / MAINTENANCE.md   算法与决策说明
│   └── CHESCA-copy/ CHESCA-main/     上游 CHESCA 参考实现（第三方，见第九节）
├── thesis/                   学位论文（XeLaTeX + Biber，北京科技大学模板）
│   ├── main.tex              主文件（封面信息、章节引入）
│   ├── contents/             摘要 + 六章正文 + 致谢 + 简历 + 数据集
│   ├── images/pictures/      架构图、流程图、界面截图、结果图
│   ├── scripts/              论文插图生成脚本（matplotlib）
│   ├── myrefs.bib            参考文献库
│   └── README.md             论文工程编译说明
```

> **clean 版范围**：本仓库只发布上图中的 `citylearnjava/`、`citylearnpy/`、`citylearnvue/`、
> `thesis/` 四个目录及其源码。运行期产物（`output/`、`outkpis/`、`rla_logs/`、`uploads/`、
> `checkpoints/` 等）、一次性实验脚本、章节备份目录、本地工作文档与第三方参考组件均**不在仓库内**。
>
> `clearml-*`、`citylearn-ui-main`、`gs参考-毕业论文的latex版本…` 为第三方组件或参考资料，
> 详见「九、第三方组件与许可」。

---

## 四、技术栈

| 分层 | 技术 |
|------|------|
| 前端 | Vue 2.6、Element UI 2.15、ECharts 6、Monaco Editor、axios、papaparse、Sass、Vue CLI 5 |
| 后端 | Spring Boot 2.6.13、MyBatis-Plus 3.5.15、MySQL 8、HikariCP、Knife4j(OpenAPI)、Fastjson、p6spy、Lombok |
| 算法 | Python、CityLearn、Gymnasium、Ray RLlib、PyTorch、Stable-Baselines3、XGBoost、pandas / NumPy / matplotlib |
| 论文 | XeLaTeX、Biber、GB/T 7714-2015 参考文献样式 |

---

## 五、功能模块

1. **系统管理**：用户 / 角色 / 权限（菜单可见性按权限控制）、通知与反馈。
2. **数据管理**：社区、建筑、设备与时序数据；数据集版本与兼容性校验；CSV 导入导出。
3. **算法与实验管理**：算法脚本登记、结构化参数配置（含在线代码编辑器）、任务提交与异步调度、
   状态轮询、日志查看、流水线任务（训练 → 评估）串联、结果归档。
4. **可视化分析**：
   - KPI 对比（柱状图 / 雷达图：成本、碳排、峰值、爬坡、舒适度权衡）
   - 时序曲线（负荷、电价、SOC、室温）
   - 决策过程回放（基线动作 / 残差 / 掩码 / 门控逐步回放，用于定位残差是否被安全层裁剪）

---

## 六、快速开始

### 6.1 环境要求

- JDK 8+（`pom.xml` 编译级别为 14）
- Maven 3.6+
- Node.js 16+ / npm
- Python 3.8+（建议 3.9–3.11）
- MySQL 8.0
- TeX Live 或 MiKTeX（编译论文时需要，含 XeLaTeX / Biber / 中文字体）

### 6.2 数据库

```sql
CREATE DATABASE citylearn DEFAULT CHARACTER SET utf8mb4;
```

1. 导入 `citylearnjava/citylearn.sql`（表结构）；
2. 按需执行 `citylearnjava/src/main/resources/db/*.sql`（增量迁移与基础数据，如权限、算法参数、数据集登记）。

### 6.3 后端（端口 8088）

修改 `citylearnjava/src/main/resources/application.yml` 中的数据源与路径配置：

```yaml
spring:
  datasource:
    url: jdbc:mysql://127.0.0.1:3306/citylearn?characterEncoding=utf8&useSSL=false
    username: root
    password: "******"
citylearn:
  file:
    image-base-path: <你的路径>/uploads/images
    out-file-path:   <你的路径>/output
    python-file-path: <你的路径>/citylearnpy
```

启动：

```bash
cd citylearnjava
mvn spring-boot:run
```

接口文档（Knife4j）：`http://localhost:8088/doc.html`

> ⚠️ 仓库中的 `application.yml` 含示例数据库口令，**请改为自己的配置或使用环境变量**，不要提交真实口令。

### 6.4 前端

```bash
cd citylearnvue
npm install
npm run serve     # 默认 http://localhost:8080，/api 代理到 http://localhost:8088
npm run build     # 产物输出到 dist/
```

### 6.5 Python 算法组件

```bash
cd citylearnpy
# 依赖（版本取自论文实验实际运行环境）
python -m pip install -r requirements.txt

# 平台侧：由后端任务调度自动调用（每个任务一个目录，配置与结果经文件交换）
# 本地调试：
python NOCONTROL.py            # 无控制参考值
python CHESCA.py               # 纯 CHESCA 基线
python CHESCA_ResMARL.py       # 残差叠加策略（α > 0）
python Multi-agent-train.py    # MARL 离线训练，产出 checkpoint
python Multi-agent-eval.py     # 评估（加载 checkpoint，仅前向推理）

# B 线：端到端纯 MARL 削峰（无需规则先验）
python district_marl/district_train.py --train-schema citylearn_challenge_2023_phase_2_local_evaluation \
       --train-epochs 100 --seed 3 --output-dir ../outkpis/_run_s3
python district_marl/district_eval.py  --help
```

参数统一在 `rla_config.yaml` 中配置；算法细节见 `citylearnpy/KPI_Explanation.md`、`DECISIONS.md`、`MAINTENANCE.md`。

> 两个入口在启动时会自动锁定 `PYTHONHASHSEED=0`（`district_marl/_hashseed.py`）。若你在同一进程内
> 循环多次训练，请显式传 `--hashseed random` 退出该护栏，否则每轮结果会逐位相同（这是特性而非缺陷）。

### 6.5b 决策推演日志（模型优选界面）

`district_marl/district_eval.py` **默认**额外落一份 `decision_trace.json`，结构与 CHESCA / Multi-agent
**完全同构**（`version: 2` + `slim`）。「模型优选」页面选中该评估任务后，就能像看 CHESCA 一样
用滑块逐步回放每一步的观测、动作、电池 SOC 与区域奖励，无需任何前端或后端改动。
**训练任务**的收尾评估同样默认落这份文件（`source: train_final_eval`）。

`decision_trace.json` 记录的是**全部动作**，不是摘要：

- `buildings[i].actions.final` = `{dhw, ele, tmp}` 三维**实际执行值**（含方案 3 的削峰改写）；
  旧版只写后两维、DHW 恒 `0.0`，界面上那一列是平线，现在填真实值；
- `buildings[i].actions.raw` = 策略**原始输出**（未改写），与 `final` 对照即可看出被改了多少；
- `buildings[i].dhw_soc` = DHW 蓄热 SOC（旧版恒 `null`）；
- `district.exec_actions` / `district.raw_actions` = 按 agent 汇总的三维执行值 / 原始值。

| 参数 | 默认 | 说明 |
|------|------|------|
| 记录开关 | **开** | 只有显式传 `--no-decision-log` 才不记录（训练入口同名参数同理） |
| `--decision-log-stride` | `1`（逐步全记） | `0` = 按「总步数 ÷ 条数上限」自动抽稀；`12` ≈ 每小时一条 |
| `--decision-log-max-steps` | `0`（不限） | 条数上限。`0` 时 `truncated` 恒为 `false`，整段全记 |

每步的 `phases` 是区域版三段：**区域观测与峰值目标 → 逐栋策略动作 → 区域奖励与分摊**；
`district` 块另带 `community_net_kw` / `is_peak_step` / `ratio_vs_segment_peak` /
`action_dims`（纯展示，**不参与任何 KPI 或选点**）。峰步标记是整段跑完后统一补的 ——
跑到第 10 步时还不知道全段峰值，逐步判断会把前期局部高点误标成峰步。

> 体积参照：local 720 步 × 3 栋全量 ≈ **5 MB**；online 整季（2–3 千步 × 6–9 栋）会到
> **几十 MB**，与仓库里既有的 Multi-agent `decision_trace.json`（40–161 MB）同一量级。
> 嫌大就显式抽稀（`--decision-log-stride 12`）或用 `python slim_decision_trace.py --all` 瘦身。

### 6.6 编译论文

```bash
cd thesis
latexmk -xelatex main.tex
# 或手动：xelatex main.tex → biber main → xelatex main.tex → xelatex main.tex
```

> 注意：**不要**使用 `latexmk -pdf`（会误选 pdflatex，导致 xeCJK 报
> `The xeCJK package requires XeTeX to function`）。详见 `thesis/README.md`。

---

## 七、算法与实验流程

**A 线（CHESCA-ResMARL，规则先验 + 残差学习）**

```
NOCONTROL（无控制，作 KPI 分母）
   → 纯 CHESCA（基线链路验证）
   → CHESCA-ResMARL α=0（退化正确性验证，须与基线逐位一致）
   → 参数消融与方案演进（残差幅度 α / 动作维度掩码 / 各改进方案，每组 3 个随机种子）
   → KPI 归一化（均为 控制组 / 无控制组 比值）
        └── 判定：Δ/σ 比值与 2σ 阈值；失败分支查决策过程「基线 / 残差 / 门控」三列定位
```

**B 线（District-MARL，端到端纯 MARL）**

```
NOCONTROL（作归一化分母，全季 max 定为 1.0）
   → 逐栋 SAC 训练（奖励 = 按贡献分摊 + 峰值目标锚定，动作 3 维）
   → 每 20 轮在完整季上评估，记录归一化峰值比
   → 验收判据 acceptance = mean_last3（训练末期 3 个检查点均值，抑制"选最小噪声"的偏差）
        └── 参考口径 best_score[0]（历史 best epoch，仅用于曲线/断点分析，不作结论依据）
```

全局约定：

- 评价指标：总成本、碳排放、全时段峰值比、爬坡、热舒适越界率、总用电量、可再生消纳、零净能耗。
  其中「峰值比」为全时段峰值比（控制组峰值 / 无控制组峰值）；绝对峰值（kW）不可与峰值比互换。
- 结果以 **无控制结果为分母归一化**，保证跨场景可比；仿真周期不同的批次（如 720 步与 2208 步）
  不可直接比较累计量。舒适度类指标是绝对量（越界百分点），**不可与比值相加**。
- **复现性**：只固定随机种子并**不足以保证**结果可复现 —— 实测同一配置、同一种子重复 4 次，
  验收指标极差达 0.0894，原因是 Python 进程哈希种子会改变字典/集合遍历顺序，进而改变策略网络的
  初始化与采样顺序。因此训练与评估入口均默认锁定 `PYTHONHASHSEED=0`（`district_marl/_hashseed.py`），
  锁定后重复运行可逐位一致。
- **训练进程留痕**：`district_summary.json` 同时写入 `fingerprint`（环境/依赖/git/源码摘要哈希）、
  `train_health`（学习是否真正激活、回放池填充比、NaN 轮次）、`perf`（训练/评估/保存耗时分段），
  用于排查"结果不对"时先分清是环境问题、训练没学动，还是指标口径问题。

---

## 八、数据与结果说明

- `output/`、`outkpis/`、`rla_logs/`、`uploads/`、`citylearnpy/checkpoints/`、`citylearnpy/outputs/`、
  `citylearnpy/ablation_results/` 等均为运行期产物或体积较大的中间结果，已在 `.gitignore` 中排除，不入库。
- CityLearn 的场景 / 数据集以 `*.pth` / `*.pkl` 形式存放（如 `CHESCA-*/data/schemas/`），属于运行必需数据，
  因此 **未** 做 `*.pth` / `*.pkl` 的全局忽略；仅按目录排除了体积较大的 `citylearnpy/datasets/`。
- 若历史提交中已经包含了上述运行产物目录（如 `citylearnpy/outputs/`、`citylearnpy/checkpoints/`、
  `__pycache__/`），可用 `git rm -r --cached <目录>` 停止跟踪（不会删除本地文件）。
- 平台所需的评测数据集（CityLearn 社区级多建筑数据集及兼容数据集）请在本地 `citylearnpy/datasets/` 下准备，
  并在平台的"数据集登记"中维护 schema 与版本信息。
- 论文中的图表：架构图与流程图由 `thesis/scripts/*.py` 生成，
  界面截图取自平台实际运行界面，存放于 `thesis/images/pictures/`。

---

## 九、第三方组件与许可

本仓库包含以下第三方内容，版权归原作者所有，请遵守其各自许可：

| 目录 | 说明 |
|------|------|
| `citylearnpy/CHESCA-copy/`、`citylearnpy/CHESCA-main/` | CHESCA 参考实现（论文基线来源） |
| `citylearn-ui-main/` | Light Bootstrap Dashboard React（前端模板，MIT） |
| `clearml-sdk/`、`clearml-server/`、`clearml-web/` | ClearML 组件源码（实验跟踪方案备选） |
| `gs参考-毕业论文的latex版本_集成参考文献和说明-2/` | 学位论文 LaTeX 参考模板 |

> 若仓库公开发布，建议按需移除或改为 submodule 引用上述第三方目录，避免许可与体积问题。

---

## 十、结论可信度与已知边界

本项目全文贯彻「先证伪、再宣称」的口径，以下边界随代码一并如实说明：

- **指标口径**：所有 KPI 均为「控制组 / 无控制组」的比值，舒适度类指标为绝对量，两者不可相加；
  `local`（720 步）与 `online`（2208 步）两个 schema 的累计量不可横向比较。
- **效应量与显著性**：District-MARL 侧 39 组训练（27 组旧批 + 12 组预注册）显示，奖励端微调的
  效应量（≤0.04）低于最小可检测效应（0.0254），**未能在统计上确证**；预注册复核的判定为
  「未复现」（n=6，p=0.203），也未推翻原结论。相关报告与原始读数保留在数据集台账中。
- **机制层**：单种子审计曾观察到"尖峰豁免步充电下降"等现象，多种子复核后消失，属训练噪声；
  唯一稳健的机制观测是"全天 SOC 抬升"与"峰值位置稳定"。
- **已关闭方向**：奖励端继续微调、跨域异构域正样本、峰值轴 4% 削减目标等方向已判定为低收益，
  不再继续投入，代码中相关开关默认关闭。
- 本项目为科研 / 学位论文用途，未做生产级安全加固（如鉴权强度、密钥管理、并发压测等）。

---

## 十一、主要参考

- CityLearn: https://github.com/intelligent-environments-lab/CityLearn
- Gymnasium: https://gymnasium.farama.org/
- Ray RLlib: https://docs.ray.io/en/latest/rllib/
- CHESCA（The CityLearn Challenge 基线）: https://github.com/intelligent-environments-lab/CityLearn-Challenge
- Stable-Baselines3: https://stable-baselines3.readthedocs.io/
- XGBoost: https://xgboost.readthedocs.io/
- Home Assistant 前端主题（UI 设计参考）: https://github.com/home-assistant/frontend
