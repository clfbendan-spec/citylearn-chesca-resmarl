# -*- coding: utf-8 -*-
r"""
任务运行包装器：转发执行目标 Python 脚本，并把**退出码落盘**
==============================================================

解决什么问题
------------
后端重启后，新 JVM 无法再取得那个 Python 子进程的退出码（它已经不是本 JVM 的
直系子进程了）。此前只能靠"日志里有没有 outputkpi 段"去猜任务成功还是失败，
遇到「成功结束但不打印 KPI 段」的脚本就会误判。

本包装器由 Java 这样调用::

    python -u _task_runner.py --exit-code-file <任务目录>/exit_code.txt -- <目标脚本> [脚本参数...]

目标脚本结束后，包装器把**真实退出码**写入 exit_code.txt（文件内容就是一个整数）。
于是「后端重启后回填任务状态」可以依据退出码判定，而不是猜。

为什么用包装器，而不是在每个脚本里加写文件的代码
------------------------------------------------
1. **一处生效**：CHESCA.py / NOCONTROL.py / Multi-agent*.py 等所有脚本自动获得该能力，
   既不用逐个改动，也不必改动 Multi-agent.py（该项目要求保持其源文件不变）。
2. **退出码语义完整**：脚本内的 ``sys.exit(n)``、argparse 参数错误（exit 2）、未捕获异常
   （exit 1）都能被正确捕获并落盘。若改在脚本内部用 atexit 实现，SystemExit 携带的码
   是取不到的（会被误记成 0）。
3. **不改变脚本行为**：仍以 ``__name__ == '__main__'`` 执行，``sys.argv`` / ``__file__`` /
   ``sys.path`` 都与"直接 python <脚本>"时一致；包装器最后用捕获到的码 ``sys.exit()``，
   所以不需要重启场景时 Java 的 waitFor() 拿到的退出码也依然正确。

进程被强杀（TerminateProcess / SIGKILL）时包装器来不及写文件，此时 exit_code.txt 不存在，
调用方需退回其它判据 —— 这是预期行为，不是缺陷。
"""

import os
import runpy
import sys
import traceback

USAGE = ('[task_runner] 用法: python -u _task_runner.py '
         '--exit-code-file <文件> -- <脚本> [脚本参数...]')


def _parse_argv(argv):
    """解析包装器自己的参数，返回 (exit_code_file, 目标脚本, 传给脚本的参数列表)。"""
    code_file = None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == '--exit-code-file' and index + 1 < len(argv):
            code_file = argv[index + 1]
            index += 2
        elif token == '--':
            index += 1
            break
        else:
            break
    if index >= len(argv):
        return code_file, None, []
    return code_file, argv[index], list(argv[index + 1:])


def _write_exit_code(code_file, code):
    """把退出码写入文件。落盘失败不影响任务本身（调用方会退回其它判据）。"""
    if not code_file:
        return
    try:
        directory = os.path.dirname(os.path.abspath(code_file))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(code_file, 'w', encoding='utf-8') as handle:
            handle.write(str(int(code)))
    except Exception:
        pass


def main():
    code_file, script, script_args = _parse_argv(sys.argv[1:])
    if script is None:
        print(USAGE, flush=True)
        _write_exit_code(code_file, 2)
        return 2

    script_abs = os.path.abspath(script)
    # 复现"直接 python <脚本>"的运行环境：argv[0] 为脚本路径，脚本所在目录进 sys.path
    # （runpy.run_path 对普通 .py 文件不会自动把其目录加入 sys.path）
    script_dir = os.path.dirname(script_abs)
    if script_dir and script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    sys.argv = [script_abs] + script_args

    code = 0
    try:
        runpy.run_path(script_abs, run_name='__main__')
    except SystemExit as exc:
        # sys.exit() / argparse 报错：保留原始退出码语义
        if exc.code is None:
            code = 0
        elif isinstance(exc.code, int):
            code = exc.code
        else:
            # sys.exit("错误信息")：按 Python 约定打印到 stderr 并返回 1
            print(exc.code, file=sys.stderr, flush=True)
            code = 1
    except BaseException:
        # 未捕获异常：先打印栈（保持原有可见性），再记为失败
        traceback.print_exc()
        code = 1
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        _write_exit_code(code_file, code)

    return code


if __name__ == '__main__':
    sys.exit(main())
