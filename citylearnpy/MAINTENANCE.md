# 维护约定（改代码前先读这一页）

> 目标：**改参数/逻辑只动一处，改完能自证"没改坏"**。
> 配套文档：历史判决与实测数字全在 [`DECISIONS.md`](DECISIONS.md)（§1–§15）✓

---

## 1. 铁律：手改**只有这几个文件**

| 文件 | 角色 |
|---|---|
| `Multi-agent.py` | **唯一手改入口**（训练+评估一体；含 `CUSTOM_REWARD_KWARGS` 配置）|
| `_gen_marl_split.py` | 生成器（切分标记、eval/train 专属模板段在这里）|
| `custom_comfort_reward.py` | 奖励实现（领域模块，三方 import 同一份）|
| `multi_agent_runner_copy.py` | CHESCA-ResMARL 残差修正（checkpoint 存取已抽到 `utils/train.py` ✓）|
| `utils/` | **通用工具（2026-10-06 合并为 5 个模块 ✓、同日再加 1 个 ⇒ 现 6 个 ✓）**：**`runtime.py`**（日志出口 / Windows `resource` 补丁 / Ray 环境准备 / **子进程 import 预检**）、**`config.py`**（训练规模与判据常量 + 奖励配置与 sidecar）、**`envs.py`**（动作与环境解包 / 上下文环境 / schema 改造 / 建环境 / 探针 / 动作注入）、**`trace.py`**（逐步采集 / 决策推演 / KPI 打印）、**`train_eval.py`**（中期评估 / 无控制成本参照 / checkpoint 的**存 / 取 / 找最新** / **`CkptManager`：训练断点与 best 快照管家** ✓）、**`train_phase.py`**（训练探针与累加器准备 / **训练主循环** / P-4 成本项 / 收尾汇总 / best 快照替换 ✓）—— 每段前都有一条 `段：xxx（原 utils/xxx.py）` 横幅，映射一目了然 ✓ |

**✗ 绝对不要手改这 4 份（生成物）**：`Multi-agent-train.detailed.py`、`Multi-agent-train.py`、
`Multi-agent-eval.detailed.py`、`Multi-agent-eval.py`
—— 它们全是 `_gen_marl_split.py` 从 `Multi-agent.py` 生成的**产物**，**下次生成即被覆盖** ✗✗

> ⚠️ **2026-10-06 起的新风险** ✗：`Multi-agent-eval.py` 的头部已精简成**一行**
> （`# Multi-agent 的评估算法入口` ✓）⇒ **文件里再没有"勿手改 ✗"那句提示了** ✗✗ ——
> **唯一的警示就是本页** ✓。真手改了 ⇒ 跑一次生成器即被静默抹掉 ✗。

> ⚠️ **真实事故（2026-10-06）**：有人在 `Multi-agent-eval.py` 里改了 2 处注释
> （`# 算子不大，设置单线程启动，避免多线程抢锁` ✓、把"Java 会把本脚本复制…"的"Java"删掉 ✓），
> **差点被下一次生成抹掉** ✗ —— 靠"先备份 → 重生成 → 逐行 diff"才抓回来并移植进源文件 ✓。
> 同日他又把 **eval 的注释整体改短并定稿**（含头部 1 行化 ✓）⇒ 为遵守他的"**源文件一个字都不动**"
> 硬要求 ✗，那批措辞**固化在生成器里** ✓ ⇒ 见 §1.1 ✓。

> **要改注释/措辞 ⇒ 对号入座** ✓
> | 改的是哪一类 | 该改哪儿 |
> |---|---|
> | **eval** 的整行注释 / 头部 / eval 专属段（准备段、参数表…）| `_gen_marl_split.py` 的 **`EVAL_WORDING_PATCHES`** 表（§1.1 ✓）或 `*_BLOCK` 常量 ✓ |
> | **train** 的专属段（参数表、准备段…）| `_gen_marl_split.py` 的 `*_BLOCK` 常量 ✓ |
> | **两入口共享**的注释（导入区 brief、主循环 brief…）| `Multi-agent.py` 里那一行 ✓（**简略行** = 详注块**外面**那行 ✓；**详细说明**写进 `# [详注-BEGIN]…[详注-END]` 之间 ✓）|
> | **行尾注释**（`x = y  # 说明`）| **谨慎** ✗：门禁 ⑥ 把**行尾注释也算代码** ✓ ⇒ 只改它会让"源文件 ↔ eval 详注版"判**漂移** ✗（要么连源文件一起改 ✓，要么只在简版改 ✓，见 §1.1 ✓）|
>
> **改完必跑** `python _gen_marl_split.py` ✓ + §2 的校验 ✓。

**eval 出两份**（2026-10-05 起 ✓；2026-10-06 起简版进一步精简 ✓）：
`Multi-agent-eval.detailed.py` = **详注版**（保留 [详注] 块 ✓，读代码 / 写论文用 ✓；与源文件的
共享代码段**逐行同源** ✓，由门禁 ⑥ 守着 ✓）；`Multi-agent-eval.py` = **精简注释版**
（送审交付 + **平台实际跑它** ✓）：= 详注版去掉 [详注] 块 ✓ → 换 **1 行头部**
（`# Multi-agent 的评估算法入口` ✓；模块 docstring 一并删掉 ✓）→ 打上 §1.1 的**措辞固化表** ✓ →
**删掉 2 行"只伺候外部诊断脚本"的兼容别名** ✓ → **裁掉所有未被引用的导入（现 87 个 ✓）**
→ 连续空行压到 1 行（顶层 `def` / `class` 前保留 2 行 ✓ PEP 8 ✓）✓；**平台与端到端冒烟跑它** ✓。
（2026-10-06 导入清理 ✓：源文件里 **12 个**"文件内未用 + 全仓库无外部引用"的导入已删 ✓，
eval 详注版另清 **4 个**训练侧专用导入 ✓（`COOL_LOAD_*` ×3 / `action_hook_status` ✓，走 §1.1 表的 **ev 阶段** ✓）；
`preflight_import_module` 则从模块级挪到**用点局部导入** ✓ —— 它原来就在**门禁段②的共享行**上 ✗，
只改 eval 会让门禁 ⑥ `exit 1` ✓（实测过一次 ✓）。判据 = AST「绑定 − 读取」+ 消费方脚本/文档/库模块交叉检索 ✓，
且改完必过：`--help` ×2 逐字节 ✓、模块级 exec 探针 ✓、`--check-reward` ✓、eval 端到端 KPI/TRACE 字节比对 ✓。）
同日另做「**默认值下沉**」✓：`DEFAULT_OUTPUT_DIR` / `DEFAULT_TRAIN_SCHEMA` / `DEFAULT_EVAL_SCHEMA` /
`DEFAULT_CHECKPOINT_DIR` 四个默认值**原先分裂在两处** ✗（前三个写在源文件顶部 ✓、第四个由生成器的
`CHECKPOINT_DIR_BLOCK` **注入**进每个产物 ✓）⇒ 现统一到 `utils/config.py` ✓，三个入口只留一句
`from utils.config import …` ✓；`DEFAULT_CHECKPOINT_DIR` 改为 `Path(CITYLEARNPY_DIR) / CKPT_DIR` ✓
（同一件事不写两遍 ✓，取值与旧写法逐字符相同 ✓ ⇒ `--help` 不变 ✓）。副作用两条 ✓：
① eval 那条合并 import 涨到 ≈176 字符 ⇒ 生成器"同模块 import 合并"的**单行阈值 152 → 200** ✓
（96 → 152 → 200，三次抬升同一原因："最长的那条常见 import"变长了 ✓）；
② eval 侧 `DEFAULT_TRAIN_SCHEMA` 变未用 ⇒ 由 §1.1 表的 ev 补丁删掉 ✓（详注版也干净 ✓）。
同日再抽「**入口启动靴**」✓（先量化过 ✓：两份入口在 `__main__` 之外共 **33 行逐字相同** ✓，
占 eval 侧模块级代码的 **73%** ✓）：新建 `utils/base.py` ✓ —— 把"Ray 的 Windows 补丁 /
torch 单线程 `TORCH_THREADS` / pd 显示选项 / 乱码与警告过滤"这**四件事**收成一份 ✓，
入口只留 `from utils.base import TORCH_THREADS`（导入即生效 ✓）。
**有意留在入口**的是"顺序敏感的最前一段" ✗✗：stdlib → 线程 env 三行 → `sys.path` 引导 →
`utils.base`（env 三行必须早于 numpy/pandas/torch ✓；引导行是"先有鸡还是先有蛋"、删不掉 ✓）。
连带四处 ✓：① 门禁段② 从"线程 env + torch 块"重划为「**顺序敏感段**」（终点锚点 = 启动靴那行 ✓，
基线 15 → **7** ✓，合计 92+7 = **99 行** ✓）；② 门禁**新增顺序守卫** ✓ —— 逐文件断言
`utils.base` 必须出现在 pandas / numpy / torch / ray / citylearn / gymnasium / utils.env…
**之前** ✓（这类错**不报错、只静默变慢** ✗，所以必须机器守 ✓）；③ AST 指纹看守纳入
`utils/base.py` ✓；④ 撤掉两条"给 eval 挪 pd.set_option"的 ev 补丁 ✓（已由启动靴统一 ✓）。
每个入口 ≈ 省 17 行 ✓（train 391→**375** ✓、eval 240→**223** ✓），而 `--help` ×2 逐字节 ✓、
`--check-reward` ✓、端到端 KPI + decision_trace **逐字节不变** ✓。
**同日再按使用者要求撤下「断点续训」** ✗（`--resume` ✓）：源文件删该参数 ✓、生成器 `MARK_CKPT_TRAIN_ARGS`
同步 ✓、`utils/train.py` 里**两份** `run_training` 的续训分支整体摘除 ✓（`_resume` ✓ /
`resolve_ckpt_dir` ✓ / `SAC.from_checkpoint` ✓ / 「中期评估历史回灌」140 行 ✓ ⇒ 模块 2802 → **2357** 行 ✓）；
顺带删掉源文件里已成死码的 `from ray.rllib.algorithms.sac import SAC` ✓（它只为续训而留 ✓），并把
`utils/train.py` **纳入 AST 指纹看守** ✓（摘续训时才发现它没在名单里 ✗ —— 改它不会惊动任何人 ✗）。
验证含**真实训练冒烟** ✓（`--train-epochs 1 --min-train-epochs 1 --no-checkpoint -o <tmp>` ⇒ exit 0 ✓、
日志里再无任何 `[续训]` 行 ✓）；eval 侧 `--help` 与端到端 KPI/TRACE **逐字节不变** ✓。
⚠️ 若平台（Java）仍在传 `--resume` ⇒ argparse 遇未知参数会直接**报错退出** ✗ ⇒ 需平台侧确认不再传 ✓。
**同日再按使用者要求撤下 `--env-runners`（并行采样旋钮）** ✗：它在仓库里**从未真正生效过** ✓
（实测所有运行日志 `env_runners=0（生效值）` ✓；唯一像 >1 的 `a7499f77` 日志里那处是**提示文案** ✓）；
撤下范围 = 源文件（参数 + `NUM_ENV_RUNNERS` 导入 + 取值行 + 预检/降级整块 + 日志子句 + `run_training` 实参 ✓）、
`utils/config.py`（`NUM_ENV_RUNNERS` 常量 ✓）、`utils/train.py`（两处签名 + `.rollouts(num_rollout_workers=0)` ✓）、
生成器（3 处镜像/文档/补丁说明 ✓）、`utils/base.py`（`preflight_import_module` 整函数 ✓ —— 它**唯一**的用户就是它 ✓）。
撤下理由（写在 `utils/env.py` 头部与 train_phase 注释里 ✓）：除"奖励类须是 worker 可 import 的真实模块"外，
还有两条**只在单进程下成立**的依赖 ✗ —— ① Ray worker 不 import 入口脚本 ⇒ **动作注入钩子装不上**
⇒ 奖励的动作项**静默为 0** ✗；② `COOL_FLOOR_SCALE` 等模块级全局传不到 worker ✗。
验证：`--env-runners 2` ⇒ **argparse 报错 exit 2** ✓；真实训练 1 轮 exit 0 且日志无 `[并行采样]` ✓；
eval `--help` 与端到端 KPI/TRACE **逐字节不变** ✓（eval 指纹哈希一字未变 ✓）。
⚠️ 平台若仍在传 `--env-runners` ⇒ 同样会**报错退出** ✗ ⇒ 需平台侧确认 ✓。想恢复并行采样请先解决上面两条依赖 ✓
（旧实现见 `_tmp_bak12/` 与 `_gen_marl_split.py` 的 `EVAL_WORDING_PATCHES` 说明 ✓）。
**同日把训练入口那 50 行「奖励口径 + 动作重标定」横幅抽成函数** ✓：`utils/train_eval.log_reward_banner(log=…)`
（`Multi-agent.py` 那段 `if USE_CUSTOM_REWARD: … else: …` 换成**一行调用** ✓，源 1221 → **1172** 行 ✓、
train 简版 → **254** 行 ✓）。三处关键约束 ✓：① 调用点必须仍在 `log_console(初始化 SAC 多智能体…)`
之后、`训练 schema=…` 之前 ✓（否则日志行序变 ✗）；② 它落在 eval 侧 `EVAL_SETUP_BLOCK` 的整段替换区内 ✓
⇒ **评估入口不调用它** ✓（所以生成器里"eval 删 `action_hook_status`"那条补丁换成"eval 删
`log_reward_banner`" ✓；同时**取消**了生成器第 0 步那句"把 --check-reward 提示改成去源文件跑"的改写 ✓
—— 那句日志现在只由训练入口打印，原文案本就诚实 ✓）；③ 新函数住在 `utils/train.py` ⇒ 该文件
**纳入 AST 指纹看守** ✓（与 `train_phase.py` 同一类缺口 ✓）。验证：横幅渲染文本在 5 组配置下
（load/const、bat=0、SPAN/FLOOR/全关、USE_CUSTOM_REWARD=False）**逐字节一致** ✓；真实训练 1 轮
exit 0 且横幅仍在原位置 ✓；eval `--help` 与端到端 KPI/TRACE **逐字节不变** ✓。）
两份由 `_gen_marl_split.py` **一次生成** ✓，每步变换各带守卫（strip 自带 AST 守卫 ✓；
裁剪器要求"去掉 import 节点后 AST 完全相同"✓；删行器要求"被删名字删后无引用"✓）
⇒ 判"代码改没改"看 **详注版**（+ train）的指纹 ✓ —— 简版指纹会随裁剪变化，不是同源基准 ✓。

**train 也出两份**（2026-10-06 起 ✓，与 eval 同款）：`Multi-agent-train.detailed.py` = **详注版**
（读代码 ✓）；**`Multi-agent-train.py` = 精简注释版**（**平台实际跑它** ✓）= 详注版去掉 [详注] 块
→ 换短头部（1 行横幅 + 4 行文档串 ✓）→ 裁掉未用导入（现 76 个 ✓）→ 空行压平 ✓。
与 eval 简版**有意不同**的一点 ✓：train 简版**不删**那 2 行"只伺候外部诊断脚本"的兼容别名
（train 是平台运行入口，保守优先 ✓）。

**命令行参数的排版约定** ✓（2026-10-06 起 ✓，使用者要求 ✓）：**一律恰好两行** ✓（无 help 的才允许一行 ✓）——
行1 = `parser.add_argument(` + **其余参数** ✓；行2 = `help=…` + `)` ✓，
**多行 help 也压成一行** ✗（只并掉字面量之间的空白/换行 ✓ ⇒ 字符串值不变 ✓；
若 help 里含**真跨行字面量**或注释 ⇒ 改用 `ast.unparse` 重建 ✓）：

```python
    parser.add_argument('--eval-schema', type=str, default=DEFAULT_EVAL_SCHEMA,
                        help=f'评估用数据集：CityLearn 数据目录名（默认 {DEFAULT_EVAL_SCHEMA}）')
```

> ⚠️ 生成器里那 **15 个含 `add_argument` 的常量**（`MARK_*_ARGS` / `MARK_NO_TRACE_ARG` /
> `ANCHOR_*` / `TRAIN_ARG` / `EVAL_ARG` ✓）是**源文本的副本或注入块** ✗ ⇒ 改源文件的参数定义时
> **必须同步它们** ✓，否则生成器会报"标记命中 0 次 / 找不到插入锚点"✗（本次就踩了：源文件改完
> 少了 6 个前缀锚点的同步 ✓）。
> **验收口径** ✓：重排只动空白 ⇒ `--help` 必须**逐字节不变** ✓、各入口 **AST 指纹必须不变** ✓
> （生成器那条会变 ✓ —— 它的块常量是字符串数据 ⇒ 属**有意变化** ✓）。

**train 入口现在是"薄壳"** ✓（2026-10-06 三步抽取 ✓）：训练专属的那一大段（探针准备 + 主循环，
约 1180 行 ✗）整段下沉到 **`utils/train.py::run_training`** ✓，训练存档下沉到
**`utils/train.py::CkptManager`** ✓ ⇒ **`Multi-agent-train.py` 从 1802 行降到 464 行** ✓
（源文件 2844 → 1374 ✓，详注版 → 1014 ✓）。
搬运方式值得记一笔 ✗✓：**段内代码一字未改** ✓ —— `run_training` 的**签名**声明它需要的名字
（关键字参数 ⇒ 同名局部 ✓），跑完把结果打包成 `TrainOutcome` 返回 ✓，调用方再**回灌**成原名 ✓
（段后代码 / 共享评估段 / 生成器注入的 `TRAIN_SAVE_BLOCK` 都直接用原名 ✓）。
抽完用**真跑一轮训练**当冒烟（临时目录、`--no-checkpoint --no-best-ckpt` ✓，不碰现有断点 ✓）
才敢收工 —— 这一步抓到 3 个静态检查看不出的错 ✗（`run_training` 没 import / `except…as exc` 与
推导式变量被误当"段内产出" / 生成器注入块用的 `ckpt_dir` 没回灌 ✓）。**eval 侧全程逐字节未变** ✓
（哈希 + 门禁 ⑥ + 端到端 KPI 三重对齐 ✓）。

### 1.1 eval 的「措辞固化表」（`EVAL_WORDING_PATCHES`）

**是什么** ✓：`_gen_marl_split.py` 里的一张补丁表（2026-10-06 建立 ✓，现 **51 条** ✓），把
"**在 eval 交付件上定稿的注释措辞**"固化下来 ⇒ 每次生成都自动重现 ✓（不必再手改生成物 ✗）。
**为什么要有它** ✗✓：使用者要求"**源文件一个字都不动**" ✗，而 eval 的措辞又是他在生成物上定的
⇒ 只能固化在生成器里 ✓。**代价**：同一句话在源文件与表里各存一份 ✗；
**好处**：train 侧措辞**完全不受影响** ✓（例：`# 日志工具，Windows 兼容` 目前只在 eval 生效 ✓ ——
想三入口统一 ⇒ 改源文件那一行 ✓）。

**怎么运作** ✓

| 阶段（按此顺序执行 ✓）| 作用对象 | 覆盖到什么 |
|---|---|---|
| `_apply_eval_patches(ev, 'ev', …)` | eval **详注版**（简版是它的派生物 ⇒ 两份同时生效 ✓）| 整行注释 ✓、eval 专属段的措辞 ✓（**行尾注释除外** ✗ —— 门禁口径所限，见 §1 表末行 ✓）|
| `_drop_module_docstring(ev_simple, …)` | 简版 | 删掉模块 docstring（头部只留 1 行 ✓）。**用 AST 定位** ✗：不用字符串找三引号 —— 文档串正文里出现这种片段会切错位置 ⇒ 残留未闭合引号、解析立刻失败 ✗（实测撞过 ✓）|
| `_apply_eval_patches(ev_simple, 'simple', …)` | 简版 | "同模块 import 合并 / 裁未用导入"**之后**才存在的行 ✓（含那 4 条**行尾注释** ✓、若干空行 ✓）|

**维护规则** ✓

- 每条补丁都要求"**恰好命中 1 次**" ✓ ⇒ 源文件里对应那行被改动 ⇒ 生成器**直接报错**（绝不静默
  产出半成品 ✗），报错还会打印 **scope / kind / 旧文本片段** ✓ ⇒ 照序号更新表即可 ✓。
- **顺序铁律** ✗✗：同 scope 内 **先删 → 再改 → 最后插**（实测两次撞车：插入先跑 ⇒ 删旧
  `pd.set_option` 命中 2 次 ✗；替换先跑 ⇒ 再删"原有的 `# 构建评估环境`"命中 2 次 ✗）。
- **空行别写死个数** ✗（前一步删行常把 1 个空行叠成 2 个 ⇒ 下次就不匹配 ✗）⇒ 用
  `drop_blank_after|before`（全删 ✓）/ `keep_blank_after|before`（只留 1 个 ✓）。
- 表是**自动配对**出来的 ✓（脚本从"生成器产出 ↔ 定稿文件"的实测差分生成 ✓），**不要手抄** ✗。
- **验收口径** ✓：重新生成后，`Multi-agent-eval.py` 应与定稿文件**逐行一致** ✓（唯一允许的字节差 = 末行换行符 ✓），
  且门禁 ⑥ `--strict` 必须 **exit 0** ✓、端到端 KPI / decision_trace **逐字节同基准** ✓。

```powershell
python _gen_marl_split.py          # 改完源文件必跑：生成 train + eval(详注版) + eval(简版)
```

> 生成器靠 `MARK_*` 标记定位切分点；若报"标记命中 0 次"⇒ 说明你把注释块改成了它认不出的样子 ✗

### ⚠️ 部署注意（`utils/` 的 import 依赖）

Java 会把脚本**复制到 `output/outkpis/<taskId>/` 再执行** ✗ —— 那时脚本目录里**没有** `utils/`，
所以每个入口只留 **1 行**引导（2026-10-06 起 ✓）：把项目目录塞进 `sys.path`
（候选 = 环境变量 `CITYLEARNPY_DIR` → 项目默认路径 ✓；就地运行时脚本自身目录已在 `sys.path[0]` ✓）：

```python
sys.path[:0] = [str(Path(p).resolve()) for p in (os.environ.get('CITYLEARNPY_DIR'), r'D:\citylearn-demo\citylearnpy') if p and Path(p).is_dir()][:1]
```

> 这 1 行**删不掉** ✗✗（必须先于 `from utils.base import …` 执行 —— 先有鸡还是先有蛋）；
> 其余全部在 `utils/base.py`：目录本身 = `CITYLEARNPY_DIR`（由**它自己的** `__file__` 推出 ✓，
> 比入口猜候选更权威 ✓）+ `ensure_on_pythonpath()`（归一化 / sys.path 去重 / PYTHONPATH 写入 ✓，
> **import 本模块即自动挂好** ✓；Ray 子进程另有 `prepare_ray_env()` 再挂一次，幂等 ✓）。

