"""AACMADRL task evaluation entry point, no global checkpoint fallback."""
# 阅读路线：本入口 -> aacmadrl/task.py 的 main('eval') -> core.py 的 evaluate()。
# 输入是明确的训练任务/检查点和评估数据；此流程只运行固定策略，不更新网络权重。
# 输出包括KPI、逐步状态/动作/反馈、配置快照及完整性清单，供模型优选按任务读取。
# 评估成功不等于舒适达标；是否可评分还要检查协议和固定Anchor是否匹配。
import os
import sys
from pathlib import Path


if __name__ == '__main__':
    candidates = [Path(os.environ['CITYLEARNPY_DIR'])] if os.environ.get('CITYLEARNPY_DIR') else []
    candidates += list(Path(__file__).resolve().parents)
    for root in candidates:
        if (root / 'aacmadrl/task.py').is_file():
            sys.path.insert(0, str(root))
            break
    else:
        raise RuntimeError('请配置 CITYLEARNPY_DIR 指向 citylearnpy')
    import platform
    from aacmadrl.task import main
    sys.exit(main('eval'))
