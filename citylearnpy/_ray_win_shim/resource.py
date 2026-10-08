"""
Windows 兼容：Ray / prometheus_client 依赖 Unix resource API。
将该目录加入 PYTHONPATH（含 Ray worker 子进程），避免 getrlimit / getpagesize 缺失。
"""

RLIMIT_CPU = 0
RLIMIT_FSIZE = 1
RLIMIT_DATA = 2
RLIMIT_STACK = 3
RLIMIT_CORE = 4
RLIMIT_RSS = 5
RLIMIT_NPROC = 6
RLIMIT_NOFILE = 7
RLIMIT_MEMLOCK = 8
RLIMIT_AS = 9


def getrlimit(_which):
    return (8192, 8192)


def setrlimit(_which, _limits):
    return None


def getpagesize():
    return 4096
