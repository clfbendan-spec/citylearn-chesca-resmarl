# -*- coding: utf-8 -*-
r"""平台入口：区域级（District-aware）MARL 评估。

与 `District_MARL_train.py` 同款「根目录入口 + 定位包根目录」套路，
原因（脚本被复制到任务目录并拍平、cwd 不是脚本目录）见该文件顶部说明。

【断点从哪来】（按优先级，见 district_marl/district_eval.py → resolve_checkpoint）
  1) `--train-task-id <训练任务id>`：平台任务编排给评估子任务固定注入的那个参数
     ⇒ 按 <输出根>/<任务id>[-train]/checkpoints/multi_agent_resume 定位训练产出的模型；
  2) `--checkpoint <目录>`：显式指定（独立运行 / 手动覆盖）；
  3) 都没有时才读 `district_config.DISTRICT_CHECKPOINT_DIR`（旧版全局兜底目录）。

【平台协议】
  · 后端固定追加 `--output-dir <任务目录>`；
  · 结尾按 `outputkpi` 协议打印 KPI 段（见 district_marl/district_eval.py → rollout_district
    的 export_dir 分支），Java 据此解析入库；
  · 同时导出 `exported_kpis.csv` 便于与历史 run 对比。

【不改动任何既有文件】本文件是纯新增。
"""

import os
import sys
from pathlib import Path

FALLBACK_ROOT = Path(r'D:/citylearn-demo/citylearnpy')
_MARKER = Path('district_marl') / 'district_config.py'


def _find_root() -> Path:
    """找到含 district_marl 包的 citylearnpy 根目录。"""
    candidates = []
    env = (os.environ.get('CITYLEARNPY_DIR') or '').strip()
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
for _p in (str(Path(__file__).resolve().parent), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---- 确定性引导（★平台路径的唯一生效点；评估也必须，否则读到的权重与训练口径不一致）----
#   `PYTHONHASHSEED` 只在解释器启动时读一次 ⇒ 见 District_MARL_train.py 同名注释。
if __name__ == '__main__':
    from district_marl._hashseed import ensure_hashseed
    ensure_hashseed()

    from district_marl.district_eval import main
    sys.exit(main())
