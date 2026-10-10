# This Python file uses the following encoding: utf-8
"""
统一标准输出/标准错误的编码为 UTF-8。

问题现象
--------
通过 OASX 启动后端时, 日志里大量中文显示为乱码(如 "伴生树" 变成 "ä¼´çæ")。

根因
----
Windows 中文版的系统 ANSI 代码页是 936(GBK), 而现代终端与 IDE 普遍按 UTF-8 读取。
当 Python 的标准输出被重定向(不是终端)时, 它按 locale 首选编码即 GBK 写出字节:
    本机实测: sys.stdout.encoding == 'gbk', 而 Console.OutputEncoding == UTF-8(CP65001)
于是"写 GBK / 读 UTF-8"造成乱码。注意日志文件本身没有问题 ——
module/logger.py 写文件时显式指定了 encoding='utf-8', 实测文件内中文完全正常;
乱码只出现在经标准输出的那一路上(控制台, 以及 OASX 捕获 stdout 时)。

修复
----
在进程启动早期把 sys.stdout / sys.stderr 重设为 UTF-8, 使"写"的一侧与
"读"的一侧(UTF-8)一致。同时设置 PYTHONIOENCODING 环境变量, 让本进程后续
spawn 的子进程(含 multiprocessing 子进程)继承同样的编码设置。

为何不改日志文件
----------------
文件侧本来就是正确的, 无需改动; 本模块只处理标准输出。

使用方式
--------
在入口(server.py / script.py)最顶部、**早于 module.logger 导入**调用:
    from module.base.encoding import setup_utf8_stdio
    setup_utf8_stdio()

注意: 旧的内置 PySide6 GUI 入口 gui.py 已移除 —— 界面统一由 OASX 承担,
它通过 server.py 的 HTTP/WebSocket 接口通信, 因此本模块只需覆盖这两个入口。
"""
import os
import sys

__all__ = ['setup_utf8_stdio']

_APPLIED = False


def setup_utf8_stdio() -> bool:
    """
    将标准输出与标准错误切到 UTF-8, 并让子进程继承该设置。

    幂等: 重复调用只会执行一次。
    安全: 任何一步失败都只记录警告, 不影响程序继续运行 —— 编码问题不应导致启动失败。

    :return: 是否至少成功处理了 stdout
    """
    global _APPLIED
    if _APPLIED:
        return True
    _APPLIED = True

    # 让本进程后续 spawn 的子进程默认使用 UTF-8。
    # 只在调用方未显式设置时写入, 避免覆盖使用者的意图。
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

    # ★★★ 先给 `None` 兜底（这一条决定"能不能启动"）★★★
    #
    # ## 现象（实测）
    #
    # OASX 启动后端用的是:
    #     .\toolkit\pythonw.exe  server.py      （见 OASX 的 server_controller.dart）
    #
    # ★ `pythonw.exe` **没有控制台** -> `sys.stdout` / `sys.stderr` 都是 **None**。
    #   而 `module/logger.py` 用 `rich` 的 `RichHandler`, 它默认往
    #   `sys.stdout` 写 -> `None.write(...)` -> `AttributeError` ->
    #   **进程在启动阶段直接死掉**。
    #
    # ★ 实测三组对照（同一台机器、同一份代码）:
    #
    #     pythonw.exe server.py              -> 进程死, 端口 22288 永不监听
    #     pythonw.exe server.py + 重定向输出  -> 正常启动
    #     python.exe  server.py              -> 正常启动（约 2 秒）
    #
    #   -> 证明差别**只在 stdout 是否存在**，与代码逻辑无关。
    #
    # ## 后果（用户报的现象）
    #
    # 后端起不来 -> 前端连不上 -> 界面显示**默认值**
    # -> 用户以为"我的配置被重置了"（其实配置一直完好）。
    #
    # ## 修法
    #
    # stdout/stderr 为 `None` 时**接到 `os.devnull`** ——
    # ★ 写日志不再崩, 而文件侧的日志（`module/logger.py` 的 FileHandler）
    #   照常记录, 所以"没有控制台"**不等于"没有日志"**。
    #
    # ⚠ 为什么在这里而不是 server.py: 本函数是**两个入口都调用**的
    #   （server.py / script.py）且已是"启动最早期"的钩子, 放在这里
    #   一次性覆盖所有入口, 不必每个入口各写一遍。
    for _name in ('stdout', 'stderr'):
        if getattr(sys, _name, None) is None:
            try:
                setattr(sys, _name,
                        open(os.devnull, 'w', encoding='utf-8'))
            except OSError:
                pass

    ok = False
    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is None:
            # 例如被替换成不支持 reconfigure 的自定义流(如 nemu_ipc 的 fdopen 流)。
            # 此时无法就地改编码, 只能依赖上面的环境变量。
            continue
        try:
            # errors='replace': 编码问题不应让脚本因 UnicodeEncodeError 崩溃
            reconfigure(encoding='utf-8', errors='replace')
            if name == 'stdout':
                ok = True
        except (ValueError, OSError, AttributeError):
            # 流已关闭或不支持该操作, 忽略
            continue

    return ok