**已实测通过**：把 `Multi-agent-eval.py` 复制到任务目录、设好 `CITYLEARNPY_DIR` 后运行，
KPI 与原地运行**逐字节相同** ✓（2026-10-02；**2026-10-06 改成 1 行引导后重测通过** ✓ ——
带/不带 `CITYLEARNPY_DIR` 两种方式 + 从任务目录真跑一次评估 ✓）

---

## 2. 标准流程（改 → 生成 → 七项校验 → 端到端）

```powershell
python _gen_marl_split.py                    # ① 生成（三个入口行数应同步变化）
python _q_ast_fingerprint.py check           # ② 只改注释的硬证据（AST 哈希不变）
python _q_config_parity.py                   # ③ 三方配置逐字一致（期望 83/83）
python _q_batch2_audit.py                    # ④ 三方常量逐名一致 + 奖励字典完整
python -m py_compile Multi-agent.py Multi-agent-train.py Multi-agent-eval.py Multi-agent-eval.detailed.py   # ⑤
python _q_eval_seg_diff.py                   # ⑥ 共享代码段逐行一致（比对目标 = **详注版** eval ✓；不一致 ⇒ exit 1 ✗；段长偏基线 ⇒ 告警）
python _q_eval_seg_diff.py --strict           # ⑥′ 同上，但段长偏基线也计为失败（CI 用）
python Multi-agent.py --check-reward         # ⑦ 奖励公式与原版逐位一致（期望 0.000e+00）
```

**⑧ 端到端冒烟**（约 20 s；改过源文件/奖励/评估段时必跑）：

```powershell
$p='d:/citylearn-demo/output/outkpis/_smoke'
python Multi-agent-eval.py -o $p --eval-schema citylearn_challenge_2023_phase_2_local_evaluation `
  --checkpoint "d:/citylearn-demo/output/outkpis/<任务id>/checkpoints/multi_agent_resume_best" --no-trace
(Get-FileHash "$p/exported_kpis.csv").Hash.Substring(0,16)   # 与上一版比对，应逐字节相同
```

> 当前基准：**`AF7DD1BAE85631E6`**（720 步 schema + 上述 best checkpoint）。
> 它只在"代码/模型不变"时恒定 —— 一旦改了奖励或映射，基准应当变化 ✓（那时重取即可）

---

## 3. 校验工具各能证明什么

| 工具 | 证明 | 不能证明 |
|---|---|---|
| `_q_ast_fingerprint.py` `save`/`check` | **代码+docstring 逐字未动**（注释不进 AST）| 值是否合理 |
| `_q_config_parity.py` | 三个入口的**模块级常量 + 奖励字典**逐字一致 | 是否只改了注释 |
| `_q_stale_api.py` | 诊断脚本里 `ma.<名字>` / `mod.<名字>` 是否**真的存在** ✓（重构后"脚本还在、其实早坏了"✗ 的探针；实测抓到过 `REWARD_KWARGS`、`SymmetricComfortReward`、`_project_hot_cool_actions` 等旧名 ✓）；有旧伤 **exit 1** ✓ | 只查**静态写死**的属性名 ✗（`getattr(ma, 变量)` 看不出 ✓）；`--list` 会列出"解析不出目标路径"的**盲区脚本** ✓；不判"名字在但语义变了"✗ |
| `_q_batch2_audit.py` | 常量**逐名**比对（缺失/额外/值差）+ 字典键完整 | — |
| `_q_ccr_signature.py` `save`/`check` | `CustomComfortReward` **签名（形参名+默认值）**未动 | 方法体是否改 |
| `_q_eval_seg_diff.py` | **详注版 eval** 与源文件的**共享代码段**逐行一致（收尾评估段 / 导入区 / 工具层 = **165 行**）；不一致 **exit 1** ⇒ 可当门禁用 ✓；另有**段长基线守卫**（`EXPECTED_LINES`）：段长偏离 ⇒ 醒目告警 ✓，`--strict` 下计为失败 ✗ —— 用来抓"锚点被挪位 ⇒ 覆盖缩水但内容比对照样通过"✗✗ | 注释/文档串差异（**按设计忽略** ✓）；锚点不唯一时它**报错退出**而不是猜 ✓；三入口"本该不同"的段（参数表 / 准备段 / 加载段 / 建环境三行）不在此列 ✗；**精简版不在此列** ✗ —— 它是详注版的派生物（去详注块 + 短文档串 + 删兼容别名 + 裁掉全部未引用导入 ✓），每步各有守卫，比对详注版即可 ✓ |
| `python -m py_compile` | **语法级**错误（含 `ast.parse` 查不出的 `global` 位置错）| 运行时逻辑 |
| `--check-reward` | 自定义奖励的**温度项**与原版逐位一致 | 动作项（原版没有 ✓）|
| `_strip_detail_notes.py` | 生成的「简版」与原件 **AST 逐字相同**（只删 `[详注-BEGIN]…[详注-END]` 块，且块内只有注释/空行 ⇒ 不可能删到代码 ✓）+ 原文件哈希未变 | 简版是否"读起来好看"；它**不参与**生成流程，也不改原件 |

---

## 4. 注释与历史的分工（最重要的一条）

- **代码里只写当前口径**：变量 / 公式现在是什么、怎么用、有哪些坑 ✓
- **不要逐个标注**「见 DECISIONS.md §N」（同一条约定重复几十处 = 冗余 ✗）——
  该约定只在 `Multi-agent.py` 的 docstring 之后**声明一次**，
  生成器会把它**原样带入** `Multi-agent-train.py` / `Multi-agent-eval.py` ✓
- **历史 / 证伪 / 回退 / 实测数字** ⇒ **追加到 `DECISIONS.md`**，不要写回代码 ✗
- `DECISIONS.md` 是**只读参考**：参数值以代码为准 ✓
- 清理历史遗留的冗余指针：`python _strip_doc_pointers.py`（dry-run）→ `--apply`；
  它只改每行 `#` 之后的文本，改完用 `_q_ast_fingerprint.py check` 自证代码未变 ✓
- 要交**简明注释版**（论文/答辩用）：`python _strip_detail_notes.py`（dry-run 先看块清单 ✓）
  → `--apply` 写出 `_simple_notes/*.py` ✓。它只删 `[详注-BEGIN]…[详注-END]` 之间的**详细注释**，
  每步上方的**简略注释**保留 ✓；三重守卫：块内只有注释 ✓ / 简版与原件 **AST 逐字相同** ✓ /
  原文件哈希未变 ✓ ⇒ 简版**可直接运行**且行为与原件一致 ✓。改了源文件后重跑它刷新即可 ✓
- **失效/过时的探针与诊断脚本 ⇒ 移到 `_archive/`** ✓（不在文档里逐个标注 ✗，避免又形成死清单 ✗）。
  当前已归档 2 个：`_verify_p0b.py`、`_smoke_c4_floor.py` ✓；它们**不进任何流程** ✓。
  判定"过时"的唯一依据是**实跑**（`exit != 0` 或断言的是已删除的常量/函数 ✓）——
  ⚠️ 别照抄历史清单 ✗：`_smoke_test_p0.py` / `_smoke_test_p1p2.py` 曾被记为"过时"，
  但 2026-10-02 改成语义化断言后**都已通过** ✓（照旧清单搬会误伤 ✓）

---

## 5. 已知坑（都踩过，逐条都吃过亏）

| 坑 | 症状 | 规避 |
|---|---|---|
| **形参默认值 ≠ 实际配置** | 改了 `custom_comfort_reward.py` 的形参默认值却"毫无效果" | 运行时总是用 `CUSTOM_REWARD_KWARGS` 实例化 ⇒ **只改它** ✓（§9.1）|
| **`fragment` 不能乱动** | 策略退化成"从不制冷"、KPI 不适 0.93+ | 保持 `"auto"`（=100 env-step/轮）✓（§12.3）|
| **早停参数已删除** | 配置页/DB 里若还传 `early-stop-*` ⇒ 脚本崩 | 评估期早停已整块移除 ✓，Java 白名单也已同步 ✓ |
| **Java 白名单** | 新增/删除 CLI 参数后平台仍按老表翻译 | `citylearnjava/.../BaseDataService.java` 的 `map.put("multi-agent*.py", ...)` **必须同步** ✓ |
| **`P4_COST_HINGE` 用 dict** | 直接 `global` 赋值报 `SyntaxError` | 保持容器形式；**用 `py_compile` 校验**（`ast.parse` 查不出）✓（§10.4）|
| **映射侧硬干预** | "关冷自锁"其实是没学会；加下界只会把热超标平移成冷超标 | 别加 per-building/固定常数规则 ✓（§14）|
| **探针窗口** | head 低估 5 倍 / head+tail 高估 33.5pp ⇒ 判据反向 | 中评一律用 `'full'`（整段、start=0）✓（§13.2）|
| **评估入口已无奖励权重开关** | 评估时传 `--bat-weight/--bat-loss/--cost-weight` ⇒ `unrecognized arguments`；或"推演里的 reward 口径与预期不符" | 奖励口径一律**从 checkpoint 读回**（`<ckpt>/reward_config.json` ✓，由训练侧写入）；要换口径 ⇒ 改训练侧开关并**重训** ✓。历史断点没有 sidecar ⇒ 打 warning 并用当前默认（§15）|

---

## 6. 文件与不变量

| 不变量 | 期望值 |
|---|---|
| 三方模块级常量 | 源 **83** 个；两个入口 = 83 + `DEFAULT_CHECKPOINT_DIR`（生成器注入 ✓）|
| `CUSTOM_REWARD_KWARGS` | 31 键，三方值源码哈希一致 ✓ |
| 评估 | **一律跑满** episode，KPI 恒为全程口径 ✓。步数**完全由数据集决定**：`build_env_config` 一律传 `episode_time_steps=None` ⇒ CityLearn 用数据集自带长度（`citylearn.py:910`）✓；探针直接读 `schema.json` 的 `simulation_end_time_step` ✓；启动日志打印实际长度，读不到（≤0）即报错 ✓ |
| 采样口径 | `fragment="auto"`、`MIN_SAMPLE_TIMESTEPS_PER_ITERATION=100`、`TRAIN_INTENSITY` 由目标反推 ✓ |

---

## 7. 脚本命名约定（`citylearnpy/_*.py` 有两百多个，按前缀认）

| 前缀 | 含义 | 例子 |
|---|---|---|
| `_q_*` | **校验/审计**（可反复跑 ✓）| `_q_ast_fingerprint.py`、`_q_config_parity.py`、`_q_batch2_audit.py`、`_q_eval_seg_diff.py`、`_q_stale_api.py` |
| `_diag_*` | 一次性诊断（当时的取证脚本，留在仓库备查）| `_diag_b2_cost.py`、`_diag_train_amount.py` |
| `_probe_*` | 探针（离线扫参/读环境）| `_probe_floor_fullseason.py` |
| `_smoke_*` | 冒烟/单元式验证 | `_smoke_test_p6.py` |
| `_analyze_*` / `_verify_*` | 结果分析与事后核验 | `_analyze_88809afe.py` |

> 交付前请**优先保留并维护 `_q_*` 这几个**（它们构成上表的"自证链" ✓）


---


> ⚠️ 上面这些说明里的模块名是**当时**的 ✓；2026-10-07 utils 合并/改名后对应关系：
> `envs.py→env.py` ✓ `runtime.py + entry_boot.py→base.py` ✓ `trace.py→report.py` ✓
> `train_eval.py + train_phase.py + mid_eval.py + cost_ref.py + action_hook.py + checkpoint_utils.py→train.py` ✓
> ⇒ **附录 A 的历史原文保持原样**（其中的旧模块名属史料 ✓）、正文已全部改成新名 ✓。
# 附录 A · 详注汇编（2026-10-07 ✓）

> 2026-10-07 按要求把**详注版里的多行详注压成正文 1 行** ✓ —— 原文**一字未删**、全部搬进本附录 ✓。
> 正文只留 1 行摘要；要看当年的完整论证时按下面小节查 ✓。

## A2 · 注释约定（源文件头部 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
# 注释约定：只写**当前口径**（变量 / 公式 / 坑 ✓）；历史统一放 DECISIONS.md ✓
# =============================================================================
# ⚠️ 注释约定（全局只此一处声明；本段会被原样带入两个生成入口）
# -----------------------------------------------------------------------------
# 适用范围：本目录下**手改的三个源文件**（`Multi-agent.py` / `_gen_marl_split.py` /
#   `custom_comfort_reward.py`）以及由它们生成的 `Multi-agent-train.py` / `Multi-agent-eval.py`。
# 这些文件的注释**只写当前口径**：变量 / 公式现在是什么、怎么用、有哪些坑。
# **所有历史**（参数怎么改过来、实测数字、为什么被证伪、怎么回退）统一放在
#   `DECISIONS.md`（同目录，§1–§14）—— 按参数名或关键词全文检索即可 ✓
# ⇒ 因此本文件与两个入口里**不再逐个标注**「见 DECISIONS.md §N」（那是冗余 ✗）；
#   新的判决请**追加到 `DECISIONS.md`**，不要写回代码注释 ✗
# =============================================================================
# [详注-END]
```

## A3 · 依赖总览 + import 顺序（源文件头部 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# =============================================================================
# 【依赖总览】本文件的**全部 import 都集中在下面这一段**（到"奖励模块"为止），
#   正文（函数定义与 main 流程）里**不再出现任何 import** ✓
# 例外只有三类，都在本段内各自有说明：
#   ① 三处 try/except 兜底（torch 线程数 / 决策推演模块 / 奖励模块）—— 允许降级运行 ✓
#   ② 两个生成入口（Multi-agent-train.py / -eval.py）多一行由生成器注入的 import
#      （checkpoint 存取），同样落在**同一区域** ✓ 见 _gen_marl_split.py
# 顺序约定：标准库 → 环境准备（线程 env / sys.path 注入）→ **项目日志与补丁**
#           （utils.runtime ✓，只依赖标准库 ⇒ 必须最先，后面任何 import 出问题都还能打日志 ✓）
#           → 第三方（numpy / pandas / torch / gymnasium / citylearn / ray）→ 其余 utils.*
#           （每个都带"为什么在这里"的说明 ✓）→ 奖励模块 ✓
# ⚠️ 两条硬约束 ✗✗：① 线程 env 三行必须在 numpy / pandas / torch **之前**（它们 import 时就定线程池 ✓）；
#   ② `import pandas` 不得提到线程 env 之前（连带 numpy ⇒ 三行 setdefault 会变成死代码 ✗）。
# =============================================================================
# [详注-END]
```

## A4 · 为什么单线程（源文件头部 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
# ⚠️ 必须写在 **import numpy / pandas / torch 之前**：这几个库在 import 时就按
#    OMP_NUM_THREADS / MKL_NUM_THREADS 定好内部线程池，之后再设**不生效** ✗
# -----------------------------------------------------------------------------
# 本任务的算子都极小：SAC learner 是 batch≈256 的 256×256 小网络；CityLearn 的
# LSTM 动力学是逐楼 batch=1 前向。这种情况下把线程开满只会互相抢锁空转
# （实测：进程 CPU/墙钟 ≈ 12.5，即十几个核在为空转的小算子干活）。
# 单线程通常更快，且**不影响结果**。想对比可设环境变量 TORCH_NUM_THREADS=4。
# 注意：这里的上限/下限只影响 CPU 算子并行度。实测该 learner 是"框架开销主导"
# （batch 1024 的一次整批更新要 ~26s，而同样规模的三层 MLP 数学只需几十毫秒），
# 所以调这个数**不会**解决训练慢的问题，别在这上面花时间。
    # [详注-END]
```

## A5 · sys.path 注入那 1 行（源文件头部 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
# 因此必须先把项目目录注入 sys.path，否则下面的 utils.* / eval_step_trace import 失败 ✗。
# 优先级：环境变量 CITYLEARNPY_DIR → 项目默认路径（就地运行时脚本自身目录已在 sys.path[0] ✓）。
#
# 为什么只剩 1 行 ✓（这是**物理下限** ✗，不能再并进工具类）：
#   · "找目录 + 塞 sys.path"**必然**发生在 import 工具类**之前** ✗✗ —— 先有鸡还是先有蛋：
#     搬进 utils/ 就得先 import utils/ ✗（平台复制执行时脚本目录里没有 utils/ ✗）；
#   · 其余全部已归口 utils/runtime.py ✓：
#       - 目录本身 = 那里的 `CITYLEARNPY_DIR` ✓（由**它自己的** __file__ 推出，比入口猜更权威 ✓）
#         ⇒ 本文件下面直接 `from utils.runtime import CITYLEARNPY_DIR` 取用 ✓；
#       - "归一化 / sys.path 去重 / PYTHONPATH 写入（Ray 子进程 ✓）" = `ensure_on_pythonpath()` ✓，
#         而且 `utils/runtime.py` **一被 import 就自动挂好** ✓（幂等 ✓）⇒ 入口不必再调 ✓。
    # [详注-END]
```

## A7 · 环境相关 import 为什么集中（源文件头部 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# 为什么集中在这里 ✗：这些实现原先**内联在本文件里** ⇒ 生成的 eval/train 入口里躺着一整套
#   从不被调用的代码（训练侧约 290 行 ✗ / 探针工厂 ✗ / 上下文环境与 COOL_* · OBS_CONTEXT_* 开关 ✗）；
#   2026-10-02 起陆续下沉到 utils/ ⇒ 三个入口共用一份实现，专用入口只剩 import ✓。
# 本组全部来自 `utils/envs.py` ✓，含四类：
#   ① schema.json 定位与观测口径改造：install_temp_delta_override / patch_schema_observations /
#      resolve_schema_path（本文件只提供配置值 OBS_EXTRA_ACTIVE / TEMP_DELTA ✓）；
#   ② 解包：unwrap_action（动作）/ unwrap_citylearn_env（环境 ✓；精简版会裁掉它 ✓）；
#   ③ 楼栋上下文环境与冷却动作映射：ContextRLlibEnv / _make_agent_env / COOL_* / OBS_CONTEXT_* /
#      get|set|update_cool_floor_scale（诊断脚本按 `ma.ContextRLlibEnv` / `ma.COOL_*` 取用 ✓）；
#   ④ 建环境：build_env_config / build_probe_env（探针工厂 ✓）。
# ⚠️ 改奖励参数请去 `utils/config.py`（不再在本文件里 ✓）；`resolve_schema_path` 的既有调用
#   （含 _smoke_test_*/_diag_* 的 `ma.resolve_schema_path(...)` ✓）与 monkeypatch 继续有效 ✓。
# 另一半（读数与中期评估）来自 `utils/train_eval.py` ✓：find_metric / read_building_series /
#   run_mid_eval / run_mini_eval / run_nocontrol_cost_ref（无控制成本参照 ✓）。
# [详注-END]
```

## A6 · 日志与运行环境 import（源文件头部 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# 本组来自 `utils/runtime.py`（"进程 / 子进程运行环境准备"的归口 ✓），含三类：
#   ① 日志出口：log_console（统一出口）/ log_once（同 key 只报一次）/ log_kpi_read_err
#      （读楼栋量失败的告警）✓。它**只依赖标准库** ⇒ RLlib worker 进程、奖励模块、
#      独立小脚本都能安全 import ✓；三入口共用一份 ⇒ 改日志格式只改一处 ✓
#   ② 包根目录：CITYLEARNPY_DIR（= citylearnpy ✓，由 utils/runtime.py **自己的** __file__
#      推出 ✓）；该模块一被 import 就把它挂到 sys.path / PYTHONPATH 上（幂等 ✓）
#   ③ Windows 兼容补丁：patch_windows_resource_limits()（Ray 会用到 Unix 的 resource API ✓）
#      背景 ✗ / 两个"必须"（**早于 `import ray`** ✓、必须是**调用**（带 `()` ✓））见
#      utils/entry_boot.py 的 docstring ✓ —— 2026-10-06 起，这**四件事**（补丁 / torch 单线程 /
#      pd 显示选项 / 乱码与警告）随下面那句 import 一起生效 ✓（原先三个入口逐字相同 ⇒ 抽一份 ✓）
# ⚠️ 整组必须写在上面 sys.path 注入**之后**：脚本被 Java 复制到 output/outkpis/<taskId>/
#   再执行时，正是靠那一行把 citylearnpy（= utils/ 的父目录）找回来，才能 import ✓
# [详注-END]
```

## A1 · 训练入口文件头横幅（生成器 BANNER_TRAIN ✓）

```text
BANNER_TRAIN = r'''# =============================================================================
# 【训练专用入口 train · 详注版】由 _gen_marl_split.py 从 Multi-agent.py 生成 —— 勿手改 ✗
# 只训练、不评估：训练结束存 RLlib checkpoint 并打印 CHECKPOINT=<路径> 后退出 ✓
#   与源文件的差别：① 不跑评估仿真 ② 参数表裁掉纯评估参数（--no-trace）✓
#   平台取模型：读日志里的 CHECKPOINT=<绝对路径>；KPI 由 Multi-agent-eval.py 产出 ✓
# 细节（执行流程 / 阅读地图 / 名词表 / 每一步的坑）看正文里每一处「详注块」✓
# =============================================================================
'''
```

## A8 · 训练收尾为什么只存 checkpoint（生成器 TRAIN_SAVE_BLOCK ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # 本段替换掉源文件里「训练完成 → 跑评估仿真」的收尾：训练脚本到这一步就结束，
    #   评估（仿真 / KPI / 决策推演）全部交给 Multi-agent-eval.py 做 ⇒
    #   一次训练可以反复评估（换 checkpoint、换评估数据集等）而不必重训 ✓
    #   注意：奖励口径已改为**从 checkpoint 读回** ⇒ 评估入口不再有 --bat-weight 等开关 ✓
    # 复用 utils/train_eval.py 里已被 CHESCA-ResMARL 验证过的存取实现，
    #   避免「怎么存 / 怎么找最新 checkpoint」两处各写一份而漂移。
    #   （2026-10-02 整理：save_multi_agent_checkpoint 已统一到**文件顶部依赖区** import ✓）
    # [详注-END]
```

## A9 · 装动作注入钩子（main ① ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    #   · 幂等 ⇒ 重复调用只返回 'already_installed' ✓
    #   · 必须排在**任何环境构造之前**：晚一步就会出现"奖励读不到动作 ⇒ 动作项静默为 0"✗✗
    #   · 2026-10-03 起它从「导入期」移到这里 ⇒ 只 import 本文件而**不运行**的脚本，
    #     需自行调用 install_action_hook()（读 rf._pending_acts 的探针就是这种 ✓）
    #   · 若将来重新启用多进程采样（Ray worker），它不 import 入口脚本 ⇒ 不在覆盖范围 ✗
    #     （`--env-runners` 已于 2026-10-07 撤下 ✓ ⇒ 当前单进程采样，不受影响 ✓）；
    #     真要覆盖它，应改由 env 类 / 奖励模块在**导入期**调用（见 utils/envs.py 头部 ✓）
    # [详注-END]
```

