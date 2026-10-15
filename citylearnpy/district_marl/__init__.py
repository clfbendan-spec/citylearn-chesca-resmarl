# -*- coding: utf-8 -*-
"""区域级（District）指标驱动的多智能体强化学习扩展包。

【本包的定位】
  现有 CHESCA-ResMARL / Multi-agent 流水线里，区域级 KPI（district 峰值、
  负荷因子……）只出现在**评估口径**（exported_kpis.csv），决策链路上完全看不见：
    · 每个 agent 的观测只有"本楼"信息；
    · 奖励里的社区信号若存在，也只是被动标量；
    · best-checkpoint 的选择指标是**纯舒适**（P4_COST_WEIGHT=0）。
  本包把区域级指标从"评估口径"搬进"决策口径"，共三件事：
    ① 观测层：给每个 agent 追加 9 维区域特征（共享维 + 本楼专属维）；
    ② 奖励层：显式社区尖峰惩罚 + 可选团队奖励混合 + 可选错峰引导；
    ③ 选择层：best-checkpoint 按区域 KPI 选，而不是纯舒适。

【零改动承诺】
  本包**只新增文件**，不修改、不覆盖 citylearnpy 下任何原有文件。
  原环境类 ContextRLlibEnv 只被**继承**（district_env），原奖励类
  CustomComfortReward 只被**继承**（district_reward）。

【导入策略】
  包顶层**不 import** ray / citylearn —— 保证 `import district_marl` 与
  `from district_marl import district_features` 可在无 ray 环境下用于单测。

组成
----
· district_features ：9 维区域观测特征（纯 numpy，可脱离仿真单测）
· district_env      ：DistrictContextRLlibEnv（在 ContextRLlibEnv 之上追加区域观测）
· district_reward   ：DistrictPeakReward（社区尖峰惩罚 + 团队奖励 + 错峰引导）
· district_config   ：全部可调参数（集中一处，便于消融实验）
· district_train    ：训练入口（按区域 KPI 选 best-ckpt）
· district_eval     ：评估入口（导出 exported_kpis.csv + 区域摘要）
"""

# -----------------------------------------------------------------------------
# 路径引导：保证 `utils.*` / `custom_comfort_reward` 等**根级模块**可被导入。
#   理由：本包位于 citylearnpy/district_marl/，单独 import 时 sys.path 里没有
#   citylearnpy 根目录（原入口脚本都在根目录，天然可见）。这里补一次即可，
#   与 utils.base.ensure_on_pythonpath 的行为一致（幂等、只插一次）。
# -----------------------------------------------------------------------------
import sys as _sys
from pathlib import Path as _Path

_PKG_ROOT = _Path(__file__).resolve().parents[1]      # …/citylearnpy
if str(_PKG_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PKG_ROOT))

# -*- 惰性导入：这里**不** import 子模块，避免把 ray/citylearn 拖进 import 期 -*-
__all__ = [
    'district_features',
    'district_env',
    'district_reward',
    'district_config',
    'district_train',
    'district_eval',
]

__version__ = '0.1.0'
