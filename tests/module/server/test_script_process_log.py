# -*- coding: utf-8 -*-
"""`ScriptProcess` 的日志广播回归测试。

## 为什么需要

用户实测: **某个账号跑过一次之后, 它的日志就再也不显示了** ——
而"重启 server"能暂时修好。这是最难查的一类 bug: 没有异常、没有报错,
只是**静默地不再推送**。

根因有两个, 都在 `module/server/script_process.py`:

1. `start()` 里 **先设 `state = RUNNING`, 再调 `stop()`** ——
   而 `stop()` 会把 `self.state` 设回 `INACTIVE`。
   日志协程原先靠 `state != INACTIVE` 才去读管道, 于是**一直跳过**,
   日志永远推不出来。
2. 日志管道只在 `__init__` 里建一次。旧子进程退出时会 `log_pipe_in.close()`,
   写端从此关闭 -> 重启后新子进程写不出日志。
   （读端还必须是**每轮动态取**, 否则协程仍握着旧管道。）

表现: 第 1 次启动有日志, 第 2 次起 0 条。本测试就是钉住这个行为。

★ 用**真实的子进程**(`ScriptProcess.start()` 会 spawn 真进程),
  所以本测试较慢(每轮 ~12s)。这是必要的 —— 纯 mock 测不出管道问题。
"""
import asyncio
from pathlib import Path

import pytest

ACCOUNT = '伴生树'


@pytest.fixture(scope='module')
def account():
    if not (Path.cwd() / 'config' / f'{ACCOUNT}.json').exists():
        pytest.skip(f'缺少配置 {ACCOUNT}')
    return ACCOUNT


async def _drain(sp, seconds: float, sink: list) -> int:
    """轮询管道 `seconds` 秒, 把收到的日志塞进 `sink`。"""
    import time

    n = 0
    end = time.time() + seconds
    while time.time() < end:
        pipe = sp.log_pipe_out
        try:
            if pipe.closed:
                await asyncio.sleep(0.2)
                continue
            if pipe.poll():
                log = pipe.recv()
                if log:
                    sink.append(log)
                    n += 1
            else:
                await asyncio.sleep(0.1)
        except (EOFError, OSError):
            await asyncio.sleep(0.2)
    return n


@pytest.mark.timeout(120)
def test_log_flows_after_restart(account):
    """
    连续 start 两次, **两次都要有日志**。

    ★ 这条断言直接对应用户反馈: 修复前第 2 次是 0 条。
    """

    async def run():
        from module.server.script_process import ScriptProcess

        sp = ScriptProcess(account)
        sink = []

        async def fake_broadcast(log):
            sink.append(log)

        sp.broadcast_log = fake_broadcast
        try:
            # ---- 第 1 次 ----
            await sp.start()
            assert sp.state.name == 'RUNNING' or int(sp.state) == 1, \
                f'start() 之后 state 应为 RUNNING, 实际 {sp.state}'
            first = await _drain(sp, 14, sink)

            # ---- 第 2 次(内部 stop -> start, 关键场景) ----
            before = len(sink)
            await sp.start()
            # ★ state 必须还是 RUNNING —— `stop()` 不该把最终状态留成 INACTIVE
            assert int(sp.state) == 1, (
                f'第二次 start() 之后 state={sp.state}, '
                f'应为 RUNNING —— 这正是"日志不再推送"的根因')
            await _drain(sp, 14, sink)
            second = len(sink) - before

            return first, second
        finally:
            await sp.stop()

    first, second = asyncio.run(run())
    assert first > 0, f'第 1 次启动就没有日志({first} 条)'
    assert second > 0, (
        f'第 2 次启动没有日志(第1次 {first} 条, 第2次 {second} 条) —— '
        f'回归: start() 的 state/管道处理被改坏了')


@pytest.mark.timeout(120)
def test_log_coroutine_survives_process_restart(account):
    """
    广播协程**同一个实例**要能跨重启继续工作。

    `main_manager.push_data_handle()` 按 name 记任务存在与否,
    **协程一旦结束就不会重建** —— 所以协程必须自己活下来,
    不能在"进程已退出"时 `return`。
    """

    async def run():
        from module.server.script_process import ScriptProcess

        sp = ScriptProcess(account)
        sink = []

        async def fake_broadcast(log):
            sink.append(log)

        sp.broadcast_log = fake_broadcast
        task = None
        try:
            await sp.start()
            task = asyncio.create_task(sp.coroutine_broadcast_log())
            await _drain(sp, 10, sink)
            n1 = len(sink)

            # 重启(内部 stop -> start), 协程**不重建**
            await sp.start()
            await _drain(sp, 12, sink)
            n2 = len(sink) - n1

            return task.done(), n1, n2
        finally:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await sp.stop()

    done, n1, n2 = asyncio.run(run())
    assert not done, (
        '广播协程在进程重启时结束了 —— 而 main_manager 不会重建它, '
        '这会导致此后永久不再推送日志')
    assert n1 > 0, f'第 1 阶段没有日志({n1} 条)'
    assert n2 > 0, f'协程未重建时第 2 阶段没有日志({n2} 条) —— 回归'