## A10 · 解析命令行参数（main ② ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    #   · --output-dir(-o) 由 Java 平台注入（= 任务目录 .../outkpis/<taskId>），其余参数按需
    #   · eval / train 两个入口的参数表已被生成器裁剪成各自真正生效的子集 ✓
    # [详注-END]
```

## A11 · --check-reward 详解（main ③ ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # ② --check-reward：**奖励公式的回归自检**（不训练、不仿真，几秒后退出）。
    #    · 它做什么：custom_comfort_reward.check_reward_equivalence() 造一批合成观测
    #      （3 种 hvac_mode × 2 组设定点 × 9 个温度 × 2 种冷热负荷 = 108 条），
    #      分别喂给两个奖励对象，再逐条比对返回值、取**最大绝对差**：
    #        A) 本项目的 CustomComfortReward（用 CUSTOM_REWARD_KWARGS 实例化）
    #        B) 数据集自带的原版 ComfortReward（CityLearn 官方实现）
    #    · 为什么必须有这一步：本项目是通过
    #        reward_function='custom_comfort_reward.CustomComfortReward'
    #      把官方奖励**替换**成我们自己写的一份实现的（这样才能加快捷参数/统计项）。
    #      一旦定制时不小心改动了温度项公式，"训练目标"与"官方 KPI 口径"就会脱钩
    #      ⇒ 出现「训练回报一路变好、但 discomfort_* / cost_total 反而变差」的假象 ✗。
    #      这条命令就是防它的门禁：证明"只是换了实现载体，公式一字未动" ✓
    #    · 判据：返回的最大绝对差 == 0.0 ⇒ 退出码 0（一致 ✓）；≠0 ⇒ 退出码 1（不一致 ✗）
    #      所以它能直接写进脚本/CI 当回归测试用（三个入口都支持这个开关，任选其一：
    #      `python Multi-agent.py --check-reward`，期望看到「温度项总体最大绝对差 = 0.000e+00」）。
    #    · 注意它**只校验温度项**：用例不带动作（_pending_acts 为空）⇒ 所有与"开度"有关的
    #      项（过热保底罚 / 过吹罚 / 过冷关冷罚）读不到 act，自动不参与计算。
    #      动作项是本项目**新增**的、原版没有对应实现，本就无从"逐位一致" ✓
    #    · 附带产出：它还会打印两组梯度演示（过热时加大开度 ⇒ 回报上升、过冷时关冷 ⇒
    #      回报上升），供人眼确认奖励方向没反。那是**展示**，不参与上面的判据 ✓
    #    · 实现位置（2026-10-02 起）：custom_comfort_reward.check_reward_equivalence ——
    #      调用点**直接调实现**，并把「当前生效」的 CUSTOM_REWARD_KWARGS 显式传进去
    #      （命令行 --bat-weight / --cost-weight 会改那个 dict ⇒ 不能让奖励模块自己猜：
    #       它的类形参默认值与实际配置并不一致 ✗）
    # [详注-END]
```

## A12 · 输出目录（main ④ ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # ③ 输出目录：-o/--output-dir 优先，否则 DEFAULT_OUTPUT_DIR。
    #    必须先建出来 —— 它同时充当 CityLearn 的 render_directory：回合结束时
    #    exported_kpis.csv / exported_data_*.csv / decision_trace.json 都写到这里，
    #    目录不存在会在渲染阶段才报错（那时的报错信息很难定位回这里）。
    # [详注-END]
```

## A13 · 数据集优先级（main ④ ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # ④ 数据集：优先级 = 命令行（Java 平台注入）> 文件顶部默认值
    #      （DEFAULT_TRAIN_SCHEMA / DEFAULT_EVAL_SCHEMA）。一个写法挡一个坑：
    #        · `or ''`    ：参数没传时是 None ⇒ 先变 ''，否则下一句 None.strip() 直接报错 ✗
    #        · `.strip()` ：平台/配置里可能带**看不见**的首尾空格或换行 ⇒ 数据集名会"找不到" ✗
    #        · `or 默认值`：传了纯空白 ⇒ strip 后是空串 ⇒ 同样落回默认值 ✓（等价于没传 ✓）
    #      各入口只解析自己那个 schema（.py 两个都要；-train 用 train；-eval 用 eval ✓）
    #      改数据集只改文件顶部那两个常量，或命令行传参 ✓
    #      （**不要**把同名变量写回常量区：会静默遮蔽这里的值 ✗）
    # [详注-END]
```

## A14 · 步数为什么一律不传（main ⑤ ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # ⑤ 步数：**一律不传**（= None）⇒ CityLearn 用数据集自带的长度
    #      （例如 local_evaluation 实测 2208 步 ≈ 一整年逐小时 ✓）。
    #      None 在这里是"自动"的**约定值**，不是"没有值" ✗ —— 别改成 0：
    #      0 步 = 空回合，什么都不跑，KPI 直接异常 ✗
    #      历史：曾经有一张"schema → 步数"表按名字硬编步数 ✗ ⇒ 换数据集就得改代码、
    #      写错还会静默截断回合 ⇒ 已彻底删除，改为"数据集自己说了算" ✓
    #      两个变量都要留着：build_env_config(..., steps) 的签名要它 ✓
    # [详注-END]
```

## A15 · 奖励权重覆盖的位置约束（main ⑥ ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # ⑥ 奖励权重覆盖：--bat-weight / --bat-loss / --cost-weight 给了就改
    #      CUSTOM_REWARD_KWARGS（没给就保持文件顶部默认值 ✓）。
    #      ⚠️ 位置有硬约束：**必须排在 build_env_config 之前** ✗ ——
    #      CUSTOM_REWARD_KWARGS 是在 build_env_config 里被拷贝进
    #      env_kwargs['reward_function_kwargs'] 的 ⇒ 建完环境再改这个 dict 对本次运行无效，
    #      只会表现为"参数传了、日志也打了，但结果一点没变"这种极难排查的静默失效 ✗
    #      三个 `_xx_arg` 都是一次性搬运工：取参 → 判空 → float() 塞进字典
    #      （下划线前缀 = "临时量，别当配置项看" ✓）
    #      键名对应：--bat-weight→bat_weight / --bat-loss→**bat_loss_weight** /
    #      --cost-weight→cost_weight（bat-loss 那个键多一个 _weight ✗ 别写错）
    #      三个权重各管奖励里的哪一项（默认值 = utils/config.py 的
    #      CUSTOM_REWARD_KWARGS ✓；命令行只覆盖**本次运行**，不改文件 ✓）：
    #        · `--bat-weight` → `bat_weight`（默认 **50**，当前唯一在用的电池项 ✓）
    #            电池「择时/套利」项：r_arb = −w × max(0, price − p_ref) × (充电 − 有效放电)
    #            （p_ref = 电价滑动均值 ≈0.0334；有效放电 = 真正供给负载的那部分 ✓）
    #            ⇒ 平价充电 margin=0 ⇒ **中性**（可自由充 ✓）；高峰放电 ⇒ 大额正收益 ✓✓
    #            ⇒ 越大越利诱"便宜时充、贵时放，把用电挪到低价时段" ✓（见 §6）
    #            ⚠️ 那个 max(0,·) 必须留着：去掉会倒贴平价充电 ⇒ 过度循环（见 §6）✗
    #        · `--bat-loss` → `bat_loss_weight`（默认 **0 = 关闭**）
    #            电池「损耗/账单」项：给"充电量"本身定价 r_loss = −w × price × 充电
    #            本意是压制"为抓高峰而过度充放" ✗，但实测**罚充电 = 掐掉套利**
    #            （"充电"本身就是套利的投入 ⇒ 放电均价塌回参考价）⇒ 三种形式全劣于不加（见 §7）
    #            ⇒ 保持 0；旋钮留着，等"电池更大 / 峰谷更长"的数据再重估 ✓
    #        · `--cost-weight` → `cost_weight`（默认 **0 = 关闭**）
    #            电费项：直接罚"从电网买电" r_cost = −w × price × max(0, net)（**含电池** ✓）
    #            本意是让策略为总能耗负责 ✗，实测"成本↓、B2 不适↑"（把冷从 B1 搬到 B2 ✗）
    #            ⇒ 净负面、已证伪关闭（见 §4）⇒ 想省电费请用电池择时，别动这个 ✗
    #      ⇒ 实操：日常只调 `--bat-weight` ✓；另两个保留给将来的重估（旋钮还在 ✓）
    #        另注：还有第四个权重 `cool_cost_weight`（§5 制冷电费，默认 2.0）本项目已固定
    #        启用，**没有命令行开关** ✗ ⇒ 上面这三个开关都管不到它 ✓
    #      ⇒ 每次保存 checkpoint 还会把**本次实际生效**的这份配置写进
    #        `<checkpoint>/reward_config.json`（评估端读回它 ✓，见 DECISIONS §15）——
    #        因此评估入口**不再提供**这三个开关 ✓：防止"评估现场换口径"导致推演里的
    #        奖励数字不再是"策略被训练时用的那个目标" ✗
    # [详注-END]
```

## A16 · 训练段为什么下沉（main ⑦ ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # 为什么整段搬 ✓：这一段约 1180 行、占 train 入口三分之二 ✗，且**只服务训练** ✓
    #   （eval 生成时本来就把这段整段换成"加载 checkpoint" ✓ ⇒ 搬走对它零影响 ✓）。
    # 段内代码一字未改 ✓：需要的名字由签名声明，结果用 TrainOutcome 返回 ✓；
    #   日志以 log_console 为名传入 ✓。
    # [详注-END]
```

## A31 · 生成器切分点 probe（main ⑦ ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    #   下面这行 `probe = …` 是**生成器的切分点** ✓（原文只此一处 ✓）：它之前的准备段被 eval 整段
    #   替换成"读 checkpoint"，它之后的训练段被下沉到 utils/train_phase.py ✓。
    # [详注-END]
```

## A30 · 评估期早停相关参数已移除（parse_args 尾部 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # 注：--no-early-stop / --early-stop-pct / --early-stop-after 已随「评估期早停」
    #     一并移除（2026-10-01，原因见文件顶部该常量块的说明）✓
    # [详注-END]
```

## A29 · 为什么删掉 --trace-every（parse_args ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # 2026-10-05 移除 `--trace-every`（判决见 DECISIONS §17）：落盘间隔**固定**为
    #   DECISION_TRACE_EVERY（= 144 ✓，utils/config.py），不再做成命令行参数 ✓ ——
    #   它几乎从不被调，却让"三入口共享段"为它背一整套兜底（见 main 里 trace_every 处的详注 ✓）。
    #   注意 `--no-trace` **保留** ✓：那是"要不要采集"的开关，和"多久落一次盘"是两件事 ✓
    # [详注-END]
```

## A28 · sidecar 读写的归属（import 说明 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# 注（2026-10-05 下沉）：奖励口径的「写 sidecar / 读 sidecar」已搬到 utils/config.py ✓
#   （与 USE_CUSTOM_REWARD / CUSTOM_REWARD_KWARGS 同家 ✓，DECISIONS §15）
#   本文件从顶部 import 回来 ⇒ 训练侧三处保存点与评估侧的准备段调用点都不用改 ✓
#   也 ⇒ 诊断脚本的 `ma._write_reward_sidecar` / `ma._read_reward_config_from_checkpoint` 照旧可用 ✓
    # [详注-END]
```

## A27 · find_metric 的归属（import 说明 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# 注（2026-10-05 下沉）：`find_metric` 已搬到 utils/train_eval.py（同属"从结果里读数"一类 ✓）；
#   本文件从顶部 import 回来 ⇒ 诊断脚本 `ma.find_metric` 照旧可用 ✓
# [详注-END]
```

## A26 · 早停删掉后成死代码的三个辅助（import 说明 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# 注：随「评估期早停」一起移除了三个只为它服务的私有辅助：
#   _attr_path / _series_prev（读"刚仿真完那一步"的属性链与时序值）
#   comfort_flags（按 KPI 口径判定每栋"高温/低温/有人"）
# 它们的唯一调用方就是早停的逐步统计 ⇒ 早停删掉后即成死代码 ✓
# 需要诊断时用导出的 KPI（discomfort_hot/cold_proportion）或 decision_trace.json，
# 不再在仿真循环里逐步重算一遍 ✓
# [详注-END]
```

## A25 · 逐步采集的归属（import 说明 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# 注：逐步采集的实现已抽到 utils/trace.py；本文件把它 import 回来后
#   仍以 `record_step_trace` 暴露 ⇒ probe 脚本可继续用 ma.record_step_trace 调用。
# decision_trace_path 的实现已抽到 utils/trace.py（诊断脚本仍可用 ma.* 调用）✓
# [详注-END]
```

## A24 · install_action_hook 的调用位置（import 说明 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# 注：原先这里还有一行**模块级**调用 `install_action_hook()`；2026-10-03 移到
#   `__main__` 第一行（= 流程最开始）⇒ 只 import 本文件的脚本若需要它，请自行调用 ✓
# [详注-END]
```

## A23 · 奖励自检实现的归属（import 说明 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
# 奖励自检的实现已于 2026-10-02 抽到该模块（它校验的对象正是 CustomComfortReward）。
# 这里只 import 实现，本文件保留一个同名"薄垫片"负责把当前生效参数传进去 ✓
# （顺带删掉了原 `from custom_comfort_reward import _clamp_temp_penalty`：
#   本文件内已无任何使用点，属过期导入 ✗；封顶机制由 _smoke_test_p6.py 校验 ✓）
    # [详注-END]
```

## A22 · 日志出口的归属（import 说明 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
# 注：`log_console` 已抽到 runtime.py（见文件顶部 import 处的说明）——
#   全项目的日志出口集中在那一个函数里（print + flush），本文件不再自己定义 ✓
    # [详注-END]
```

## A21 · 回合长度为什么传 None（import 说明 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
#   · 环境   ：build_env_config 传 episode_time_steps=None ⇒ CityLearn 用数据集自带长度 ✓
#              （源码 citylearn.py:910：`… = 数据集长度 if episode_time_steps is None else <传入值>`）
#   · 探针   ：直接读 schema.json 的 simulation_end_time_step（见 build_probe_env）✓
#   · 自检   ：评估段把环境实际长度打印出来（读不到就立刻报错，不让 0 流到下游 ✗）
#   历史：曾有一张 `SCHEMA_DEFAULT_EPISODE_STEPS` 表（2026-10-02 删除）——
#     它会与数据集版本脱钩、未登记 schema 时只能靠硬编码兜底（要么截断回合、要么越界）✗
    # [详注-END]
```

## A20 · 训练侧常量的归属（import 说明 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
#   已抽到 utils/config.py（2026-10-02）——原先内联于此 ⇒ 评估脚本里躺着约 240 行
#   从不被调用的训练侧常量 ✗；抽出后三个入口只剩这一处 import ✓
#   ⚠️ 不要再在入口脚本里重复定义同名常量：会静默遮蔽这里的值 ✗
    # [详注-END]
```

## A19 · 奖励配置与 sidecar 的归属（import 说明 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
#   （2026-10-05 下沉：那里是奖励配置的唯一真源 ⇒ 配套的 _write_reward_sidecar /
#     _read_reward_config_from_checkpoint / REWARD_CONFIG_SIDECAR 也放那儿 ✓，
#     本文件从顶部 import 回来 ⇒ 诊断脚本的 ma.* 调用与旧引用都不变 ✓）
#   训练侧写：_save_checkpoint / _save_best_checkpoint / 训练收尾（TRAIN_SAVE_BLOCK）；
#   评估侧读：Multi-agent-eval.py 的准备段 —— 必须排在 build_env_config **之前** ✓✗
    # [详注-END]
```

## A17 · 删掉的 SAC 导入（import 说明 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# （2026-10-07 ✓）原先这里有一行 `from ray.rllib.algorithms.sac import SAC   # checkpoint 续训用
#   SAC.from_checkpoint()` —— 续训已整体撤下 ✓（`--resume` + utils/train_phase.py 的续训分支 ✓）
#   ⇒ 本文件再无 SAC 代码用途 ⇒ 删 ✗（模型构建在 utils/train_phase.run_training 里 ✓）。
# [详注-END]
```

## A17b · 为什么删掉降级 try/except（import 说明 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# ⚠️ 2026-10-06 删掉了原先"模块缺失就降级"的 try/except ✗ —— 实测它是**死代码** ✓：
#   · 本文件**前面**已有一大批 utils.* 与第三方 import（runtime / envs / config / pandas ✓）
#     ⇒ 若 utils.trace 真不可达，程序更早就失败了 ✗，永远走不到那个 try ✓；
#   · 它捕的是 ModuleNotFoundError ✗，而"模块在、名字不在"抛 ImportError ✓（捕不到 ✓）；
#   · 这 5 个名字在 utils/trace.py 里全是**模块级无条件定义** ✓（只依赖 numpy / pandas / utils.runtime ✓）。
#   · 2026-10-06 又删掉 `_TRACE_MODULES_OK = True` ✗：它只在**旧设计**里当守卫
#     （`trace_on = _TRACE_MODULES_OK and …` ✓，见 _simple_notes/ 旧快照 ✓）⇒ 早已退化成"恒 True 的摆设" ✓，
#     唯一读者是 `_smoke_test_import_shim.py` 的一行探针（已同步撤掉 ✓）。
# [详注-END]
```

## A18 · checkpoint 存取工具的归属（生成器 CHECKPOINT_FUNCS_BLOCK ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
#   （2026-10-05 起它们来自 utils/train_eval.py ✓ —— 原先寄居在
#     multi_agent_runner_copy.py 那个 CHESCA 专名模块里 ✗ ⇒ 已抽出成公共工具 ✓）：
#   · 该模块的**顶层依赖**很轻（pathlib / typing + utils.runtime），Ray 的 import
#     延迟在函数里 ⇒ 提前到顶部**不新增风险** ✓
#   · 一体化入口 Multi-agent.py 用不到它们（模型就在内存里 ✓），只有本生成物需要 ⇒ 由生成器注入 ✓
#     （两个入口各有一个用不到的名字，属"有意保留"，与文件头横幅的说明一致 ✓）
    # [详注-END]
```

## A35 · main 的共享区 / 切分边界（章节题头 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# =============================================================================
# main —— 三个入口共用这段「启动逻辑」
# -----------------------------------------------------------------------------
# 本文件是「训练 + 评估」一体化入口；_gen_marl_split.py 由它生成另外两个入口：
#   Multi-agent-train.py  保留「训练流程段」，在训练结束处截断 → 存 checkpoint 后退出
#   Multi-agent-eval.py   用「加载 checkpoint」替换「训练流程段」，评估段原样保留
# 切分边界（改本文件时请注意，生成器靠这些标记定位，改坏了生成器会直接报错）：
#   · 【共享区】本行 → `train_schema = ...` 之前：三个脚本**逐字一致**（就是本段）
#   · 【训练准备段】`train_schema = ...` → `probe = _AGENT_ENV_CLS(train_env_config)`：
#       eval 里被整段替换成「评估准备段」⇒ 这里是训练/一体化专属
#   · 【训练流程段】`probe = ...` → `total_steps = int(getattr(citylearn_env, ...))`：
#       eval 里被替换成「加载 checkpoint」；train 里执行完就存档退出。
#       ⚠️ 这一段里还夹着本脚本的「步骤 4/8 建评估环境」3 行（env / citylearn_env / reset）✗：
#         一体化脚本是**训练完再建**评估环境（不提前 —— 免得在 3h 训练期间白占一个
#         CityLearnEnv ✗ 无收益 ✗）；而 eval 侧这 3 行由生成器 EVAL_SETUP_BLOCK 提供、
#         并**提前到"评估配置构建之后"** ✓ ⇒ 它们**不在**下面的【评估段】里 ✓
#         （被本段整段吃掉 ✓，这是 2026-10-05 挪位的**有意**结果 ✗）
#   · 【评估段】`total_steps = ...`（步骤 5/8 第一行）→ 文件末尾：
#       **一体化与 eval 逐字一致**（两个入口都跑这段 ✓；门禁 ⑥ 守的就是它 ✓）
#
# 本段（共享区）的职责，顺序不能换：
#   ① 解析命令行 → ② --check-reward 自检早退 → ③ 落地输出目录
#   → ④ 把「数据集 / 轮数区间 / 种子 / 奖励权重覆盖」解析成确定值（建环境前必须定好）
# =============================================================================
# [详注-END]
```

## A34 · 动作钩子的 import / 调用（章节题头 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# -----------------------------------------------------------------------------
#   本文件只保留「import」，**调用在 `__main__` 的第一行**（= 流程最开始，早于任何环境构造 ✓）
#   ⚠️ 只 import 而不运行本文件的脚本需自行调用 install_action_hook() ✓（理由见流程第一行注释）
#   ⚠️ 状态要用 action_hook_status() **函数**读，不要 import 那个私有变量 ✗
#      （import 变量会把当时的值拷走，装钩子之后再读仍是 not_installed ✗）
# -----------------------------------------------------------------------------
# [详注-END]
```

## A33 · 动作注入补丁为什么必须钩在 step（章节题头 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# =============================================================================
# 动作注入补丁（奖励要用 act_cool 就必须先拿到动作）
# -----------------------------------------------------------------------------
# 问题：CityLearn 的 reward.calculate(observations) **只给观测、不给动作** ⇒ 自定义奖励里
#   所有依赖 act 的项（过热保底 / 过吹罚 / 过冷关冷 / 制冷电耗 / 电池项）都读不到 ⇒
#   ∂R/∂act_cool = 0 ⇒ 策略"加大制冷也拿一样的分"（= §2「高温不制冷」的病根 ✗）
#
# 做法：包装 RLlibMultiAgentEnv.step —— 在「真正 step（内部会调 reward.calculate）」之前，
#   把本步各楼动作按**楼栋顺序** note_pending_actions() 给奖励函数（外加制冷热容量与
#   电池规格，见 pass_actions_to_reward 内三段 ✓）。
#   · 只**读**动作、不改动作、不改返回值 ⇒ 仿真动力学与 KPI 完全不变 ✓
#   · 挂在**基类**上：子类 ContextRLlibEnv 的 super().step() 也会走到 ✓，
#     且 OBS_CONTEXT_ENABLE=False（环境直接用库里那个类）时同样生效 ✓
#
# 为什么必须钩在这里（而不是在调用点自己填 ✗）：
#   · 训练时 env.step 是 **RLlib 内部**调的 ⇒ 全项目没有调用点可以插手 ✗
#   · 评估主循环虽能自己填，但拿不到"经 P-1 重标定后**实际执行**的动作" ✗
#   · 一处覆盖所有调用方（训练 / 评估 / 诊断脚本）⇒ 这是唯一的公共拦截点 ✓
#
# 它在两个入口里的作用域不同（都是**有意**的 ✓）：
#   · 训练：动作项 = 奖励的**梯度来源**（主战场 ✓）
#   · 评估：不参与任何决策 ✗，只把奖励变成**可读的诊断账本** ——
#       决策推演的分项明细与实际执行值（decision_trace.json ✓）、
#       [评估阶段] 统计与"训练↔评估"对照（output.log ✓）；没有它这些会**假零** ✗✗
#   ⇒ 因此不能"只为评估"把它拆掉：train / eval 共用同一份代码，拆开会变成
#     同一句 record_step_trace 在两个入口行为不同 ✗（口径细节见 DECISIONS.md §9.2）
# =============================================================================
# [详注-END]
```

