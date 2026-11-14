# -*- coding: utf-8 -*-
r"""平台入口：区域级（District-aware）MARL 训练。

【为什么不直接把 district_marl/district_train.py 登记进 py_file】
  后端执行前会把脚本**复制到任务目录并拍平**：
      copyPythonScriptForTask: targetDir.resolve(source.getFileName())
  （见 BaseDataService.java:4787-4798）
  ⇒ 运行副本落在 `output/outkpis/<taskId>/` 下，那里**没有** district_marl 包；
    且子进程 cwd = 后端 JVM 的工作目录（ProcessBuilder 未设 .directory）
  ⇒ 直接登记子目录里的脚本，包内导入必然失败。
  所以把入口放在 citylearnpy **根目录**，由它把真实的包根目录补进 sys.path。

【定位包根目录】按优先级：
  1) 环境变量 CITYLEARNPY_DIR（本项目既有约定，utils/base 也在用）
  2) 从本文件所在目录逐级向上找含 district_marl/district_config.py 的目录
  3) 兜底常量 FALLBACK_ROOT（与 application.yml 的 file.python-file-path 一致）

【顺带满足平台协议】
  · 后端会固定追加 `--output-dir <任务目录>`（BaseDataService.java:3637-3639），
    district_train.py 已支持该参数 ⇒ KPI/曲线/汇总**以及训练断点**
    （<任务目录>/checkpoints/multi_agent_resume）都落在任务目录里，
    评估子任务据此按训练任务 id 定位模型；
  · 脚本末尾按 `outputkpi` 协议打印 KPI 段（见 district_marl/district_train.py
    的 export_kpis_csv），Java 据此解析入库。

【不改动任何既有文件】本文件是纯新增；训练逻辑全在 district_marl/ 包里。
"""

import os
# 新手提示：真正的学习发生在district_train.main的algo.train()内。
# 观测由district_env整理，动作由RLlib策略产生，CityLearn负责物理状态转移。
# train_progress和learner诊断用于核实是否实际更新，最终KPI还需独立rollout计算。
import sys
from pathlib import Path

# 与 citylearnjava/src/main/resources/application.yml 的 file.python-file-path 保持一致
FALLBACK_ROOT = Path(r'D:/citylearn-demo/citylearnpy')
_MARKER = Path('district_marl') / 'district_config.py'


def _find_root() -> Path:
    """找到含 district_marl 包的 citylearnpy 根目录。"""
    candidates = []
    env = (os.environ.get('CITYLEARNPY_DIR') or os.environ.get('CITYLEARN_PYTHON_PATH') or '').strip()
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve()
    candidates.append(here.parent)
    candidates.extend(here.parents)
    candidates.append(FALLBACK_ROOT)
    for base in candidates:
        try:
            if (base / _MARKER).is_file():
                return base
        except OSError:
            continue
    raise SystemExit(
        '[District-MARL] 找不到 citylearnpy 包根目录'
        f'（应包含 {_MARKER.as_posix()}）。'
        '请设置环境变量 CITYLEARNPY_DIR 指向 citylearnpy 后重试。')


ROOT = _find_root()
# 先放脚本自身目录，再把 ROOT 插到最前（保证 utils / district_marl 解析到真身）
for _p in (str(Path(__file__).resolve().parent), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---- 噪声抑制（★必须在 import ray / torch 之前）---------------------------
#   实测一次 320 轮训练：protobuf 版本警告 40+ 条、requests 1 条、ray deprecation 若干，
#   全部在 `from district_marl.district_train import main` 那一行里产生
#   ⇒ 放在这里（该 import 在下方 `__main__` 块内）才来得及。
#   同时压 warnings 与 logging 两条通道，原因见 district_marl/_quiet.py 顶部。
#   要看全部：加 --verbose-warnings（会被摘掉，不传给下游 argparse）。
from district_marl._quiet import quiet_warnings  # noqa: E402  （必须晚于 sys.path 设置）

quiet_warnings()

# ---- 确定性引导（★平台路径的唯一生效点）----------------------------------
#   `PYTHONHASHSEED` 只在**解释器启动时**读一次，进程内赋值无效 ⇒ 必须"发现不一致就
#   把自己重启一次"。district_train.py 里那份 bootstrap 写在它自己的 `__main__` 下，
#   而平台是从**本文件**以 `__main__` 身份启动、再 import 那个模块的
#   ⇒ `__name__` 是 'district_marl.district_train'，那份 bootstrap **永不触发**
#   （实测：历史全部平台任务的 district_summary.json 里 pythonhashseed 都是 ""）。
#   所以引导必须放在这里，且必须在 import 重依赖（ray/torch）之前完成。
if __name__ == '__main__':
    from district_marl._hashseed import ensure_hashseed
    ensure_hashseed()

    from district_marl.district_train import main
    sys.exit(main())
