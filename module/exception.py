class CampaignEnd(Exception):
    pass


class MapDetectionError(Exception):
    pass


class MapWalkError(Exception):
    pass


class MapEnemyMoved(Exception):
    pass


class CampaignNameError(Exception):
    pass


class ScriptError(Exception):
    # This is likely to be a mistake of developers, but sometimes a random issue
    pass


class ScriptEnd(Exception):
    pass


class GameStuckError(Exception):
    pass


class GameBugError(Exception):
    # An error has occurred in Azur Lane game client. Alas is unable to handle.
    # A restart should fix it.
    pass


class GameTooManyClickError(Exception):
    pass


class EmulatorNotRunningError(Exception):
    pass


class GameNotRunningError(Exception):
    pass


class GamePageUnknownError(Exception):
    pass


class RequestHumanTakeover(Exception):
    # Request human takeover
    # Alas is unable to handle such error, probably because of wrong settings.
    pass

class TaskEnd(Exception):
    pass


class TaskPaused(BaseException):
    """★★★ 收到「暂停调度」请求 —— **在安全点中断当前任务** ★★★

    ## 为什么需要它（实测出的真 bug）

    「暂停调度」原本靠**协作式安全点**实现:

    * `script.py` 在**任务之间**检查（`_handle_run_control`, 这个没问题）
    * `tasks/base_task.py` 的 `should_stop_battle_loop()` 在**战斗循环里**检查

    ⚠ **但只有 15/54 个任务调用了它** —— 实测:

    * `run_general_battle()` 里**有**安全点（`general_battle.py:77`），
      它 `return True` 并把 `self._pause_requested` 置位
    * ★ 可是 **50 处调用点丢弃了返回值**（`self.run_general_battle(...)`)
      -> 安全点的信号**被无声忽略**
    * ★ 而且 `_pause_requested` **全项目只被写、从不被读**
      （6 处引用: 1 初始化 + 1 判据 + 3 写入 + 1 注释）

    **后果**: 用户点「暂停调度」后, 大多数任务**完全不响应**, 一直跑到自己结束。
    这正是用户报的"**暂停调度并没有实现**"。

    ## 为什么用 `BaseException` 而不是 `Exception`

    ★ 任务代码里有大量 `except Exception`（兜底容错）。若继承 `Exception`,
      它们会把暂停请求**吞掉** -> 又变成"点了没用"。
    ★ `BaseException` 只被**明确的**处理者接住（`script.py` 的 `run()`）。

    ## 谁抛

    * `BaseTask.should_stop_battle_loop()` —— 27 处已有调用点直接生效
      （原来它们 `if ...: break`, 现在异常会直接穿出去, 效果相同）
    * `run_general_battle()` —— **兜底**那 50 个丢弃返回值的地方

    ## 谁接（★ 关键: 不能跳过收尾）

    `script.py` 的 `run()` —— 那里已有任务收尾的 `finally`
    （与 `TaskEnd` 同一层, 照它的做法）。任务自己的收尾逻辑
    （退房间/回庭院/`commit_count`/`set_next_run`）**照常执行**,
    所以**不会卡在半途**（见 `docs/architecture.md` §6.1）。

    ## 接住之后

    不结束进程, 只是让 `run()` 返回 -> 回到 `loop()` 的
    `_handle_run_control()`, 那里会**阻塞等待**用户点「继续」。
    """
    pass
