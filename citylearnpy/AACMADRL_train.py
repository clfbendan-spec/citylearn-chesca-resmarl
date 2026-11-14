"""AACMADRL task entry point; also works after the backend copies this file."""
# 阅读路线：本入口 -> aacmadrl/task.py 的 main('train') -> core.py 的 train()。
# 输入来自任务参数（数据、轮数、学习率等），不是在这里直接创建神经网络。
# 输出包括训练过程、候选检查点、选中的模型及模型哈希；评估任务再明确引用它。
# 此文件会被后端复制到任务目录，bootstrap负责找回真正的源码包，不负责训练。
import os
import sys
from pathlib import Path


def bootstrap():
    candidates = [Path(os.environ['CITYLEARNPY_DIR'])] if os.environ.get('CITYLEARNPY_DIR') else []
    candidates += list(Path(__file__).resolve().parents)
    for root in candidates:
        if (root / 'aacmadrl/task.py').is_file():
            sys.path.insert(0, str(root))
            return
    raise RuntimeError('请配置 CITYLEARNPY_DIR 指向 citylearnpy')


if __name__ == '__main__':
    bootstrap()
    import platform
    from aacmadrl.task import main
    sys.exit(main('train'))