## A32 · 自定义奖励为什么抽成独立模块（章节题头 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# =============================================================================
# 自定义奖励函数：CustomComfortReward（C′-1：已抽成独立真实模块）
# -----------------------------------------------------------------------------
# 类体一字未改地搬到 citylearnpy/custom_comfort_reward.py，原因见该文件头部：
#   原来定义在本脚本里 → 脚本名含连字符、不能作为模块被 import → 只能在进程内注册
#   一个合成模块 → **Ray worker 无法 import 它** ⇒ 当时的并行采样（--env-runners>0）必然失败
#   → 脚本只能单进程采样（数据量上不去、过训练比高达 ~1024，C′ 的结论）。
#   （`--env-runners` 这个旋钮已于 2026-10-07 按使用者要求**撤下** ✗ ⇒ 详见 utils/envs.py 头部两条限制 ✓）
# 本脚本顶部已把本目录加入 sys.path / PYTHONPATH，worker 进程继承同一 PYTHONPATH，
# 因此 worker 也能 import 到同一个真实模块 —— 这正是 C′-1 要解决的问题。
#
# 数值等价性：搬家未改任何字符，`--check-reward` 仍应与数据集原版逐位一致。
# 回退方法：把 custom_comfort_reward.py 的内容粘回本处，并删掉下面三条 import，
#          再把 _CUSTOM_REWARD_MODULE 改回合成名（旧名别名已于 2026-10-06 删除 ⇒ 需自行在进程内注册 ✓）。
#
# ⚠️ 澄清（常见误解）：本文件里**没有** `class CustomComfortReward` 的定义 ✗ ——
#   类体只存在于 citylearnpy/custom_comfort_reward.py，下面这三行就是"引用入口"。
#   三个入口脚本（本文件 / Multi-agent-train.py / Multi-agent-eval.py）都走同样三行，
#   导入方式**完全相同**（生成器逐字复制）⇒ 不存在"某个入口引的是内部副本"这种事 ✓
# [详注-END]
```

## A36 · 奖励自检薄垫片为什么移除（源文件 + 生成器常量同名 ✓）

```text
    # [详注-BEGIN]（生成简版时整段删除）
    # 注：原先这里有一层同名"薄垫片" `def check_reward_equivalence(verbose=True)`，用于兼容
#   `_smoke_test_p6.py` / `_smoke_test_p13.py` 里的 `ma.check_reward_equivalence(verbose=False)`。
#   2026-10-02 **垫片已移除** ✓ —— 那两个探针改为直接调实现，与 `--check-reward` 同一条路径：
#       ma._reward_equiv_check(ma.CUSTOM_REWARD_KWARGS, verbose=False)
#   ⇒ 三入口 + 探针现在完全统一：**实现只有一份（custom_comfort_reward.py），
#     调用点一律显式传参**，不再有"猜参数"的余地 ✓
    # [详注-END]
```

## A37 · describe_reward_function / build_decision_recorder 的归属（源文件 ✓）

```text
# [详注-BEGIN]（生成简版时整段删除）
# 注（2026-10-05 下沉）：原先这里定义的两个函数已搬到各自的"本职模块" ✓ ——
#   · describe_reward_function  → utils/config.py（奖励配置的唯一真源旁 ✓）
#   · build_decision_recorder   → utils/trace.py（记录器所在模块 ✓）
#   本文件从顶部 import 回来（后者在 try 降级块里 ✓）⇒ 诊断脚本 `ma.xxx` 照旧可用 ✓
# [详注-END]
```

## A38 · utils/ 各模块也出「详注版 + 简版」（2026-10-07 ✓）

```text
utils/X.detailed.py   详注版（保留全部 [详注] 块 ✓）—— **唯一可信来源** ✗：改注释只改它 ✓
utils/X.py            精简注释版（= 详注版删掉详注块 ✓）—— **程序 import 的是它** ✓
                      ⚠️ 每次 `python _gen_marl_split.py` 都会把它覆盖 ✗（别手改 ✗）
```

与两个入口同一套约定 ✓：一个生成器、一次生成两份 ✓、代码逐字相同 ✓
（由生成器里的 `ast_digest()` 守卫把关：删详注若动了**代码** ⇒ 拒绝写盘 ✗）。

- 实现位置：`_gen_marl_split.py` 的「**3) utils/ 各模块**」段 ✓ —— 复用
  `_strip_detail_notes.py` 的 `find_blocks` / `guard_only_comments` / `ast_digest` ✓。
- **首次运行**：只有 `X.py` 且它已含详注块 ⇒ 先把 `X.py` **固化**为 `X.detailed.py` ✓，再写简版 ✓
  ⇒ 两条命令都**幂等** ✓、反复重跑安全 ✓。
- **没有详注块的模块会被跳过**并打印一行提示 ✓（当前 `config.py` / `env.py` / `report.py`
  属此列 ⇒ 待补详注块 ✓；补块时把既有长说明**包进** BEGIN/END 即可 ✓，
  只需保证每块**上方紧邻**一句"简略注释"✓ —— 简版里留下的就是它 ✓）。
- 已拆：`utils/train.py`（24 块 ⇒ 2403 → **2248** 行 ✓）、`utils/base.py`（5 块 ⇒ 446 → **276** 行 ✓）。
- 简版头部有 3 行横幅提醒"改注释请改 detailed" ✓（横幅是注释 ⇒ 不进 AST ✓，不影响任何指纹 ✓）。
- ⚠️ `utils/base.py` / `config.py` / `env.py` / `report.py` / `train.py` 都在 **AST 指纹**名单里 ✓
  ⇒ 拆分前后 AST 不变 ⇒ 指纹**一字不动** ✓（实测 `eda53672…` / `66414824…` ✓✓）。

## A39 · utils 合并遗留清理 + checkpoint 目录 bug（2026-10-07 ✓）

**① 合并遗留**（`utils/*.py` 是历史**一次性合并**的产物 ✗；仓库里**没有**合并器脚本 ✓ ⇒ 现在手工维护 ✓）：
- **残留 docstring 字符串**：它是**代码** ✗（不是注释 ⇒ 简版删不掉 ✗）。`base.py` / `config.py` 各一处
  ⇒ 已改写成**注释**并包进详注块 ✓（与 `train.py` 既有做法一致 ✓）；实测全仓**没人**读
  `__doc__` / `getdoc` ✓ ⇒ 无行为影响 ✓。
- **重复 import**：`base.py` 的 `import os` / `import sys` 各出现两遍 ✗ ⇒ 删一份 ✓。
- **重复语句段**：`train.py` 的「ckpt 目录解析」被**粘贴两遍** ✗ ⇒ 去重 ✓。
- **错标签横幅**：`utils/base.py` 里写着"合并自 utils/base.py" ✗、`config.py` 里"· config.py · config.py" ✗
  ⇒ 改写成真段名 ✓（`log_utils` / `process_env` / `entry_boot` / `train_config` / `reward_config` ✓）。

**② checkpoint 目录 bug（真 bug ✗ —— 训练写一处、评估读另一处）：**
`utils/train.py` 解析相对路径时用 `Path(__file__).resolve().parent`（= **`utils/`** ✗✗）⇒ 不传
`--checkpoint-dir` 时 checkpoint 会写进 `utils/checkpoints/…`，而**评估侧**读的是
`DEFAULT_CHECKPOINT_DIR`（= `CITYLEARNPY_DIR / CKPT_DIR` = `citylearnpy/checkpoints/…` ✓）
⇒ "没传参数就找不到断点" ✗。已改为 ✓：**没传** ⇒ 直接用 `DEFAULT_CHECKPOINT_DIR`（与评估侧**同一常量** ✓，
从此不可能再漂移 ✓）；**显式传相对路径** ⇒ 基准改为 `CITYLEARNPY_DIR`（包根目录 ✓）。
证据 ✓：相对 `--checkpoint-dir _tmp_ck_probe` 的 1 轮冒烟 ⇒ checkpoint 落在
`citylearnpy\_tmp_ck_probe\` ✓（**不再**是 `utils\` ✓）、exit 0 ✓；端到端 KPI `af7dd1ba…` +
TRACE `8c9aac97…` **逐字节同基准** ✓。
⚠️ **平台提醒** ✓：若此前依赖 `utils/checkpoints/…`（错误位置）找断点，请改看
`citylearnpy/checkpoints/multi_agent_resume/` ✓ —— 那正是评估默认读的位置 ✓。

**③ 生成器加固 ✓**：`utils/X.py` 首次被"固化"为 `X.detailed.py` 时会打印**醒目告警** ✓ ——
2026-10-07 实测踩过一次：误删 `base.detailed.py` 后，生成器把磁盘上的**简版**当成详注版固化 ✗
⇒ 详注块丢失 ✗（已从 `_tmp_bak24/` 复原并重做 ✓）。

**④ 进度** ✓：`utils/base.py`（6 块 ✓ 444 → **266** 行）、`utils/config.py`（36 块 ✓ 611 → **315** 行）、
`utils/train.py`（24 块 ✓ 2409 → **2254** 行）已拆；**`env.py` / `report.py` 待补详注块** ✓。

## A40 · utils 五模块**全部**完成拆分（2026-10-07 ✓）

| 模块 | 详注版 `X.detailed.py` | 简版 `X.py`（**程序 import 它** ✓） | 拆掉 |
|---|---|---|---|
| `base.py` | 444 行 / 6 块 ✓ | **266** 行 ✓ | 181 行 ✓ |
| `config.py` | 611 行 / 36 块 ✓ | **315** 行 ✓ | 299 行 ✓ |
| `env.py` | 1069 行 / 23 块 ✓ | **661** 行 ✓ | 411 行 ✓ |
| `report.py` | 880 行 / 6 块 ✓ | **807** 行 ✓ | 76 行 ✓ |
| `train.py` | 2409 行 / 24 块 ✓ | **2254** 行 ✓ | 158 行 ✓ |

- **块规则**（`env` / `report` 这两份是**扫描器挑的** ✓，`base` / `config` / `train` 是手工圈的 ✓）：
  连续注释段（允许夹空行）注释行 **≥ 3** ⇒ 保留**首 1–2 行**当简略行 ✓（首行是 `# ====` / `# ----`
  分隔线 ⇒ 连标题一起留 ✓），其余整段包进详注块 ✓；剩不足 2 行的段跳过 ✓
  ⇒ **简版里每段都还留着"一眼看懂的那句"** ✓。
- 残留 docstring：`env.py` / `report.py` 各 1 处 ✓ 也已改成注释 ✓（与 `base` / `config` 同款 ✓）——
  它们是合并遗留的**字符串表达式**（是**代码** ✗）；实测全仓**没人**读 `__doc__` ✓。
- 验证 ✓：编译 / 导入（含两份 `.detailed.py` ✓）/ `--check-reward` / 门禁 `--strict` /
  `--help` 字节数（12148 / 8704 ✓）/ 端到端 KPI `af7dd1ba…` + TRACE `8c9aac97…` **逐字节同基准** ✓ /
  训练 1 轮冒烟 exit 0 ✓。
- 指纹 ✓：本轮只有 `utils/env.py`（`ec217415…` → `ddaa405b…`）与 `utils/report.py`
  （`7fae5f35…` → `af3ff620…`）变动 ✓ —— 原因 = 清残留 docstring ✓；
  两个入口 / `custom_comfort_reward.py` / `base` / `config` / `train` **一字未变** ✓。

## A41 · 收尾三件（2026-10-07 ✓）

**① 过期说明改写 ✓**：`utils/train.detailed.py` 里曾有一句"原来嵌在源码里的 `[详注]` 标记
**没有搬过来**" ✗ —— 那是 `train.py` 刚搬进 utils 时写的；现在 utils 里**到处是**标记 ✓
⇒ 说法已过期 ✗。已改写为正确说法（本文件是详注版 / 简版由生成器产出 / 改注释改本文件 ✓），
并**整段收进详注块** ✓ ⇒ 简版不再显示过期文字 ✓（实测 `utils/train.py` 里
「没有搬过来」**0 次** ✓、`详注-BEGIN` 字样 **0 次** ✓）。

**② 密度复核 = 已饱和 ✓**：用**块感知**扫描器（跳过已包过的段 ✓）把阈值从 3 行降到 2 行复核 ——
`env.detailed.py` / `report.detailed.py` 里"包掉能省 **≥2 行**"的候选都是 **0 段** ✓
（`report.py` 降到 2 行只剩 1 段 / 3 行、`env.py` 只剩 6 段 / 8 行 ⇒ 每段只省 1 行，
详注版却多 2 行标记 ✗ ⇒ 纯噪声 ✓）。⇒ 长解释都已进块 ✓，剩下的都是 1–2 行的短句 ✓
（**简版靠它们读懂代码** ✓）⇒ 不再动 ✓。想再瘦只能删信息 ✗（要另说 ✓）。

**③ 备份清理 ✓**：`_tmp_bak*` 只留最近 4 个（`_tmp_bak25`~`28` ✓，分别对应
"改 base/config/train 前" / "改 base/train 前" / "插 env/report 块前" / "改过期说明前" ✓），
早期 16 个已删 ✓。

**验证 ✓**：编译 / 导入（简版 + 详注版 ✓）/ `--check-reward` / 门禁 `--strict` /
`--help` 字节（12148 / 8704 ✓）/ 端到端 KPI `af7dd1ba…` + TRACE `8c9aac97…` **逐字节同基准** ✓ /
训练 1 轮冒烟（错误行 0 ✓）；指纹 = 只有 `utils/train.py` 行数 2254 → **2252** ✓，**AST 一字未变**
（`edf997de…` ✓）= 纯注释改动 ✓。

## A42 · 每个 def 加一行"新手向"注释 + docstring 收进详注块（2026-10-07 ✓）

**做法** ✓（一个脚本一次做完 ✓，见 `_tmp_def_comments.py`）：
1. 在 `def`（含装饰器 ✓）**上方**插一行 `# 一句话说清这个方法干嘛` ✓ —— 这行落在详注块**外** ✓
   ⇒ **简版会保留它** ✓（新手读简版就够 ✓）。文字优先取**人工对照表** ✓（技术名词多的、
   以及**没有 docstring** 的函数必须给 ✓）；其余从 docstring 首行加工（去 `**` ✓、补 ` ✓` ✓）。
2. 把函数 docstring **改成注释**并整段包进详注块 ✓（= "融入详细版注释" ✓）⇒ 简版不再显示 ✓
   ⇒ 方法体里的"引号注释"从此**不在代码里** ✓（⚠️ docstring 是**代码** ✗，不是注释 ✓）；
   若函数体**只有** docstring ⇒ 补一句 `pass` ✓（否则语法错 ✗）。

**守卫** ✓：① 归一化 AST（**递归**忽略纯字符串表达式 ✓、空 body 视作 `pass` ✓、顶层完全重复的
import 去掉 ✓）**逐字不变** ✓；② 改完**不许**再有任何 def 带 docstring ✓；③ 幂等 ✓
（上方已是同一行就跳过 ✓）；④ **三个文件先全部算好再统一写盘** ✓（任一检查失败 ⇒ 文件系统一个字不动 ✓）。

**进度** ✓：

| 文件 | 加了一行注释 | docstring → 详注块 | 简版行数 |
|---|---|---|---|
| `base.py` | 8 个 def ✓ | 8 ✓ | 266 → **178** ✓ |
| `config.py` | 3 ✓ | 3 ✓ | 315 → **297** ✓ |
| `report.py` | 26 ✓ | 13 ✓ | 807 → **752** ✓ |
| `env.py` / `train.py` | **待做** ✗ | 待做 ✗ | — |

**验证** ✓：编译 / 导入 / `--check-reward` / 门禁 `--strict` / `--help` 字节（12148 / 8704 ✓）/
端到端 KPI `af7dd1ba…` + TRACE `8c9aac97…` **逐字节同基准** ✓（= 去掉 docstring **没改变任何行为** ✓）/
训练 1 轮冒烟 0 错误行 ✓；指纹 = 只有 `base` / `config` / `report` 变动 ✓（`env` / `train` / 两个入口**未动** ✓）。

**⚠️ 本次**没**动的** ✓：**class 的 docstring**（如 `MarlDecisionTraceRecorder` ✓）—— 范围是"方法" ✓；
要一并处理说一声 ✓（同一脚本 ✓；去掉后类的 `__doc__` 变 None ✓，实测全仓没人读 ✓）。

## A43 · 收尾三件（2026-10-07 ✓）

**① `utils/base.py` 顶部改成 2 行** ✓（应使用者要求 ✓）—— 说明"被引用时主要起什么作用" ✓，
写在详注块**外** ⇒ **简版也看得到** ✓：

```text
# base = 三个入口共用的「启动靴」：日志工具 + 子进程/Ray 环境准备 + torch 单线程 + 编码与警告 ✓
# 用法：`from utils.base import …`，必须写在任何重库（numpy/pandas/torch/citylearn/ray）之前 ⇒ 导入即生效 ✓
```
（原来那段 38 行模块说明仍在**详注块**里 ✓ —— 详注版可见 ✓、简版不显示 ✓。）

**② 去掉 base 里重复的 `patch_windows_resource_limits()` 调用** ✓：它是**合并遗留** ✗ ——
`process_env` 段与 `entry_boot` 段**各留了一次** module-level 调用 ✓；函数幂等（每项先 `hasattr` ✓、
非 Windows 直接 return ✓）⇒ 无害但冗余 ✓。已保留带 `# Ray 环境准备` 注释的那处 ✓、删掉紧跟
`import warnings` 之后的那处 ✓ ⇒ module-level 调用只剩 **1 处** ✓。
（`prepare_ray_env()` **函数体内**那处是正当内部调用 ✓，**不动** ✓。）

**③ `utils/env.py` / `utils/train.py` 的"每方法一行注释 + docstring 收进详注块"完成** ✓ ⇒
**五个 utils 模块全部完成** ✓：

| 文件 | 详注版 | 简版 | 一行注释 | docstring → 块 |
|---|---|---|---|---|
| `base` / `config` / `report` | 442 / 620 / 932 | **152 / 297 / 752** | 8 / 3 / 26 | 8 / 3 / 13 |
| `env` / `train` | 1122 / 2493 | **590 / 2160** | 23 / 34 | 15 / 23 |

**验证** ✓：编译 / 导入 / `--check-reward` / 门禁 `--strict` / `--help` 字节（12148 / 8704 ✓）/
端到端 KPI `af7dd1ba…` + TRACE `8c9aac97…` **逐字节同基准** ✓ / 训练 1 轮冒烟 0 错误行 ✓；
指纹已重存 ✓（`base` `7515b358…`、`env` `605d679c…`、`train` `ac5e569e…` ✓ —— 均为**有意**变化 ✓）。

## A44 · utils 死代码 / 失效引用体检（2026-10-07 ✓）

**做法** ✓：先跑仓库现成检查器（`_q_mod_undef.py` 未定义名 ✓、`_q_dup_check.py` 重复函数体 ✓），
再写一个**死代码分析器**（`_tmp_find_dead.py`，临时件 ✓）：判据 = ① 本文件内无引用 ✓
② 别处无 `from utils.X import 它` ✓ ③ 全仓（除镜像 ✓）连**字符串**都搜不到 ⇒ 才算**硬死** ✗；
只被字符串提到 ⇒ **软死**（可能被 `getattr` / 探针按名取用）⇒ **不删** ✓。

**结果与处置** ✓：

| 发现 | 处置 |
|---|---|
| `utils/env.py`：`from typing import Any, Mapping` 里 **`Mapping` 未用** ✗ | 去掉 `Mapping` ✓ |
| `utils/env.py`：`_make_agent_env` **定义了两遍** ✗（两份**逐字相同** ⇒ 后者覆盖前者 ✓）| 删掉第一份 ✓（7 行 ✓；带"两份内容相同"断言 ✓）|
| `utils/report.py`：`format_reward_kwargs_text` **全仓零引用** ✗ | 删掉 ✓（24 行，含上方注释 ✓）|
| `utils/train.py`：局部 import 里 **`CKPT_DIR` 未用** ✗ | 去掉那一行 ✓（另一处 import 仍在用 ✓ 不动 ✓）|
| `utils/train.py`：header 里 3 条 **`· train_eval.py`**（模块早没了 ✗）| 换成**实际段名** ✓：`mid_eval` / `cost_ref` / `action_hook` / `checkpoint_utils` ✓（由脚本扫段横幅生成 ✓）；顺手改掉"合并自 utils/train.py"这种自我指涉横幅 ✓ 与失效的 `# -*- coding` 行 ✓ |

**未定义名检查** ✓：`utils/*` + 三个入口 **全部 OK** ✓（= 没有"少 import / 拼错名"这类真错 ✓）。

**有意保留** ✓（软死 ⇒ 不删，供你定夺 ✓）：
- `utils/env.py` 的 **`_make_agent_env`** ✓：代码里**零调用** ✗，只在字符串里出现 3 次（注释/文档 ✓）；
  入口用的是 `_AGENT_ENV_CLS` ✓ ⇒ **疑似真死** ✗，但怕有探针按名取用 ⇒ 留着 ✓，要删说一声 ✓。
- `utils/env.py` 的 **`_TEMP_DELTA_STATUS`** ✓：名字没人用 ✗，但那一行**调用有必需的副作用** ✗
  （`install_temp_delta_override(TEMP_DELTA)` ✓ 装了覆盖 ✓）⇒ 建议改成"只调用、不接名字" ✓，要不要改说一声 ✓。

**工具盲点（顺带记下 ✗）**：`_q_dup_check.py` 会把 `utils/*.detailed.py` 的**镜像**当成
"重复函数体"报 ✗（它只跳过 3 个入口生成物 ⇒ 应把 `*.detailed.py` 一起跳 ✓）；`_q_mod_undef.py`
未跳镜像（无害 ✓，镜像与本体同名同义 ✓）。临时分析器 `_tmp_find_dead.py` 已留着 ✓，可提升为
正式 `_q_dead_code.py` ✓（需先修它两个假阳性 ✗：`__future__` 导入 ✓、`__file__` 这类 dunder ✓）。

**验证** ✓：编译 / 导入 / `--check-reward` / 门禁 `--strict` / `--help` 字节（12148 / 8704 ✓）/
**端到端 KPI `af7dd1ba…` + TRACE `8c9aac97…` 逐字节同基准** ✓（最强证据：删的确实是死代码 ✓）/
训练 1 轮冒烟 0 错误行 ✓；指纹重存 ✓（`env` `e89296d0…`、`report` `e9280898…`、`train` `18c059af…` ✓）。

## A45 · 评估详注版「不裁导入」是**契约**（2026-10-08 试了又回退 ✗）

**试过** ✗：应使用者要求"`Multi-agent-eval.detailed.py` 里很多引用没用到（如 `_write_reward_sidecar`）⇒ 裁掉"，
在生成器里加了一行 `ev_detailed = _trim_unused_imports(ev_detailed, '评估入口·详注版')` ✓
（排位正确：在 `_strip_detail_blocks` **之前** ✓，简版自然跟着干净 ✓）。

**实测失败** ✗✗：`_q_eval_seg_diff.py --strict` ⇒ **exit 1**、报"2 项未通过 + 段长偏离基线" ✗。
**原因** ✓：门禁的契约就是"**评估详注版与源文件（Multi-agent.py）逐行同源**" ✓，而它靠 **import / 横幅行
当锚点**去定位共享段 ✗ ⇒ 裁掉导入 = 改锚点 ⇒ 段数、段长双双偏离 ✗。

**结论（已写进生成器注释 ✓）**：**详注版必须保持"源文件镜像"** ✓ —— 读代码时那点多余导入是"镜像"的
代价 ✓；**真正跑的是精简版** ✓，它已经裁掉 **84** 个未用导入 ✓。⇒ 生成器那行已**回退** ✓，
并在原处留下上面这段"试过/为什么不行"的记录 ✓（避免下次有人再试一遍 ✗）。
若哪天真要裁详注版 ⇒ 必须**同时重定义门禁的锚点与基线** ✗（那是"改契约"，需单独决定 ✓）。

**本轮另一件事** ✓：`utils/config.detailed.py` 里「过吹罚 / over 罚」那段的注释改成**新手也看得懂** ✓
（讲清"吹过头 = 实际开度 act 超过这栋楼刚够用的 a_ref" ✓、`excess` 公式逐项解释 ✓、
两个容差（绝对 `hot_over_tol` / 相对 `hot_over_tol_frac` ✓）各自作用 ✓、`hot_over_weight` 是"每 1 个
超标单位的罚分权重" ✓、`hot_over_penalty_cap` 是"单步最多扣 60 分" ✓）；只动注释 ⇒ `utils/config.py`
的 **AST 一字未变**（`4b0eff83…` ✓）、端到端 KPI/TRACE **逐字节同基准** ✓、门禁 exit 0 ✓。

## A46 · 删掉「额外整段评估」（FULL_EVAL_*，2026-10-08 ✓）

**为什么能删** ✓：它**默认就是关的**（`FULL_EVAL_EVERY = 0` ✓ ⇒ 独立探针为 None ⇒ 那段循环永不进 ✓），
best-ckpt 早就改用 mid-eval 的**整段**读数（`MID_EVAL_WINDOWS = ('full',)` ✓）⇒ 删除**不改变行为** ✓
（用端到端 KPI/TRACE 逐字节核对 ✓）。

**删了什么** ✓：`utils/config.detailed.py`（3 个常量 + 上方整段说明 ✓）、
`utils/train.detailed.py`（import 3 名 ✓、`log_training_summary` 的形参 + 收尾汇总块 17 行 ✓、
探针准备 9 行 ✓ + 探针创建 try/except 19 行 ✓、mid-eval 的 `_full_eval_hist.append` 5 行 ✓、
主循环「额外的整段评估」整块 66 行 ✓、`TrainOutcome._full_eval_hist` 字段 ✓、调用 kwarg ✓）、
`Multi-agent.py`（import 3 名 ✓ + `log_training_summary(..., full_eval_hist=_o._full_eval_hist)` 实参 ✓）。
**规模** ✓：`utils/train` 2493 → **2367**（简版 2160 → **2063** ✓）、`utils/config` 631 → **618**（简版 **292** ✓）、
`Multi-agent.py` 882 → **878** ✓、`Multi-agent-train.detailed` 486 → **482** ✓、`eval.detailed` 963 → **960** ✓。

**⚠️ 三次尝试的教训（很重要 ✓）**：这活**不能**用"按行/按命中删" ✗✗
- v1 按"单行命中"删 ⇒ 把 `try/except`、`if` 的**块内单行**拆散 ✗（语法崩）；
- v2 按"语句含 full_eval 就删" ⇒ 命中 **411 行**的 mid-eval 大 If ✗✗、还把 **616 行**的训练主循环
  当"一条语句" ✗✗（两次都靠 `assert` 在**写盘前**中止 ✓ —— 守卫救了命 ✓）；
- v3 最终做法 ✓：**读准原文 ⇒ 按行区间精确删**（每段断言首/末行 ✓）+ 3 处 AST 精修 ✓。
**v3 还是留了两个坑 ✗，靠冒烟抓出来 ✓**：① 我"改注释"与"改 `_p4_probe` 赋值"两段区间在**赋值行重叠** ✗
⇒ 赋值被整个删掉 ⇒ `NameError: _p4_probe` ✓；② 源文件里那行**调用实参**没删 ✗ ⇒ 会 AttributeError ✓。
⇒ 已补：从 `_tmp_bak34/` 取回 else 分支源码写回 `_p4_probe = mid_probes[0] if mid_probes else None` ✓、
删掉调用实参 ✓、并把两处**引用已删常量**的注释改准 ✓。
**教训** ✓：区间删除必须写成**半开区间**（`[a, b)` ✓）并断言区间**互不重叠** ✗；改完必须跑**真实训练冒烟** ✓
（`py_compile` + 门禁都抓不到 `NameError` ✗）。

**验证** ✓：编译 / 导入 / `--check-reward` / 门禁 `--strict`（98 行共享代码逐行一致 ✓）/
**端到端 KPI `af7dd1ba…` + TRACE `8c9aac97…` 逐字节同基准** ✓ / **训练 1 轮冒烟 exit 0** ✓ /
`--help` 字节（12148 / 8704 ✓）；指纹重存 ✓（`train` `a9f3a62b…`、`Multi-agent.py` `6f97b0c4…` ✓）。

**⚠️ 遗留（旧探针脚本会 import 失败 ✗，需你定夺 ✓）**：`_smoke_test_p0.py`（8 处 ✓）、
`_verify_p1.py` / `_verify_p2.py` / `_verify_pab.py` ✓ 仍按老名字 import `FULL_EVAL_*` ✗；
以及 `_simple_notes/` 里是**过时的生成副本** ✓（建议直接删掉 ✓，它还会污染"重复代码检查" ✗）。

## A47 · 让 `_write_reward_sidecar` / `_read_reward_config_from_checkpoint` **彻底消失**（2026-10-08 ✓）

**动机** ✓：这两个名字住在 `utils/config.py`（"三入口共用层" ✓），但
*写* sidecar **只被训练侧**用到 ✓（评估入口那条 import 纯属多余 ✗）、*读* sidecar **只有评估准备段
一个调用点** ✓ ⇒ 摆在共用层里既容易误判"没人用"，也让评估详注版背一条死 import ✗。

**做法** ✓（既不重复代码、又让名字清零 ✓）：
- **写入器 ⇒ 并进 `save_multi_agent_checkpoint()`** ✓（它本来就在存 checkpoint ✓）：
  `CkptManager.save / save_best` 的「save + 写 sidecar」两行 ⇒ 改成**一行**调它 ✓；
  生成器注入的训练收尾 ⇒ 去掉单独调用的那行 ✓（**保留 `_ckpt_saved = …` 赋值** ✗ ——
  下一行 `log_console(f'CHECKPOINT={_ckpt_saved}')` 还要用它 ✓，第一次改漏了 ⇒ 冒烟 `NameError` ✓）。
- **读取器 ⇒ 内联进生成器的 `EVAL_SETUP_BLOCK`** ✓（它只有这一处调用 ✓；内联段自带
  `import json` / `from utils.config import REWARD_CONFIG_SIDECAR` ✓，不依赖入口的 import ✓）。
- `utils/config.detailed.py` 删掉两个 def ✓（含上方注释 ✓，共 **65 行** ✓）；源文件 import 去掉两名 ✓；
  生成器里**依赖旧文本的补丁**也一并清理 ✓：删掉 2 条失效的"措辞补丁"（#23 锚在已删注释上 ✓、
  #11 锚在"合并后 import"上而那条 import 已变 ✓）+ 改准 2 处文档/注释里的旧名字 ✓。

**结果** ✓：`utils/config.detailed` 618 → **553**（简版 292 → **251** ✓）、
`utils/train.detailed` 2367 → **2391**（写入器并入 ⇒ 净增 ✓，简版 2063 → **2087** ✓）、
`Multi-agent.py` 878 → **876** ✓、`eval.detailed` 960 → **980**（内联段 ✓，简版 212 → **236** ✓）。
**全仓已无**这两个名字的**代码**引用 ✓（残留的几处都是注释/文档里的历史说明 ✓）。

**验证** ✓：编译 / 导入 / `--check-reward` / 门禁 `--strict`（98 行共享代码逐行一致 ✓）/
**端到端 KPI `af7dd1ba…` + TRACE `8c9aac97…` 逐字节同基准** ✓（⇒ 内联读取器行为一致 ✓）/
**训练 1 轮冒烟 exit 0** ✓ 且 **checkpoint 目录里真的出现了 `reward_config.json`** ✓★
（= 合并后的写入器确实在写 ✓，内容与旧实现一致 ✓）/ `--help` 字节（12148 / 8704 ✓）。

## A48 · config 术语注释 → 新手白话（2026-10-08 ✓）

**为什么必须改这些行** ✓：`utils/config.py`（简版 ✓）里能看见的注释只有两类 —— **块外的引子行** ✓ 与
**代码行尾注释** ✓ —— 两者都**塞不进详注块** ✗ ⇒ 只能本身就白话 ✓；技术细节继续留在详注块 ✓。

**两批共 44 行** ✓（改 `utils/config.detailed.py` ✓，简版随之刷新 ✓）：

| 原术语 | 改成（简版可见 ✓） |
|---|---|
| `缺口罚权重` | 「罚多重：室温高出舒适区多少，就按这个倍数罚（1 个"缺口单位" = 110 分）」 ✓ |
| `过吹罚` / `over 罚` | 「吹过头也要罚：实际开度超过"刚够用的量"的那部分，按超出多少扣分」 ✓ |
| `a_need 的口径` | 「"这栋楼此刻刚够用的开度"怎么算：'load' = 按物理量逐步算 / 'const' = 老的一刀切常数」 ✓ |
| `(b)/(c) 带外基础权重` | 「[带内] / [带外]」+ 白话说明（标签本身也白话 ✓）|
| `刹车缓冲带` | 「余量 = 提前刹车的缓冲」 ✓ |
| `指标口径版本` | 「指标算法的版本号…两种算法数值量级不同（1e-7 vs 1e-2），混着比会出错」 ✓ |
| `全局 hinge / 成本率` | 「只在成本率超过目标线时才开始计分」 ✓ |
| `电池套利/择时` | 「电池"低价存、高价放"的力度（唯一旋钮）」 ✓ |
| `死区` / `敏感度` | 「彻底过冷（死区）」/「= 实测灵敏度」 ✓ |
| `sidecar` | 「随断点存档」 ✓ |

**定位手法** ✓：`line` 规则按**去掉缩进后的行首前缀**匹配、整行替换 ✓；`trail` 规则按 kwargs 名匹配、
**只换 `#` 之后的注释** ✓（代码半字不动 ✓）。**守卫** ✓：每条断言"恰好命中 1 处" ✓、改完 **AST 逐字不变** ✓。

**踩的坑（如实记 ✓）**：① 第一条规则漏了行首 `# ` ✗ ⇒ `ast.parse` 语法错 ⇒ **写盘前中止** ✓；
② `trail` 分支里多拼了一次 `# ` ✗ ⇒ 出现 `# # …` ✗ —— 而它**仍是合法注释** ⇒ AST 守卫**查不出** ✗，
是**人眼查输出**才发现的 ✓ ⇒ 已收敛为单 `#` ✓。
**教训** ✓：AST 守卫只保证"语义没变" ✗，**注释排版要另设检查** ✓（如"不得出现 `# #`"）。

**验证** ✓：编译 / 导入 / `--check-reward` / 门禁 `--strict` / 端到端 KPI `af7dd1ba…` + TRACE
`8c9aac97…` **逐字节同基准** ✓ / `--help` 字节（12148 / 8704 ✓）/ 训练 1 轮冒烟 exit 0、错误行 0 ✓；
指纹 `utils/config.py` **AST 一字未变**（`eb95c5f3…` ✓）= 纯注释改动 ✓。

## A49 · custom_comfort_reward 也出「两份」+ env/report/train 术语白话化（2026-10-08 ✓）

**① 自定义奖励模块纳入"详注版 + 简版"** ✓（`base.py` 不动 ✓，用户指定 ✓）
- 生成器新增 `ROOT_MODULES` / `SPLIT_TARGETS` ✓（第「3)」段现在遍历
  `[(utils/, …5 个…), (根目录, custom_comfort_reward.py)]` ✓，打印沿用同一套 ✓）。
- `custom_comfort_reward.py`（**1214 行 / 0 块** ✗）⇒ 两步详注化：
  ① **18 处 docstring → 逐行注释** ✓（模块 / 类 / 方法都算 ✓；`__doc__` 全仓无人读 ✓ 与
  `base/config/env/report` 同款处理 ✓）；② **35 段长注释**留首 1–2 行简略行 ✓、其余包块 ✓。
  ⇒ 详注版 **1282 行 / 41 块** ✓、简版 **981 行** ✓（删 304 行详注 ✓）。
- ⚠️ **模块名不变** ✓ ⇒ 三个入口那句 `__module__ == 'custom_comfort_reward'` 断言照旧成立 ✓；
  入口 `from custom_comfort_reward import …` 引的就是**简版** ✓。
- **硬证据** ✓：`--check-reward` ⇒ **温度项总体最大绝对差 = 0.000e+00** ✓✓（奖励逐位一致 ✓）。

**② 三个模块的"可见术语行"改成白话** ✓（共 **77 行** ✓：`env` 30 / `report` 7 / `train` 40 ✓，
含同一句在详注块里的重复出现 ✓）。改的是 `.detailed.py` ✓（简版随之刷新 ✓）。例：
- `把冷却维做重标定` → 「把制冷动作换算成"真实施加的开度"」 ✓
- `动作重标定**去 per-building 化**` → 「动作换算不再**按楼栋各用一套**」 ✓
- `applied = a_ref × 倍率` → 「**真实施加的开度** = a_ref × 倍率」 ✓
- `奖励口径 sidecar` → 「把奖励配置写进断点目录」（`sidecar` 这一外来词彻底去掉 ✓）
- `决策推演` 保留 ✓（已是白话 ✓），但 `落盘` → 「写盘 / 写文件」 ✓、`口径` → 「算法 / 计数 / 配置」 ✓。

**定位手法** ✓：按"去掉缩进后的**行首前缀**"匹配 ✓（默认允许 ≤3 处 ✓ —— 同一句常同时出现在
简版可见处与详注块里 ✓）；`trail` 规则只换 `#` 之后的注释 ✓（代码半字不动 ✓）；
**单行 → 单行** ⇒ 行号不位移 ✓，可对同一份文件连续放多条规则 ✓。

**踩的坑（如实记 ✓）**：① 守卫次序写反（对 `line` 规则也要求"不带 `#`" ✗）⇒ 断言在**写盘前**中止 ✓；
② 两条规则忘了改显式上限 ⇒ 也被断言拦下 ✓（**两次都没写坏文件** ✓）。
⇒ 教训 ✓：**"写盘前断言 + 全量 AST 比对"这套护住我两次** ✓，继续保留 ✓。

**验证** ✓：编译 / 导入（简版 + 详注版 ✓）/ `--check-reward`（0.000e+00 ✓）/ 门禁 `--strict` /
端到端 KPI `af7dd1ba…` + TRACE `8c9aac97…` **逐字节同基准** ✓ / `--help` 字节（12148 / 8704 ✓）/
训练 1 轮冒烟 exit 0、错误行 0 ✓。
指纹 ✓：**只有 `custom_comfort_reward.py` 变**（`8db50b6b…` → `cc63c99a…` ✓ 行数 1214 → **981** ✓，
原因 = docstring 变注释 ✓）；`env` / `report` / `train` / `base` / `config` / 两个入口 / `Multi-agent.py`
**AST 一字未变** ✓（= 纯注释改动 ✓）—— 已重存基线 ✓。

## A50 · 术语白话化收尾（三批 107 行）+ 备份清理（2026-10-08 ✓）

**① 白话化共 4 批、184 行** ✓（A48 的 config 44 行 + A49 的 77 行 + 本段 107 行 ✓）；
本段三批 ✓（改 `utils/{env,report,train,config}.detailed.py` ✓，简版随之刷新 ✓）：

| 批 | 行数 | 清掉的术语（→ 白话 ✓） |
|---|---|---|
| 二 | 63 | `口径`→算法/计数/配置 ✓、`探针`→试跑 ✓、`落盘`→写盘 · 写进文件 ✓、`标量`→一个数 · 数值 ✓、`hinge`→超过目标线才罚 ✓、`半带宽`→舒适带半宽 ✓、`δ²/δ³`→（偏离量）²/³ ✓、`per-building`→按楼栋各用一套 ✓、`回退`→改回 · 兜底 ✓、`快照`→存档 ✓、`决策推演`→补一句"把每步观测/动作/奖励写成一条记录" ✓ |
| 三 | 35 | `主读数 / 影子读数`→**主动读数 / 参考读数**（与 A49 的用法统一 ✓）、`幂等`→重复执行也没副作用 ✓、`归一化`→换算成 0~1 ✓、`sidecar`→（函数名保留 + 白话解释 ✓）、`落盘`→写盘 ✓ |
| 四 | 9 | `train` **顶部文档区**（简版也可见 ✓）的最后几处 ✓ |

**保留的词** ✓（已是白话 ✓，不再动 ✓）：`窗口`、`核实`、`别名`、`触发`、`兜底`、`试跑`、`断点`、`存档` ✓。
**唯一剩余命中** ✓：注释里出现的**函数名** `_write_reward_sidecar()` ✓（code 标识符 ✗ 不能改 ✓，
其后的括号里已用白话说明它干什么 ✓）。

**② 备份清理** ✓：`_tmp_bak*` **13 个 → 3 个** ✓（保留 `_tmp_bak39`（改 custom 前 ✓）、
`_tmp_bak40`（第一批白话前 ✓）、`_tmp_bak41`（②③④批改前 ✓））。
⚠️ 另有 `_tmp_userbase/`、`_tmp_userconfig/`（2026-10-07 你做那次手改时的副本 ✓）与
`_tmp_find_dead.py` 未动 ✓ —— 那是更早的东西，**要不要删你说** ✗。

**验证** ✓（四批都跑同一套 ✓）：编译 / 导入 / `--check-reward`（**0.000e+00** ✓）/
门禁 `--strict`（98 行共享代码逐行一致 ✓）/ 端到端 KPI `af7dd1ba…` + TRACE `8c9aac97…`
**逐字节同基准** ✓ / `--help` 字节（12148 / 8704 ✓）/ 训练 1 轮冒烟 exit 0、错误行 0 ✓。
指纹 ✓：`env` / `report` / `train` / `config` 的 **AST 全部一字未变** ✓（= 纯注释改动 ✓）。

## A51 · 澄清：`_write_reward_sidecar` / `_read_reward_config_from_checkpoint` 早已删除（2026-10-08 ✓）

**结论** ✓：这两个函数在 `utils/config.py` 里**已经不存在** ✓（A47 那次删除 ✓）。活文件里
**0 个 `def`、0 处 import、0 处调用** ✓；只剩**历史说明注释** ✓（已加"该函数**已删除** ✓"标注 ✓，
免得再被误读 ✗）。**功能没有丢** ✓ —— 已**内联**到使用点 ✓：

| 原函数 | 现在在哪（内联 ✓） | 活着的证据 ✓ |
|---|---|---|
| `_write_reward_sidecar()` | `utils/train.detailed.py` L729 / 简版 L651：`(_sp / REWARD_CONFIG_SIDECAR).write_text(...)` ✓ | 训练 1 轮（带断点）⇒ 断点目录里**真的出现** `reward_config.json` ✓（3 键：`reward_kwargs` / `saved_at` / `saved_by` ✓）、`Traceback`/`NameError` 各 0 行 ✓ |
| `_read_reward_config_from_checkpoint()` | `Multi-agent-eval.*` 步骤 1 的内联段（`_rc_f = next((d / REWARD_CONFIG_SIDECAR …` ✓；生成器里是 `_gen_marl_split.py` L426–438 ✓） | 端到端 eval 用 `reward_config.json` 读回奖励配置 ⇒ KPI `af7dd1ba…` + TRACE `8c9aac97…` **逐字节同基准** ✓ |
| 常量 `REWARD_CONFIG_SIDECAR` ✓ | **留在** `utils/config.*` ✓（上面两处内联都 import 它 ✓）—— 它才是"该留下的那份" ✓ |

**为什么你会觉得"还在"** ✗：那是**过期副本** ✗，不是活代码 ✓：
- `_simple_notes/`（`_strip_detail_notes.py` 的临时产物 ✓，里面有旧版 `Multi-agent.py` /
  `Multi-agent-train.py` —— 里面确实有 `from utils.config import _write_reward_sidecar` 与 4 处调用 ✓）
  ⇒ **已删** ✓；
- `_tmp_userconfig/config_user.py`（2026-10-07 你手改时的副本 ✓）⇒ 里面还留着这两个 `def` ✗
  ⇒ **待你点头再删** ✓；`_tmp_bak39/gen_before_root_modules.py`（备份 ✓）同理 ✓；
- `output/outkpis/<hash>/` 下那些**旧运行快照** ✓（历史 checkpoint 副本 ✓，不是源码 ✓）；
- 或者 IDE 里未重新加载的旧缓冲区 ✓ ⇒ 建议"Reload from Disk" ✓。

**本轮改动** ✓：只给 3 处历史注释加了"已删除"标注 ✓（`_gen_marl_split.py` ×2 ✓、
`utils/train.detailed.py` ×1 ✓）⇒ 生成物里也带上 ✓。**验证** ✓：编译 / `--check-reward`
（0.000e+00 ✓）/ 门禁 / 端到端**逐字节同基准** ✓ / `--help` 字节（12148 / 8704 ✓）；
指纹只有 `_gen_marl_split.py` 变（`9929f628…` → `63abf730…` ✓ = 字符串说明改动 ✓），
其余 9 项**一字未变** ✓（已重存基线 ✓）。

## A52 · CHESCA.py 也出「详注版 + 简版」（2026-10-08 ✓）

**背景** ✓：`CHESCA.py`（`citylearnpy/` ✓，1225 行 / **0 块** ✗）对标 `Multi-agent-eval/train` ✓
——它**既是脚本**（`python CHESCA.py …` ✓）**又是被 import 的模块** ✓
（`train_chesca_resmarl.py` / `CHESCA_ResMARL.py` / `tests/test_residual_phase0.py` /
`ablation_resmarl.py` 都 `from CHESCA import …` ✓）⇒ 拆分**不改模块名** ⇒ 调用方零改动 ✓。

**做法** ✓（`_tmp_detail_chesca.py`，四步 + 三重守卫 ✓）：
① **20 处 docstring → 逐行注释** ✓（长块留首 1–2 行简略行 ✓，其余包块 ✓）；
② **8 段长注释**同样包块 ✓；③ 给 **31 个 def/class 各配一行白话说明** ✓（缺的插入 ✓、
原有的粗糙说明替换 ✓）；④ **14 处术语 → 白话** ✓（`残差`→「RL 修正」✓、`掩码`→「修正哪几维动作的开关」✓ 等 ✓）。
⇒ 详注版 **1242 行 / 21 块** ✓；简版 **1108 行** ✓（藏起 137 行详注 ✓）。
生成器里 `ROOT_MODULES = ('custom_comfort_reward.py', 'CHESCA.py')` ✓。

**踩的坑（如实记 ✓）**：步骤 ③ 若某个 `def` 上方紧邻的是**详注块的 END** ✗，我原来会把 END
**覆盖成说明** ✗ ⇒ 块失衡、吞掉代码 ✗ —— **被生成器的 `guard_only_comments` 当场拦下** ✓
（它报"详注块内混入非注释内容" ✓，一个字没写 ✓）。已改成"插到整块上方" ✓ 并加断言 ✓。

**验证** ✓（最硬的一条在 ②）：
| 检查 | 结果 |
|---|---|
| 编译 / `from CHESCA import WrapperEnv, DEFAULT_SCHEMA, load_agent_config, evaluate, DEFAULT_OUTPUT_DIR` | exit 0 ✓ / OK ✓ |
| **短程仿真对照**（48 步 `--no-render` ✓，**注释前的原版** vs **现在的简版** 各跑一次 ✓） | 两次 `exported_kpis.csv` sha256 **都是 `a9e7b2bb3fe39b67`** ✓✓（逐字节一致 ✓）；产出文件集相同 ✓（含 `chesca_trace.csv` / `chesca_agent_config.json` ✓）|
| 详注版 vs 简版 **AST** | **逐字相同** ✓（生成器守卫 + 独立复核 ✓）|
| `CHESCA.py --help` / `CHESCA_ResMARL.py --help` | 与原版**逐行 diff 为空** ✓（⚠️ 字节数会因 argparse 换行宽度浮动 ±百字节 ✗，**别用字节数判等价** ✗，要用 diff ✓）|

⚠️ **`CHESCA.py` 暂不在 AST 指纹名单里** ✗（名单只有 `Multi-agent*` / `utils/*` /
`custom_comfort_reward.py` ✓）⇒ 要不要把它加进去，你说 ✓。

## A53 · CHESCA 配置改走「代码编辑器页 + Java 传 CLI」（2026-10-08 ✓）

**对标机制** ✓（查证自 Java 侧 ✓）：Multi-agent 系列的配置 = 代码编辑器页「配置」弹窗把参数挂到
脚本上（存 `py_file.algorithm_config` ✓），执行时 Java 按**每脚本白名单**翻成
`param_name → --param_name value`（`BaseDataService#resolveAlgorithmConfigArgs` ✓）✓。
而 CHESCA 原先走「CHESCA-ResMARL 配置」页 → Java 写 `chesca_agent_config.json` →
`--min-soc-config` 传路径 ✓，且 Java 白名单**故意没登记** `chesca.py` ✗（旧注释的理由是
"硬当 CLI 传会 unrecognized" ✓）。本轮把它改成与 MARL 同一套 ✓。

**Python 侧（`CHESCA.detailed.py` ✓，改动全在此 ✓）**：
1. 新增 `AGENT_CONFIG_CLI_KEYS`（**56 个字段名** ✓ = `chesca_agent_config.json` 的键 ✓ =
   `db/algorithm_param_config_chesca_*.sql` 登记的 `param_name` ✓）+ `DEFAULT_MIN_SOC_PER_HOUR`
   （无 JSON 时的默认 SOC 表 ✓，与 Java 侧默认值同一组 ✓）。
2. `parse_args` 按表登记 `--字段名` ✓ **并自动补中划线别名** ✓（`--B_low` 与 `--b-low` 都认 ✓）；
   已有同名选项的 **7 个**（`--eval-schema` / `--marl-mode` / `--residual-*` / `--multi-agent-*` ✓）
   **不重复登记** ✗（否则 argparse 报 conflicting option string ✓），改为给旧选项**补下划线别名** ✓。
3. `_read_agent_config_raw()` 抽出"读文件"段 ✓；
   `load_agent_config(config_path, cli_overrides=None)` = 读 raw → **命令行并进 raw** →
   **原来的归一化逻辑一字不动** ✓ ⇒ 取值优先级 = **命令行 > 配置 JSON > 内置默认** ✓，
   且**校验口径只有一份** ✓（命令行值走同一套 `_parse_*` ✓，不用重抄 `max_value` 等 ✓）。
4. `_cli_overrides_from_args()`（只有显式传了的项才进 ✓；`min_soc_per_hour` 解 JSON 成 dict ✓）；
   `__main__` 改为 `load_agent_config(args.min_soc_config, _cli_overrides_from_args(args))` ✓。
   ⚠️ 老调用方 `load_agent_config(path)`（`CHESCA_ResMARL.py` / `ablation_resmarl.py` /
   `tests/test_residual_phase0.py` ✓）行为**一字不变** ✓。

**Java 侧（`BaseDataService.java` ✓）**：白名单新增 `map.put("chesca.py", chescaCommon)` ✓
（**59 个名字** ✓：含 `B_low/b_low`、`B_high/b_high`、`TMP_*/tmp_*` **两种大小写** ✓，因为历史配置里两种
都出现过 ✓）；同时把"没登记的脚本（CHESCA…）一律不传"那段**过期注释**改成现状 ✓。
⚠️ `CHESCA_ResMARL.py` **仍不登记** ✓（它只认自己 10 个参数 ✓，硬传会崩 ✗）。
⚠️ **需重新编译 / 重启后端**才生效 ✓。

**Python 侧验证（三重 ✓，48 步 `--no-render`）**：
| 场景 | `exported_kpis.csv` sha256 | 结论 |
|---|---|---|
| 不带任何新参数 | **`a9e7b2bb3fe39b67`** ✓ | 与注释前原版**逐字节一致** ⇒ **零回归** ✓ |
| `--tau 2 --B_low 1.3` | `fbe874e5a5d8e951` ✓ | **变了** ⇒ 参数真进了算法 ✓ |
| `--max_soc_normal 0.95 --B-low 1.25 --price-high-quantile 0.8`（混用拼写 ✓） | `a5d0566e9b11f9df` ✓ | 两种拼写都被接受 ✓ |
| 三份日志 | `Traceback` / `unrecognized arguments` / `error:` **各 0 行** ✓ | ✓ |

规模 ✓：`CHESCA.detailed.py` **1416** 行 / 26 块 ✓、`CHESCA.py`（程序 import 它 ✓）**1253** 行 ✓。

## A54 · CHESCA 的 CLI 参数名**统一下划线**（去掉别名机制，2026-10-08 ✓）

**动机** ✓：A53 那版为兼容保留了一套"双名"机制 ✗ —— `AGENT_CONFIG_CLI_EXISTING` 字典
（把 7 个已有中划线选项映射到自己的 dest ✓）+ 自动补中划线别名 ✓。用户判定其**不该存在** ✗
⇒ 参数名统一采用**下划线版** ✓（= 平台参数目录的 `param_name` ✓ = Java 翻出来的名字 ✓）
⇒ **Java 发来即正确，脚本侧不需要任何别名** ✓。

**改法** ✓（全在 `CHESCA.detailed.py` ✓）：
- **删** `AGENT_CONFIG_CLI_EXISTING` 字典 ✗ 与循环里的跳过分支 ✗；
- **删** 7 个手写的中划线选项块 ✗（`--marl-mode` / `--residual-alpha` / `--multi-agent-checkpoint` /
  `--resmarl-after-safety` / `--residual-action-mask` / `--multi-agent-explore` / `--eval-schema` ✓，
  共 **43 行** ✓）⇒ 全部改由同一循环登记 `--字段名` ✓，**`dest` 自动 = 字段名** ✓
  ⇒ `args.marl_mode` / `args.eval_schema` / `args.residual_alpha` 等**老消费点照旧可用** ✓；
- `AGENT_CONFIG_CLI_KEYS` 补上漏掉的 `marl_mode` ✓（现 **57 个** ✓）；
- 新增 `AGENT_CONFIG_CLI_HELP` ✓（给那 7 个键保留原来的说明文字 ✓，其余走默认说明 ✓）；
- `_cli_overrides_from_args` 统一为 `getattr(args, 字段名)` ✓；
- 注释 / 帮助里残留的 `--marl-mode` 等写法一并改成下划线 ✓。

**Java 侧** ✓：白名单补 `marl_mode` ✓；"副带中划线别名"的说法改准 ✓。

**验证** ✓（`--no-render` ✓）：
| 场景 | 结果 |
|---|---|
| 无参数（48 步） | `a9e7b2bb3fe39b67` ✓ = 原版基准 ⇒ **零回归** ✓ |
| `--tau 2 --B_low 1.3`（48 步） | `fbe874e5a5d8e951` ✓ ⇒ 参数真进算法 ✓ |
| `--eval_schema` + `--marl_mode none` + `--residual_action_mask` + `--max_soc_normal`（8 步） | exit 0 ✓ ⇒ **框架键也统一** ✓ |
| **旧中划线** `--eval-schema`（8 步） | **exit 2** ✓（argparse 拒绝 ✓ = 统一生效 ✓）|
| `--help` | exit 0 ✓ |
> 规模 ✓：`CHESCA.detailed.py` 1368 行 ✓、简版 `CHESCA.py` 1204 行 ✓。
> ⚠️ **迁移提醒** ✓：谁若手敲过 `--marl-mode` / `--eval-schema` 等旧写法 ✗，请改用下划线 ✓
> （已全仓扫过：**没有任何脚本给 CHESCA.py 传 CLI** ✓，Java 只硬编码 `--output-dir` /
> `--min-soc-config` 两个框架参数 ✓ ⇒ 无破坏 ✓）。

## A55 · CHESCA 参数改为**逐条显式声明**且**只从命令行来**（2026-10-08 ✓）

**用户判定** ✓：A53/A54 那版 `parse_args` **很怪异** ✗（用 `AGENT_CONFIG_CLI_KEYS` + 循环生成 ✗），
而且 CHESCA **不该**再去读 Java 写下的 `chesca_agent_config.json` ✗。要的是：
**形式与 `Multi-agent-eval/train` 一致** ✓（每条参数一条 `parser.add_argument(...)` ✓）、
CHESCA 有**自己的**一套参数 ✓、Java **直接把参数写在命令行**传进来 ✓。
（"形式一致"≠"参数名一致" ✓ —— CHESCA 的参数名仍是它自己的下划线写法 ✓。）

**改法** ✓（全在 `CHESCA.detailed.py` ✓）：
1. **删掉两张表** ✗（`AGENT_CONFIG_CLI_KEYS` / `AGENT_CONFIG_CLI_HELP` ✓）与循环 ✗；
2. `parse_args` 里**逐条显式声明 60 个参数** ✓ —— 与 eval/train 同款写法 ✓，
   并且带上了**类型**（`float` / `int` / `str` ✓，bool 类传 `'true'`/`'false'` ✓）
   与**逐条中文说明** ✓（说明取自 Java 侧默认值 / 参数目录的描述 ✓）；
3. **不再读配置文件** ✗：`__main__` 改为 `load_agent_config(None, _cli_overrides_from_args(args))` ✓；
   `--min-soc-config` **保留但忽略** ✓（旧调用方不会因 unrecognized 崩掉 ✗，且会打印一行提示 ✓）；
4. `_cli_overrides_from_args` 改成**遍历 `vars(args)`** ✓（跳过 `_FRAMEWORK_DESTS` 里的 5 个框架参数 ✓，
   `min_soc_per_hour` 解 JSON 成 dict ✓）⇒ 不再需要任何名单表 ✓；
5. `load_agent_config(config_path, cli_overrides=None)` **原样保留** ✓
   —— `CHESCA_ResMARL.py` / `ablation_resmarl.py` / `tests/test_residual_phase0.py` 仍按老方式用它 ✓
   （只有纯 CHESCA 入口不再传路径 ✓）。

**Java 侧** ✓：纯 `CHESCA.py` **不再传** `--min-soc-config` ✗（JSON 快照仍写 ✓，仅供任务详情页查看 ✓）；
`CHESCA_ResMARL.py` **保持**写 JSON + 传路径 ✓。⚠️ 需重新编译 / 重启后端 ✓。

**验证** ✓（48 步 `--no-render` ✓）：
| 场景 | 结果 |
|---|---|
| 无参数 | `a9e7b2bb3fe39b67` ✓ = 原版基准 ⇒ **零回归** ✓ |
| `--tau 2 --B_low 1.3` | `fbe874e5a5d8e951` ✓ ⇒ 命令行生效 ✓ |
| 传旧 `--min-soc-config <json>` | **与"无参数"完全相同** ✓✓ ⇒ **文件确实不再被读** ✓ |
| `--min_soc_per_hour '<24 小时 JSON>'` | exit 0 ✓ ⇒ 字典型参数也能走命令行 ✓ |
| 旧中划线写法 `--eval-schema` | exit 2 ✓ |
| `--help` | exit 0 ✓、**65 条**可传值选项（60 配置 + 5 框架 ✓）|

> 规模 ✓：`CHESCA.detailed.py` **1658** 行 / 24 块 ✓、简版 `CHESCA.py` **1509** 行 ✓。
> ⚠️ **平台侧要配的两件事** ✓：① 参数目录里把 CHESCA 需要的参数**挂到 `CHESCA.py`** 上
> （代码编辑器「配置」弹窗 ✓）；② **24 小时 SOC 表**（`min_soc_per_hour` ✓）在平台上是**对象型** ✗
> ⇒ Java 会跳过不传 ✓，若要改它请用**文本型**参数传 JSON 字符串 ✓（脚本已支持 ✓）；
> 不改就用脚本内置默认表 ✓（= Java 侧那组默认值 ✓ 逐值相同 ✓）。

## A56 · 删掉 CHESCA 的步数硬编码表 + 4 个无用参数（2026-10-08 ✓）

**判定依据** ✓（先测后改 ✓）：
- `SCHEMA_DEFAULT_EPISODE_STEPS`（23 条 ✓）里 **22 条**与数据集自己的
  `simulation_end_time_step + 1` **逐条相等** ✓（只剩 `warm_up` 在 v2.5.0 缓存里不存在 ✓）
  ⇒ **纯冗余** ✗；而且**未登记的 schema 会被静默按 720 跑** ✗（截断回合 ✓）。
- 这与 `utils/env.py` 早就写明的约定**相反** ✗：
  「⚠️ `episode_time_steps=None` 是**有语义的**：不传 ⇒ 交给 CityLearn 用数据集自带长度
  （源码 `citylearn.py:910`）⇒ 未登记的 schema 不会被静默按硬编码值跑 ✗」✓✓

**改法** ✓（全在 `CHESCA.detailed.py` ✓）：
1. **删表**（26 行 ✓）与查表函数 `_default_episode_steps_for_schema` ✓；
2. `resolve_schema_plan`：没给步数 ⇒ 返回 **None** ✓（= "交给数据集自己定" ✓），日志里显示"数据集自带" ✓；
3. `create_citylearn_env`：`steps is None` ⇒ **不传** `episode_time_steps` ✓（与 eval/train 同约定 ✓）；
4. ⚠️ 需要**整数**的下游（`total_steps` / `agent_config` ✓）⇒ 在**建好环境之后**从
   `wrapper_env.time_steps` **读回真实值** ✓（与 `utils/env.py` 探针读回同一做法 ✓）；
   未指定时也**不再**往 agent 配置里塞 `None` ✓；
5. 删掉 **4 个"代码里从未被读取"**的参数 ✗：`resmarl_eval_schema` / `schema_split_enabled` /
   `train_schema` / `multi_agent_eval_schema`（那是我 A55 之前"为完整"加的 MARL 遗留 ✗）✓；
   Java 白名单**同步删** ✓。

**验证** ✓（用**环境级**证明 + 快速冒烟，避开"720 步跑十分钟" ✗）：
| 检查 | 结果 |
|---|---|
| 旧表值 vs 新版"交给数据集"**建环境后读回** | `local_evaluation` **720 = 720** ✓；`online_evaluation_1` **2208 = 2208** ✓✓ |
| 新版 48 步冒烟 | `a9e7b2bb3fe39b67` ✓ = 原版基准 ⇒ **零回归** ✓ |
| 4 个已删参数 | `--train_schema` ⇒ **exit 2** ✓ |
| `--help` | exit 0 ✓、可传值选项 **61 条**（56 配置 + 5 框架 ✓）|
| **两侧名字一致性** ✓ | Python 参数 **56 个** == Java 白名单 **56 个** ✓，**两个方向零差异** ✓✓ |

> 规模 ✓：`CHESCA.detailed.py` **1624** 行 / 27 块 ✓、简版 `CHESCA.py` **1459** 行 ✓。
> ⚠️ Java 改了 ⇒ **需重新编译 / 重启后端** ✓。

## A57 · 配置层抽到 `utils/ches_config.py`（引用 utils + 2 行参数 + 默认值下沉，2026-10-08 ✓）

**用户要求** ✓（四条）：① 该引用 utils 的就引用 ✓；② `parser.add_argument` 与 eval/train
**同款 2 行写法** ✓；③ 像 `_parse_threshold` 这类"检查数值合理"的方法**抽到 utils** ✓；
④ `load_agent_config` 对纯 CHESCA **不再需要**（参数全从命令行 ✓）；要默认值就把默认值也放 utils ✓。

**做法** ✓：
- **新建 `utils/ches_config.py`**（530 行 ✓）＝ CHESCA 的"配置层" ✓：
  · `DEFAULTS`（**52 键默认值** ✓）—— 由**旧版实跑**导出 ✓（跑 `load_agent_config(None, {…})` ✓
    再 `repr` 出来 ✓，**不手抄** ✗，因此零转写风险 ✓）；
  · **10 个校验器原样搬** ✓（`_parse_min_soc_map` / `_parse_soc_limit` / `_parse_threshold` /
    `_parse_nonneg_float` / `_parse_tau` / `_parse_balance_type` / `_parse_bool` /
    `_parse_residual_alpha` / `_parse_residual_mask` / `_parse_marl_mode` ✓ —— 按 AST 行号**整段切** ✓）；
  · `_read_agent_config_raw` / `load_agent_config` / `apply_resmarl_cli_overrides` ✓（整段搬 ✓）；
  · 新增 `build_agent_config(cli_overrides)` ✓ = `load_agent_config(None, cli_overrides)` ✓
    （纯 CHESCA 只走命令行 ✓，**校验口径仍只有一份** ✓）。
- `CHESCA.detailed.py` ✓：删掉搬走的 14 段（**699 行** ✓）⇒ **1624 → 925 行** ✓；
  顶部加 `from utils.ches_config import …` ✓（**放在两行 `sys.path.insert` 之后** ✓，否则 import 不到 ✗）；
  `load_agent_config` / `apply_resmarl_cli_overrides` 借这次 import **re-export** ✓
  ⇒ 老调用方 `from CHESCA import …` **不破** ✓（实测 ✓）。
- `parse_args` ✓：**61 条全部 2 行写法** ✓（56 配置 + 5 框架 ✓），配置项默认值取自
  `DEFAULTS.get('名字')` ✓ ⇒ 默认值**只写在 utils 一处** ✓（与 eval/train 从 `utils/config.py` 取默认 ✓ 同款 ✓）。
- 生成器 `UTILS_MODULES` 纳入 `ches_config.py` ✓ ⇒ 它也有详注版 + 简版 ✓
  （**530 / 497 行** ✓）。

**验证** ✓（最关键的是第 ① 条 ✓）：
| 检查 | 结果 |
|---|---|
| ① 旧/新 `load_agent_config(样本 JSON)` | **52 键 逐键相同** ✓✓（等价性证明 ✓，无需跑仿真 ✓）|
| ② 新版 48 步 CLI 冒烟 | `a9e7b2bb3fe39b67` ✓ = 原版基准 ⇒ **零回归** ✓ |
| ③ re-export | `load_agent_config` / `apply_resmarl_cli_overrides` / `build_agent_config` / `DEFAULTS` 均可 `from CHESCA import` ✓；`CHESCA_ResMARL.py --help` exit 0 ✓ |
| ④ 两侧名字 | Python **56** == Java 白名单 **56** ✓（零差异 ✓）|
| ⑤ `utils/ches_config.py` 独立可用 | 只 import 它也能拿到 52 个默认值 ✓（不拉起仿真栈 ✓）|

> 规模 ✓：`CHESCA.detailed.py` **925** 行 / 23 块 ✓、简版 `CHESCA.py` **785** 行 ✓
> （上一轮分别是 1624 / 1509 ⇒ 砍掉约一半 ✓）。
> 踩坑记录 ✓：两次崩都**在写盘前**被断言/异常拦住 ✓（一次是把**字符偏移**当**行号**用 ✗、
> 一次是"倒序 `del` 在范围重叠时级联错位" ✗）⇒ 已改成**AST 行号 + 行号集合删除** ✓。

## A58 · CHESCA 的 trace 落盘抽成 `utils/ches_trace.py`（与 eval 同形式，2026-10-08 ✓）

**动机** ✓：`save_chesca_trace_csv()` 长在 `CHESCA.py` 的仿真主循环旁 ✗，
而 eval 侧早就把它做成了"**记录器 + `save()`**"的独立工具 ✓（`utils/report.py` 的
`MarlDecisionTraceRecorder` ✓ + `build_decision_recorder()` ✓ + `decision_trace_path()` ✓）
⇒ 两边**形式统一** ✓、CHESCA 主循环里只留一行 `save` ✓。

**形式对照** ✓（新模块 `utils/ches_trace.py` ✓，117 / 93 行 ✓）：

| CHESCA 这套 ✓ | 对标 Multi-agent ✓ |
|---|---|
| `build_chesca_trace_recorder(n_buildings)` | `build_decision_recorder(env, *, enabled)` |
| `ChescaTraceWriter(recorder, output_dir).save(env=None)` | `MarlDecisionTraceRecorder.save(path)` |
| `chesca_trace_path()` / `chesca_decision_trace_path()` | `decision_trace_path(env, output_dir)` |

**做法** ✓（**零重写** ✓）：原函数体**按 AST 整段搬**进工具模块（34 行 ✓，只把 5 处 `log_console(`
换成模块内 `_log(` ✓）；CHESCA 侧删掉该函数（38 行 ✓）⇒ **906 → 873 行** ✓，调用点变成
`trace_writer.save(env=env)` ✓；记录器改用工厂建 ✓（顺手建好 writer ✓，与 eval"先建记录器、后 save"一致 ✓）。
⚠️ **不动 `CHESCA-copy/checa/trace_exporter.py`** ✓：它**被两个测试直接 import**
（`tests/test_residual_phase1.py` / `test_residual_phase3.py` ✓，连 `_build_step_phases` 这类内部函数都用 ✓）
⇒ 留在原地、由新工具**包一层**最稳 ✓。产出文件仍是 `chesca_trace.csv` + `decision_trace.json` ✓
（Java 任务详情页与测试都读它们 ✓ ⇒ 格式一个字节都不能变 ✓）。

**工具可独立 import** ✓：模块自带上行引导（把 `citylearnpy` 与 `CHESCA-copy` 补进 `sys.path` ✓）
⇒ 单测 / REPL 里直接 `from utils.ches_trace import …` 就能用 ✓（实测 ✓）。

**验证** ✓（**改前 / 改后各跑 48 步** ✓，比三个产物 ✓）：
| 产物 | 改前 | 改后 | |
|---|---|---|---|
| `exported_kpis.csv` | `a9e7b2bb3fe39b67` | `a9e7b2bb3fe39b67` | ✓ |
| `chesca_trace.csv` | `038a31a8ea73e26d` | `038a31a8ea73e26d` | ✓ |
| `decision_trace.json` | `6d525049bda3b5d3` | `6d525049bda3b5d3` | ✓ |
⇒ **三个产物逐字节一致** ✓✓（抽取零改动 ✓）；`CHESCA.py --help` / `CHESCA_ResMARL.py --help` exit 0 ✓。

**踩坑记录** ✓：插入新行时**漏了缩进** ✗ ⇒ `IndentationError` ⇒ 因**写盘前已有备份**
（`_tmp_bak48/` ✓）当场还原重做 ✓（已补断言"原行必须是 4 空格缩进" ✓）。

> 规模 ✓：`CHESCA.detailed.py` **873** 行 / 22 块 ✓、简版 `CHESCA.py` **742** 行 ✓
> （最初 1225 行 ⇒ 已经砍掉 483 行 ✓）。

## A59 · CHESCA 抽环境工具 + 复用日志/KPI/编码 + 清死代码（2026-10-08 ✓）

**① 抽 `WrapperEnv` + `create_citylearn_env` → 新工具 `utils/ches_env.py`** ✓（119 / 90 行 ✓）
- 连同 3 个默认常量（`DEFAULT_SCHEMA` / `DEFAULT_OUTPUT_DIR` / `DEFAULT_RENDER_SESSION` ✓）
  一起搬去 ✓ ⇒ **唯一来源** ✓；CHESCA.py 改为 `from utils.ches_env import …` **再导出** ✓。
- **为什么没有复用它处的构建方法** ✗：`utils/env.py` 那套是 **Multi-agent / Ray 侧**的
  （`build_env_config` 造的是 RLlibMultiAgentEnv 的 env_config ✓）⇒ 拉进纯 CHESCA 会把
  Ray/RLlib 依赖带进来 ✗；而 `local_evaluation.py` 里是**另一份副本** ✗（不是工具 ✗）
  ⇒ 所以新开一个**轻量**模块（只 import citylearn ✓）。
- 兼容 ✓：`train_chesca_resmarl.py` 的 `from CHESCA import WrapperEnv, DEFAULT_SCHEMA` 照旧可用 ✓
  （实测 `WrapperEnv.__module__ == 'utils.ches_env'` ✓）。

**② 复用 `utils.base`**：`log_console`（逐字相同 ✓）+ **统一控制台编码 / 忽略警告** ✓
（原 CHESCA 自己那段 9 行删掉 ✓ —— `utils.base` 那份连 `errors='replace'` 都一致 ✓）。
⚠️ 副作用：`utils.base` 在导入时还会 `filterwarnings(DeprecationWarning)` ✓（比原先多忽略一类 ✗
但只影响 stderr ✓，产物逐字节不变 ✓，实测 ✓）；模块本身只依赖标准库 + pandas ✓（**不拖 torch/ray** ✓）。
**③ 复用 `utils.report.print_kpis_for_java`** ✓（与三个 MARL 入口**共用同一份** ✓，逐字相同 ✓）。
**④ 删 `_resolve_marl_mode`** ✓：它有个**从未使用**的 `agent_config` 入参 ✓ ⇒ 逻辑就地内联成
一行 `_parse_marl_mode(cli) if cli is not None else 'none'` ✓。
**⑤ `resolve_schema_plan` 删掉没用到的 `marl_mode` 入参** ✓（原为兼容占位 `_ = marl_mode` ✓）+ 2 处调用点 ✓。
**⑥ 删死引用** ✓：`import os` / `import warnings`（随编码块失效 ✓）、`import pandas as pd`
（清完本地 KPI 打印后全文 `pd.` 0 次 ✓ —— 断言先验 ✓ 再删 ✓）、新工具里我模板多带的 `Optional/Tuple` ✓。
**保留** ✓：`load_agent_config` / `apply_resmarl_cli_overrides` ✓ —— 本文件内确实不再用 ✗，
但**外部 4 个文件** `from CHESCA import …`（`CHESCA_ResMARL.py` / `20260914153739.py` /
`ablation_resmarl.py` / `tests/test_residual_phase0.py` ✓）⇒ 必须留作**再导出** ✓。

**⚠️ 未做（需你拍板 ✗）**：ResMARL 分支（`marl_mode` / `resmarl_enabled` / 残差合成 /
`setup_chesca_multi_agent_residual` ✓）。本文件虽名为"纯 CHESCA 入口" ✓，但**它的 `evaluate()`
就是 CHESCA-ResMARL 的评估内核** ✓（`CHESCA_ResMARL.py` 以 `--marl_mode multi_agent` 调它 ✓，
见文件头【CHESCA-ResMARL】段 ✓）⇒ 直接删会把那个入口打断 ✗。

**过程记录** ✓（三次都被"写盘前断言"拦下 ✓，文件没写坏 ✓）：① `find_def` 只认函数、没认类 ✗；
② 删函数用**旧行号**（前一次删除已让行号位移 ✗ —— A57 同款坑 ✓）⇒ 改成每次重新解析 ✓；
③ `import pandas as pd` 行**带行尾注释** ✗ ⇒ 按"注释前部分"匹配 ✓。

**验证** ✓（48 步实跑 ✓）：
| 产物 | 基准 | 现测 | |
|---|---|---|---|
| `exported_kpis.csv` | `a9e7b2bb3fe39b67` | `a9e7b2bb3fe39b67` | ✓ |
| `chesca_trace.csv` | `038a31a8ea73e26d` | `038a31a8ea73e26d` | ✓ |
| `decision_trace.json` | `6d525049bda3b5d3` | `6d525049bda3b5d3` | ✓ |
⇒ **逐字节一致** ✓✓；兼容矩阵 `MISSING: none` ✓（7 个名字全在 ✓）；两个入口 `--help` exit 0 ✓；
门禁 `--strict` exit 0（98 行共享代码逐行一致 ✓）；死引用复查：`os.` / `warnings.` /
`_resolve_marl_mode` / 本地四个定义 **全 0 次** ✓。

**规模** ✓：`CHESCA.detailed.py` **873 → 752** 行 ✓、简版 **742 → 643** 行 ✓
（最初 1225 行 ⇒ 已砍 **582** 行 ✓）；新增 `utils/ches_env.py`（90 / 119 行 ✓）。

## A60 · 残差层搬进 `utils/ches_residual.py`（方案 B：CHESCA 只留入口开关，2026-10-08 ✓）

**按你选的方案** ✓：CHESCA.py 里删掉 ResMARL 的**全部细节** ✓（残差参数 if/else ✓、SAC 挂载 ✓、
旁路环境同步 ✓、内嵌 `_bind_multi_obs()` ✓），只留 **8 处 `residual.*` 调用** ✓：

| 原 CHESCA 里的东西 ✓ | 现在 ✓ |
|---|---|
| `use_marl_residual = marl_mode == 'multi_agent'` + checkpoint 校验（8 行 ✓） | `residual = build_residual_layer(agent_config, marl_mode)` ✓（校验搬进构造器 ✓，报错**时机不变** ✓） |
| 残差参数 if/else 两块（12 行 ✓） | `residual.apply_agent_params(agent_params)` ✓ |
| `setup_chesca_multi_agent_residual(...)`（10 行 ✓） | `residual.attach(agent, config, schema_plan)` ✓ |
| `_bind_multi_obs()` 定义 + 3 处调用 ✓ | `residual.bind()` ×3 ✓（定义进工具 ✓） |
| `if multi_env is not None: multi_observations = sync_multi_env_step(...)` ✓ | `residual.sync(actions)` ✓ |
| `multi_env.reset()`（开局 + 多局 ✓） | `residual.reset()` ✓ |

**顺带一个实实在在的收益** ✓：`multi_agent_runner_copy`（拖 Ray / RLlib / torch ✗）在 CHESCA 顶部
**不再 import** ✓ ⇒ 由残差层**真启用时**才懒加载 ✓。可观测证据 ✓：ResMARL 同一场景的控制台从
**380 行降到 190 行** ✓（少掉的正是 Ray 导入期的空行与横幅 ✓）。
**保留** ✓：CLI 参数名 `--resmarl_enabled` / `--residual_alpha` 等（5 处 ✓）与那条提示文案 ✓
—— 它们是**入口开关的名字** ✓，不是实现 ✓。

**验证** ✓：
1. **纯 CHESCA 48 步 ⇒ 三产物逐字节同基准** ✓（`a9e7b2bb…` / `038a31a8…` / `6d525049…` ✓）；
2. **ResMARL 接线指纹** ✓：同一个 checkpoint 跑 1 步 ✓，把"Traceback 之前"的日志逐行比对 ✓ ⇒
   **21 个关键标记全部一致** ✓（`CHESCA-ResMARL 评估入口` ✓、`已加载 tau=` ✓、
   `已加载 CHESCA-ResMARL residual_alpha=` ✓、`CHESCA-ResMARL schema：` ✓、
   `已加载预存 Multi-Agent SAC` ✓、`CHESCA-ResMARL 已启用` ✓ …）；两者都在**同一处**以**同一个**
   `RuntimeError: mat1 and mat2 shapes cannot be multiplied (1x32 and 40x256)` 结束 ✓
   （= 该 checkpoint 与残差状态维度不匹配 ✓，**改动前就存在** ✓）；唯三差异 = 输出目录名（测试目录 ✓）、
   时间戳、traceback 行号（文件变短 ✓）。
   ⚠️ **如实记**：本仓库**没有**可用的 ResMARL checkpoint ✗（45 个候选里试了 6 个：要么维度对不上 ✓、
   要么 checkpoint 里引用了不存在的模块 ✗）⇒ **完整 48 步 ResMARL 实跑没做成** ✗；
   要补这一项，请给一个能跑通的 `multi_agent_checkpoint`（+ 配套配置 ✓）✓。
3. `CHESCA.py` / `CHESCA_ResMARL.py` / `20260914153739.py` `--help` 全 exit 0 ✓；
   兼容矩阵 `MISSING: none` ✓（7 个再导出名字全在 ✓）；门禁 `--strict` exit 0 ✓。

**你的另外两项** ✓：q-1 ⇒ 删 `_tmp_userbase/` ✓（`_tmp_userconfig/`、`_tmp_find_dead.py` 按你的选择保留 ✓）；
q-2 ⇒ `_q_ast_fingerprint.py` 的 `DEFAULT_FILES` 纳入 **6 个 CHESCA 系文件** ✓
（`CHESCA.py` / `CHESCA.detailed.py` / `utils/ches_{config,env,residual,trace}.py` ✓），已存新基线 ✓
且 `check` 全 OK ✓。

**踩坑（都在写盘前被拦 ✓）**：① `del_block` 只比 strip 后的内容 ✗ ⇒ `if use_marl_residual:`
在 4 空格与 8 空格处各有一份 ✓ ⇒ 改成**带缩进的整行**匹配 ✓；② 死名字断言写宽了 ✗
（`resmarl_enabled` 是 CLI 参数名 ✓ 本就该留 ✓）⇒ 改成"实现名必须 0 ✓ + `agent_params[...]`
赋值必须 0 ✓ + 配置项名允许 ✓"；③ 我自己的**验证脚本字符串写错** ✓（漏 `self.` / 单行 vs 多行 ✓）
⇒ 换了归一化比对 ✓（14 处里 10 处逐字相同 ✓，其余 4 处是比对写法差异 ✓ 非漂移 ✓）。

**规模** ✓：`CHESCA.detailed.py` **752 → 714** 行 ✓、简版 **643 → 605** 行 ✓
（最初 1225 行 ⇒ 已砍 **620** 行 ✓）；新增 `utils/ches_residual.py`（101 / 140 行 ✓）。

## A61 · 数据集/步数判定改成"只看 Java 入参"（2026-10-08 ✓）

**① `resolve_schema_plan(config)`** ✓（签名去掉 `agent_config` ✓）：原来五级兜底
（`config.EVAL_SCHEMA` → `agent_config['eval_schema']` → `config.SCHEMA` → `agent_config['schema']`
→ `DEFAULT_SCHEMA` ✗）⇒ 现在**与 Multi-agent-eval 同一写法** ✓：

```python
eval_schema = (str(getattr(config, 'EVAL_SCHEMA', None) or '')).strip() or DEFAULT_SCHEMA
steps = getattr(config, 'episode_time_steps', None)      # 没给 ⇒ None ⇒ 用数据集自带长度 ✓
```

**② `evaluate()` 里的"自我喂养"整块删除** ✗（原 L366-374 ✓）：它把解析出的
`eval_schema` / `eval_episode_time_steps` **写回** `agent_config` ✓，而那正是 ① 的第二/四级来源 ✗
（读自己刚写的值 ✓）；顺带删掉**从未使用**的 `marl_mode_resolved` ✓ 与那份多余的 `schema_plan` ✓。
`agent_config['marl_mode']` 的写入**保留** ✓（它是"运行记录快照 `chesca_agent_config.json`"的内容 ✓，
不再被任何判定读取 ✓）。

**③ 唯一"必须从 agent_config 读"的调用方 ⇒ `ablation_resmarl.py`** ✓：它没有命令行 ✓，
配置来自 `configs/*.json` ✓（`load_agent_config(cfg_path)` ✓）⇒ 给它补一行显式入参 ✓：
`EVAL_SCHEMA = agent_config.get('eval_schema')` ✓（保住原语义 ✓，其余不变 ✓）。

**④ 清理后仍读 `agent_config` 的地方（说明清楚 ✓）**：
| 位置 ✓ | 读什么 ✓ | 为什么必须走 agent_config ✓ |
|---|---|---|
| `build_residual_layer(agent_config, marl_mode)` ✓ | `multi_agent_checkpoint` / `residual_alpha` / `residual_action_mask` / `resmarl_after_safety` ✓ | 这些是 ResMARL 配置 ✓，`agent_config` 就是它们的**唯一**载体 ✓ |
| `agent_params` 组装（13 处 ✓） | `tau` / `min_soc_per_hour` / `B_low` / `B_high` / 一串 cool/price 开关 / `balance_type` ✓ | CHESCA **算法参数** ✓（约 40 个 ✓）—— 纯 CHESCA 路径**不读文件** ✗ ✓，`agent_config` 由 `build_agent_config(_cli_overrides_from_args(args))` 产出 ✓ ⇒ 它**就是 Java 入参** ✓✓ |
> 结论 ✓：除上面两类 ✓，**已没有**"数据集/步数必须从 agent_config 读"的地方 ✓。
> （`load_agent_config(json)` 只在 `CHESCA_ResMARL.py` / `ablation_resmarl.py` 里用 ✓
> —— 那两个入口的配置**来自文件** ✓，是它们自己的输入方式 ✓。）

**⑤ 一个要你留意的历史包袱** ✓：抽查 60 份 `chesca_agent_config.json` ⇒ 19 份含
`eval_episode_time_steps` ✓（其中一部分是**旧版 CHESCA 自己写进去的** ✓）。这条 fallback 现在**不再读** ✗ ⇒
若某天有入口只靠 JSON 里的它来定步数 ✗，就会退回"数据集自带长度" ✓。**步数的权威入参是
`--episode-time-steps`** ✓（框架参数 ✓，Java 直接传 ✓）—— 若你确认配置页也会用它 ✓，我再补回来 ✓。

**验证** ✓：
| 检查 | 结果 |
|---|---|
| 默认路径 48 步（不传 `--eval_schema` ✓） | KPI `a9e7b2bb…` ✓、trace `038a31a8…` ✓、JSON `6d525049…` ✓ ⇒ **逐字节同基准** ✓ |
| 显式 `--eval_schema citylearn_challenge_2023_phase_2_local_evaluation` ✓ | 同样三个哈希 ✓（日志 `数据集: …（48步）` ✓ ⇒ 确实是入参在决定 ✓） |
| 兼容矩阵 / 四个入口 `--help` | `MISSING: none` ✓ / 全 exit 0 ✓ |
| 门禁 `--strict` | exit 0 ✓（98 行共享代码逐行一致 ✓）|
| 指纹 | `CHESCA.detailed.py` / `CHESCA.py` 因**语义改动**而变（`c2d1af7f…` → `3bedf19b…` ✓ 预期 ✓）⇒ 已**重存**新基线 ✓ |

**踩坑** ✓：① 先改"那一处调用点"再删旧块 ⇒ 断言报**命中 2 次** ✗（`evaluate` 与 `evaluate_chesca`
各一处 ✓）⇒ 把删除排在前 ✓；② 我自己验证时把参数写成 `--eval-schema`（**中划线** ✗）⇒ argparse
exit=2 ✓ —— 本脚本解析器用的是 `--eval_schema`（**下划线** ✓，与 Java 参数名一致 ✓）。

**规模** ✓：`CHESCA.detailed.py` **714 → 697** 行 ✓、简版 **605 → 586** 行 ✓（最初 1225 ⇒ 已砍 **639** 行 ✓）。

## A62 · 算法参数键表化 + ResMARL 参数整体移出 CHESCA（2026-10-08 ✓）

**① 算法参数改成"键表驱动"** ✓：新增模块级 `AGENT_PARAM_KEYS`（**44 键** ✓）**就放在 `parse_args` 旁边** ✓
（`tau` / `min_soc_per_hour` / `max_soc_normal·outage·reduction` / `B_low` / `B_high` /
`TMP_max_reduction_percent` / 35 个 cool·price 键 / `balance_type` ✓）⇒ 组装块 **80 行 → 16 行** ✓：
```python
for key in AGENT_PARAM_KEYS:
    value = agent_config.get(key)
    if value is None: continue
    agent_params[key] = value
    log_console(...)          # 日志文案与原先**逐行一致** ✓（便于控制台指纹比对 ✓）
```
- ⚠️ **键表是"手抄不出来的"** ✓：它由 AST 从**旧代码的 `for cool_key in (...)` 元组**整段切出 ✓
  ⇒ 35 个键零手抄风险 ✓（`_q_ast_fingerprint.py` + 键表一致性检查一起守着 ✓）。
- ⚠️ 为什么值仍过 `agent_config` ✓：它是 `build_agent_config(_cli_overrides_from_args(args))` 的产物 ✓
  = **入参 + DEFAULTS + 校验**的唯一结果 ✓（`'true'→True` ✓、`min_soc` 的 JSON→dict ✓、
  `tau` 的 1/2/3 范围 ✓）⇒ 若改成直接读 `args` 就会**丢掉校验** ✗（bool 会变成字符串 ✗）⇒ 故保留 ✓。

**② ResMARL 参数整体移出本文件** ✓（8 个 `add_argument` 删除 ✓）：`--marl_mode` / `--resmarl_enabled` /
`--resmarl_after_safety` / `--multi_agent_train_epochs` / `--multi_agent_explore` /
`--multi_agent_checkpoint` / `--residual_alpha` / `--residual_action_mask` ✓。
`evaluate(config, residual=None)` / `evaluate_chesca(config, residual=None)` ✓ 改为**接收**残差层 ✓
（纯 CHESCA 不传 ⇒ `build_residual_layer({}, 'none')` = **未启用层** ⇒ 8 处调用全是空操作 ✓）；
`__main__` 去掉 `apply_resmarl_cli_overrides` ✓ 与 `MARL_MODE_CLI` ✓；imports 去掉
`_parse_marl_mode` / `apply_resmarl_cli_overrides` / `_parse_bool`（已无引用 ✓）✓
—— 两个日志文案 `marl_mode={residual.marl_mode}` **保持不变** ✓（纯路径输出仍与改前逐行相同 ✓）。

**③ 兜底（Java 侧风险）** ✓：Java 的**纯 CHESCA** 任务仍可能把那些参数一起传过来 ✗
（证据 ✓：`BaseDataService.java` L633-639 的 `"chesca.py"` 参数表列着
`marl_mode` / `resmarl_enabled` / `resmarl_after_safety` / `multi_agent_*` / `residual_alpha` /
`residual_action_mask` ✓）⇒ 用 **`parse_known_args()`** 容忍 + 打一行告警 ✓：
「忽略未识别参数 [...]（纯 CHESCA 已不再接受 ResMARL 参数 ✓）」✓ ⇒ 不静默 ✗、也不 exit 2 崩掉 ✗。

**④ 两个入口副本** ✓（`CHESCA_ResMARL.py` 与 `20260914153739.py` ✓ 内容一致 ✓）：
`apply_resmarl_cli_overrides` 改从 `utils.ches_config` 取 ✓、新增
`from utils.ches_residual import build_residual_layer` ✓ ⇒ 自己 `layer = build_residual_layer(agent_config,
'multi_agent')` ✓ 再 `evaluate(Config(), residual=layer)` ✓（残差层只此一处"建" ✓）。

**验证** ✓：
| 检查 | 结果 |
|---|---|
| 纯 CHESCA 48 步 | KPI `a9e7b2bb…` ✓、trace `038a31a8…` ✓、JSON `6d525049…` ✓ ⇒ **逐字节同基准** ✓ |
| **照传 8 个 ResMARL 参数** | exit **0** ✓（不再 exit 2 ✓）+ 告警行 ✓ + 三产物**仍同基准** ✓ |
| ResMARL 控制台指纹（1 步 ✓） | 去空行后 **125 / 125 行完全一致** ✓（唯一差异 = Ray 那行 WARNING 的**时间戳** ✓）；关键标记全一致 ✓ |
| 兼容矩阵 | `MISSING: none` ✓（`evaluate`/`evaluate_chesca` 签名均为 `(config, residual=None)` ✓、`AGENT_PARAM_KEYS` 44 ✓）|
| 键表 ↔ `parse_args` | 键表有而未声明 = **无** ✓；声明而未进键表 = `b_low` / `b_high` / `tmp_max_reduction_percent`（**小写别名** ✓）+ `eval_schema`（数据集参数，走 `config.EVAL_SCHEMA` ✓）⇒ **预期** ✓ |
| 四入口 `--help` / 门禁 / 指纹 | 全 exit 0 ✓ / exit 0 ✓ / 语义改动 ⇒ `3bedf19b…` → `660bde13…` 已**重存** ✓ |

**踩坑** ✓：① `marl_mode` 死名字守卫太严 ✗ —— 命中 2 处是**日志 f-string 的字面量** ✓
⇒ 判定前先剥字符串 ✓ 并**正向**断言"日志文案正好 2 处" ✓；② 新组装块的插入点先落在
"环境创建完成"日志**之前** ✗ ⇒ 会改日志顺序 ✓ ⇒ 挪到之后 ✓。

**规模** ✓：`CHESCA.detailed.py` **697 → 668** 行 ✓、简版 **586 → 545** 行 ✓
（最初 1225 ⇒ 已砍 **680** 行 ✓）。

## A63 · （Java/DB）CHESCA 参数补进「配置组」+ 白名单同步（2026-10-08 ✓）

**背景** ✓：代码编辑器「配置」弹窗按**配置组**挂参数 ✓，组存在 DB 表 `algorithm_param_config_set`
（成员是 `algorithm_param_config.id` 的 JSON 数组 ✓，由 `BaseDataService.updateSetMembers` 维护 ✓）；
执行时按 `BaseDataService.ALGORITHM_CONFIG_CLI_WHITELIST`（每脚本一份 ✓）翻成 `--参数名 值` ✓。

**查出两个缺口** ✗（对照 `CHESCA.py` 的 argparse ✓）：
1. `tau` / `balance_type` / `B_low` / `B_high` 虽已登记 ✓，但 **`if_system = 1`** ✗ ——
   而"系统参数**不允许**加入配置组"（`updateSetMembers` 的硬规则 ✓）⇒ 这 4 个一直**进不了任何组** ✗；
2. `eval_schema`（纯 CHESCA 的评估数据集 ✓）**完全没登记** ✗。
（其余 40 个早已成组 ✓：冷机 12 ✓、TMP 帽 5 ✓、缓充 6 ✓、SOC 4 ✓、电价 13 ✓。）

**做法** ✓：
- 新增 `citylearnjava/src/main/resources/db/algorithm_param_config_chesca_groups2.sql` ✓（**幂等** ✓）：
  ① 登记 `eval_schema`（`value_type = special` ✓ ⇒ 界面渲染成数据集下拉 ✓ 与 `eval-schema` 同型 ✓）；
  ② `UPDATE ... SET if_system = 0` 把那 4 个改成可入组 ✓（与 `price_*` 那次同一处理 ✓）；
  ③ 新建 2 组：**树搜索与负荷阈值**（4 ✓）、**纯CHESCA 评估数据集**（1 ✓）；
  ④ **重算全部 7 组** 的 members ✓（自愈 ✓：参数清单变了重跑即可 ✓）；
  ⑤ `is_member = 1` 收敛成"这 45 个都在组里" ✓；⑥ 3 条校验查询 ✓。
- `BaseDataService.java` 的 `chesca.py` 白名单 ✓：删掉 **8 个 ResMARL 参数** ✓
  （`marl_mode` / `resmarl_enabled` / `resmarl_after_safety` / `multi_agent_train_epochs` /
  `multi_agent_explore` / `multi_agent_checkpoint` / `residual_alpha` / `residual_action_mask` ✓）
  —— A62 已把它们从 `CHESCA.py` 删掉 ✓ ⇒ 名单不同步的话"用户填了却不生效" ✗（虽不会崩 ✓：
  CHESCA.py 现在是 `parse_known_args()` ✓）✓；注释里同时写明这条规矩与本次原因 ✓。

**分组规模** ✓（7 组 / 45 参数 ✓）：

| 组 | 参数个数 |
|---|---|
| 电价感知电池 | 13 ✓ |
| 冷机 | 12 ✓ |
| 电力恢复后缓充 | 6 ✓ |
| 电力恢复时 TMP 功率帽 | 5 ✓ |
| SOC 参数配置 | 4 ✓ |
| 树搜索与负荷阈值（新 ✓） | 4 ✓ |
| 纯CHESCA 评估数据集（新 ✓） | 1 ✓ |

⇒ **最大组 13 个** ✓（"别导致单配置组配置数量过多" ✓）。

**验证** ✓：
- 三方一致性 ✓（`CHESCA.py` argparse 声明 **48** ✓ ↔ Java 白名单 **48** ✓ ⇒ **双向零差异** ✓）；
- Java 编译 ✓：`_compile_check.ps1` ⇒ `javac exit code: 0` ✓，生成 105 个 class ✓（`BaseDataService.class` 在 ✓）；
- ⚠️ **SQL 未在本机执行** ✗（这台机器没有 `mysql` 客户端 ✓）⇒ 需手工跑一次 ✓：
  `mysql -uroot -p000000 citylearn < algorithm_param_config_chesca_groups2.sql` ✓
  ⇒ 看第 6.1 条结果：7 个组、最大 13 ✓；第 6.3 条应返回 **0 行** ✓。

**两条待你确认** ✗：① 小写别名 `b_low` / `b_high` / `tmp_max_reduction_percent` 只在**白名单**里 ✓、
不在参数目录里 ✗ ⇒ 配置弹窗选不到（选大写的 `B_low` / `B_high` 即可 ✓）—— 要"两种都能选"我再补登记 ✓；
② 纯 CHESCA 的 `eval_schema`（下划线 ✓）与 Multi-agent 的 `eval-schema`（中划线 ✓）是**两个条目** ✓，
弹窗里会各有一条数据集参数 ✓（脚本不同、参数名不同 ✓，属预期 ✓）。

## A64 · （Java/DB）把配置页的 CHESCA 取值灌进「代码编辑器 CHESCA.py 的脚本配置」（2026-10-08 ✓）

**目标** ✓：`py_file.algorithm_config`（`file_name = 'CHESCA.py'`）预置好 ——
编辑器里选中 CHESCA.py 点「配置」，7 个配置组已挂好、**值也按配置页填好了** ✓。

**新增** ✓：`citylearnjava/src/main/resources/db/py_file_chesca_algorithm_config.sql` ✓（幂等 ✓）
- 落库格式与 `AlgorithmConfigDialog.vue` 逐字一致 ✓：
  `[{"type":"alone","params":[]}, {"type":"set","set_id":N,"params":[{"id":..,"param_name":"..","value":".."}, …]}, …]`
  （第一个 section 固定是「单独配置」空卡 ✓；`set_id` 是下划线 ✓；`params[].id` = `algorithm_param_config.id` ✓）
- **取值来源 = 配置页**（`algorithm_config` 表 ✓）：一般参数取同名键 ✓；
  `B_low`/`B_high`/`TMP_max_reduction_percent` 做**大小写键映射** ✓；
  `eval_schema`（`special` ✓）换成 `citylearn_dataset.id` ✓（弹窗只认 id ✓）；
  `min_soc_per_hour`（`map` ✓）取目录 `default_value` ✓（本就是弹窗的 `[{key,value}]` 形状 ✓，
  且 map 类参数**不会**被翻成命令行 ✓）；没存过的键 ⇒ 空串 ✓。
- ⚠️ **踩到的坑** ✓：`GROUP_CONCAT` 默认上限 **1024 字节** ✗ ⇒ 45 个参数约 2.7KB 会被**截断** ✗
  ⇒ 脚本开头 `SET SESSION group_concat_max_len = 1000000;` ✓。
- 先决条件 ✓：先跑 A63 的 `algorithm_param_config_chesca_groups2.sql`（7 组齐全 ✓）；
  缺组也不会写出非法 JSON（缺的组自动跳过 ✓）。

**验证** ✓（**离线模拟** ✓：用仓库 SQL 里的种子值把脚本逻辑在 Python 里复算一遍 ✓）
- `json.loads` 通过 ✓（形状合法 ✓）；顶层 section = **8**（1 alone + 7 set ✓）；
  各组参数个数 = **[12, 5, 6, 4, 13, 4, 1]** ✓（最大 13 ✓）；合计 **45** ✓；字段名 `set_id/param_name/value` 齐全 ✓。
- ⚠️ **SQL 未在本机执行** ✗（无 `mysql` 客户端 ✓）⇒ 需手工跑 ✓：
  `mysql -uroot -p000000 citylearn < py_file_chesca_algorithm_config.sql` ✓
  ⇒ 看 3.1：`json_ok = 1` ✓、`section_count = 8` ✓；3.3：`alone` 0 个 + 7 个 set 分别为 12/5/6/4/13/4/1 ✓。

**注意** ✓：弹窗取配置时**优先任务级** `py_task.config` ✓，没有才回落到脚本文件这份 ✓
（`AlgorithmConfigDialog.buildSectionsFromFile` ✓）⇒ 本脚本管的是"编辑器里点执行 / 任务没自带配置"这条路 ✓；
若要连**任务级**那两份也一起预置，说一声我再补一段 ✓。CHESCA_ResMARL.py 的同款预置同理 ✓。

## A65 · （实测）把配置页取值**真正写进** `py_file.algorithm_config`（2026-10-08 ✓）

**症状** ✓：编辑器里点开 CHESCA.py 的「配置」是**空的** ✗ —— 查库发现根因很简单 ✓：
`py_file.id = 6`（`file_name = 'CHESCA.py'`）的 `algorithm_config` **长度 = 0** ✓
（A64 那个 SQL 是**手工执行**的 ✓，还没跑过 ✓）；而**配置组其实都在** ✓
（`algorithm_param_config_set` 里 7 组齐全 ✓：冷机 [26–37] ✓、TMP 帽 [38–42] ✓、缓充 [43–48] ✓、
SOC [49–52] ✓、电价 [11–23] ✓、树搜索与负荷阈值 [7,10,9,8→7–10] ✓、纯CHESCA 数据集 [57] ✓
—— 说明 `algorithm_param_config_chesca_groups2.sql` **已经跑过** ✓）。

**做法** ✓：**直接连库写**（不再依赖手工执行 SQL ✓）——`127.0.0.1:3306/citylearn` ✓
（`application.yml` 里的 root/000000 ✓）。因为该 conda 环境没有 MySQL 驱动 ✗，
先 `pip install pymysql`（纯 Python ✓ 2.2.8 ✓），再用一个临时脚本 ✓：
读 `algorithm_param_config_set`（7 组 + members ✓）→ 读目录定义 ✓ → 读配置页 `algorithm_config`（59 键 ✓）
→ 拼 v2 分组 JSON ✓ → **先备份旧值** ✓ → `UPDATE py_file SET algorithm_config = %s WHERE id = 6` ✓ → 复验 ✓。

**结果** ✓：`JSON_VALID = 1` ✓、section = **8**（1 alone + 7 set ✓）、**4299 字节** ✓；
各组参数 **12 / 5 / 6 / 4 / 13 / 4 / 1** ✓（合计 **45** ✓）。

**数值核对** ✓（逐项与配置页对照 ✓，全部一致 ✓）—— 能证明取值来自**配置页**而不是默认值 ✓：
`min_cool_per_c_overheat = 0.25` ✓、`lagged_indoor_hotter_margin_c = 0.5` ✓、
`outdoor_floor_max_overheat_c = 1.0` ✓、`price_low_charge_ele = 0.15` ✓、
`price_low_target_soc = 0.75` ✓、`tau = 1` ✓、`balance_type = C` ✓、`B_low = 1.18` ✓、`B_high = 1.0` ✓；
`eval_schema = 2` ✓（= `citylearn_challenge_2023_phase_2_online_evaluation_1` 且 `enabled = 1` ✓，
数据集目录里该 schema 唯一 ✓）。
⚠️ **如实记一处"刻意不同"** ✓：`min_soc_per_hour` 存的是目录的 `default_value`
（弹窗要的 `[{"key":"0","value":"0.6"}, …]` 形状 ✓），而配置页里是 `{"0":0.6, …}`
—— 数值逐个相同 ✓；且 `map` 类参数**本来就不会**被翻成命令行参数 ✓（`resolveAlgorithmConfigValue` 跳过 ✓）
⇒ 运行时用的仍是配置页那份 ✓，这里只为让弹窗能显示 ✓。

**遗留** ✓：① 配置组里有个多出来的 **`id=1`「组1」**（成员只有 `[7]` = tau ✓）—— 像是早先的测试残留 ✓，
要不要删你说了算 ✓（删：`DELETE FROM algorithm_param_config_set WHERE id = 1;` ✓）；
② `CHESCA_ResMARL.py`（`py_file.id = 7`）仍是空的 ✓ —— 需要的话我照同一套补 ✓
（它还要多 4 个残差参数 ✓，得先给它们建组或放进「单独配置」卡 ✓）。
**查看方式** ✓：浏览器里**刷新**一下再点「配置」✓（文件列表接口返回 `algorithmConfig` ✓）；
临时脚本已删 ✓、旧值备份留档在 `citylearnpy/_tmp_bak53/_bak_py_file6_algorithm_config.json` ✓。

## A66 · 修复平台任务崩溃：`--min_soc_per_hour` 入参容错（2026-10-08 ✓）

**症状** ✗（平台跑 CHESCA 任务，任务 `75fe31e7…`、`py_task.py_id = 6` ✓、`config = NULL` ✓）：
```
File ".../CHESCA.py", line 516, in _cli_overrides_from_args
    value = json.loads(value) if isinstance(value, str) else value
json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 3 (char 2)
```
**根因** ✓：A65 把配置页取值灌进 `py_file.algorithm_config` 后 ✓，`map` 类参数
（`min_soc_per_hour` ✓）第一次**真的**被当成命令行参数传给了脚本 ✓ —— 而平台那条链路
把它序列化成**不是 JSON** 的写法 ✗（错误信息 "char 2" 正是 `{0…` ✓，即 Java/Fastjson
直接序列化 `Map<Integer,Double>` 的 `{0=0.6, 1=0.65}` / `{0:0.6}` ✓）。
⚠️ **如实记** ✓：A65 的灌入本身没写错（库里那份是**合法 JSON** ✓：`[{"key":"0","value":"0.6"},…]` ✓，
已核对 ✓）—— 它只是**引爆了平台侧一个既有的形状问题** ✗。具体是哪一处 Java 序列化未能 100% 定位 ✗
（`BaseDataService.resolveAlgorithmConfigValue` 对字符串是原样透传 ✓ ⇒ 说明源头更早 ✓）。

**修法** ✓（脚本侧容错 ✓，一次覆盖所有形状 ✓）：`_cli_overrides_from_args` 里那行 `json.loads(value)`
换成新函数 `_parse_min_soc_cli(value)` ✓，按序接受：
1. `{"0":0.6,…}`（配置页 `chesca_agent_config.json` 写法 ✓）
2. `[{"key":"0","value":"0.6"},…]`（配置弹窗「键值对」控件写法 ✓）
3. `{0=0.6, 1=0.65}` / `{0:0.6, 1:0.65}`（Java/Fastjson 写法 ✗ → 宽松解析 ✓）
4. 都不行 ⇒ 抛 `ValueError`，**带上原值** ✓（不再裸 JSONDecodeError ✓，好定位 ✗）

**验证** ✓：
| 用例 | 结果 |
|---|---|
| 单元：4 种写法 + 垃圾串 | ①②③④ 全部解析成 `{小时: 下限}` ✓；垃圾串给清晰报错 ✓ |
| 端到端：**不传** `min_soc`（基线 ✓） | exit 0 ✓、三产物 `a9e7b2bb…` / `038a31a8…` / `6d525049…` ✓ **同基准** ✓ |
| 端到端：**Java 写法** `{0=0.6, 1=0.65, …}`（24 项 ✓） | **exit 0** ✓（原先必崩 ✗）、三产物**同基准** ✓ |
| 端到端：弹窗数组写法 ✓ | exit 0 ✓、同基准 ✓ |
| 门禁 / 指纹 | `--strict` exit 0 ✓；CHESCA 语义改动 ⇒ 指纹已**重存** ✓ |

**平台侧后续** ✓（可选 ✓）：这次靠脚本容错接住 ✓；若要根治，把 `map` 类参数在 Java 里
统一成**合法 JSON 字符串**再传 ✓（或干脆跳过 ✓——但那样配置页的 `min_soc_per_hour` 就不生效了 ✗）。
另 ✓：任务目录里那份 `CHESCA.py` 是**旧副本** ✓（30,934 字节 ✓，含崩溃代码 ✓）⇒ 重跑一次任务即可
拿到新副本 ✓；若平台对同一任务 id 不重新复制 ⇒ 新建一次任务 ✓。
**规模** ✓：`CHESCA.detailed.py` **668 → 714** 行 ✓（新增容错函数 + 详注 ✓）、简版 **545 → 582** 行 ✓。

## A67 · 续修：`min_soc_per_hour` 的**小时键**规范化（2026-10-08 ✓）

**下一层症状** ✗（A66 修好 JSON 解析之后 ✓，平台再跑一次就露出来 ✓）：
```
File ".../utils/ches_config.py", line 88, in _parse_min_soc_map
    raise ValueError(f'缺少对应的时间段 {hour}')
ValueError: 缺少对应的时间段 0
```
**根因** ✓：`_parse_min_soc_map` 要求键**恰好**是 `'0'…'23'` ✓，而平台传来的键是
**Java 的浮点键** `'0.0' / '1.0' / …` ✗（`Map<Integer,Double>` 序列化所致 ✓）
⇒ 一个都对不上 ✗。原报错只说"缺少 0"，看不出对方到底给了什么 ✗。

**修法** ✓（两处都做 ✓）：
1. `utils/ches_config._parse_min_soc_map` ✓：先把每个键 `str(int(float(键)))` **归一** ✓
   （`'0.0'` / `0` / `'00'` / `'"0"'` / 带空格 ⇒ 全变 `'0'` ✓）；
   报错改成**列出收到的键** ✓：`min_soc_per_hour 缺少时间段 0（收到的键：['5']）` ✓。
2. `CHESCA._parse_min_soc_cli` ✓：同样归一 ✓；并顺手接受**扁平偶数列**写法
   `['0','0.6','1','0.65', …]` ✓（前端再变形状也接得住 ✓）。

**验证** ✓：
| 用例 | 结果 |
|---|---|
| 单元：浮点键 `{'0.0':0.6,…}` ✓ | 解析成功 ✓、键归一成 `['0','1','2']`、共 24 项 ✓ |
| 单元：缺项（只给 `{'5.0':…}`） | 报错**列出键** ✓：`缺少时间段 0（收到的键：['5']）` ✓ |
| 端到端 ×4 种怪写法 | **Java 浮点键** ✓ / Java 整数键 ✓ / Fastjson `{0:…}` ✓ / 弹窗数组 ✓ ⇒ **全部 exit 0** ✓ 且三产物 `a9e7b2bb…` / `038a31a8…` / `6d525049…` **同基准** ✓ |
| 门禁 / 指纹 | `--strict` exit 0 ✓；`utils/ches_config.py` + `CHESCA.py` 语义改动 ⇒ 指纹已**重存** ✓ |

**平台侧后续** ✓（同 A66 ✓）：根治要把 `map` 值统一成合法 JSON **且键为字符串** ✓；
现在脚本侧两种形状都接得住 ✓。任务目录里那份 `CHESCA.py` 已同步成新版 ✓
（`utils/ches_config.py` 走**源码目录** ⇒ 无需复制 ✓ 已自动生效 ✓）。
**规模** ✓：`utils/ches_config.detailed.py` **497 → 549** 行 ✓、`CHESCA.detailed.py` **714 → 728** 行 ✓。

## A68 · 三修：`min_soc_per_hour` 支持「key/value 字段名没加引号」的写法（2026-10-08 ✓）

**新证据** ✓（A67 改好的报错直接给出来的 ✓）：
```
ValueError: min_soc_per_hour 缺少时间段 0（收到的键：['key', 'value', '{key']）
```
⇒ 平台传的是**带 `key` / `value` 字段名**的写法 ✓，但字段名**没加引号** ✗（不是合法 JSON ✗），
形如 `[{key:0, value:0.6}, {key:1, value:0.65}, …]` ✗；
上一版宽松解析把它按 `键=值` 硬切 ✗ ⇒ 切出 `'{key'` 这种**假键** ✓。

**修法** ✓（`CHESCA._parse_min_soc_cli` ✓，并补 `import re` ✓）：
1. 新增 **② 分支**：用正则按 `key…value…` **成对抽取** ✓（冒号/等号 ✓、键值带不带引号 ✓、
   带不带花括号 ✓ 都能吃 ✓）；
2. **③ 分支**（Java Map 文本 ✓）加**数字键校验** ✓ ⇒ 切不出数字键就**直接报错** ✓，
   不再造 `'{key'` 假键 ✗，且报错留在**入参层**并**带上原值** ✓（下次一眼定位 ✓）。

**踩的坑** ✓（自己当场抓住 ✓）：第一版正则把**逗号**排除在"可跳过字符"之外 ✗ ——
而 `key:0, value:0.6` 中间**正是一个逗号** ✓ ⇒ 永远匹配不上 ✗ ⇒ 改成
`[^}\]]{0,60}?`（可跳过到 `}` / `]` 之前 ✓）✓。

**验证** ✓：
| 用例 | 结果 |
|---|---|
| 单元 8 种写法 | `{key: k, value: v}` ✓ / 带引号 ✓ / `{key=k, value=v}` ✓ / 无花括号 `key: k, value: v; …` ✓ / Java Map ✓ / 标准 JSON 对象 ✓ / 弹窗数组 ✓ / 扁平偶数列 ✓ ⇒ **全部 24 项** ✓ |
| 端到端 3 种（含平台真实形态 ✓） | key/value 无引号 ✓ / 带引号 ✓ / Java 浮点键 ✓ ⇒ **exit 0** ✓ 且三产物 `a9e7b2bb…`/`038a31a8…`/`6d525049…` **同基准** ✓ |
| 门禁 / 指纹 | `--strict` exit 0 ✓；指纹已**重存** ✓ |
| 任务目录 | 两个失败过的任务目录（`49d5236d…` / `2e482e19…`）都已换成新版 `CHESCA.py` ✓（33,556 字节 ✓）|

**平台侧根治（仍未做 ✗，待你定）** ✓：源头是把配置弹窗的 `map` 值序列化成
**JS 对象文本**（字段名不带引号 ✗、键还可能是浮点 ✗）⇒ 合法 JSON 化即可 ✓；
脚本侧现在四种形状都接得住 ✓，不改也能跑 ✓。
**规模** ✓：`CHESCA.detailed.py` **728 → 740** 行 ✓、简版 **596 → 608** 行 ✓。
