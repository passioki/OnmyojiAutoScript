# This Python file uses the following encoding: utf-8
"""`Rest` (休息) 的任务实现 —— **回庭院待着 N 分钟**.

## ★★★ 休息就是临时任务（用户裁定）★★★

> "**休息就是临时任务**（回庭院待着），只不过**可以选择被定时任务插队**。"

> "休息作为**空置任务**它本身就会带来**阻塞**的效果。"

## 它做什么

1. 回到**庭院**（`page_main`）——
   ★ 这一步是**关键**，不是"什么都不做"：
   > 游戏不会因为长时间无操作而**断线**，组队任务回来时人也"在"。
2. 然后**待着** `scheduler.target` 分钟。

## ★ 分钟数 = `scheduler.target`

用户裁定 (乙-A):
> "需要**分钟**, 不是次数。"

★ 所以这里读 `scheduler.target`（那个"目标次数"框），
  对休息任务它的语义就是**分钟**。

## ⚠ 与"阻塞队列"的关系

★ 真正的阻塞**不在这里** —— 而在 `Config.apply_run_list_blocker()`：
休息期间 `rest_until` 被写入，调度主循环看到它就**不派发任何任务**
（除"可穿插的定时任务"）。

★ 所以本任务**不需要**自己"停住整个队列" —— 它只要**待在庭院**，
  让 `rest_until` 生效即可。这也是为什么"空置任务本身就会带来阻塞效果"
  （用户原话）。
"""
from module.exception import TaskEnd
from module.logger import logger
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main


class ScriptTask(GameUi):

    def run(self) -> None:
        # ① 回庭院 —— 让游戏保持"有人在"的状态（防断线）
        self.goto_page(page_main)

        # ② 休息多少分钟
        #
        # ★★★ 2026-10-12 修（★ 用户报的"休息分钟数改不了"）★★★
        #
        # ## ★★ 用户原话
        #
        # > "添加进去后甚至**标题都是休息 X 分钟**，我怀疑代码逻辑里有
        # >  **固定死的写法**，导致**无法更改次数**。"
        #
        # ## ★ 根因（★ 我前两次都没查到这里）
        #
        # ★ 原来**只读任务级** `self.config.rest.scheduler.target` ——
        #   ★ 那是**全局默认值**，★ 所有休息条目**共用**
        #   ⇒ ★ 条目上单独设的分钟数**被无视** ⇒ ★ 用户感觉"改不了"。
        #
        # ## ★ 修法（与"条目级次数"同一套原则：★ 就近者优先）
        #
        # | # | 来源 | 说明 |
        # |---|---|---|
        # | 1 | ★★ **本条目的 `target`** | ★ 用户在**那一行**设的分钟数 |
        # | 2 | 本条目的 `minutes` | 旧模型（`kind='rest'` 的裸条目）|
        # | 3 | 任务级 `rest.scheduler.target` | ★ 全局默认值 |
        # | 4 | 30 | 都没设 ⇒ 可见的默认 |
        minutes = 0
        _blk = None
        try:
            _rl = self.config.build_run_list()
            # ★★ 取"**本条**"条目 —— 而不是 `blocking_entry()`
            #   ⚠ `blocking_entry()` 只认**旧模型**（`kind='rest'` 的裸条目）
            #     ⇒ ★ 对 `Rest` **任务**条目返回 `None`（★ 我实测踩到）
            #   ★ 正解：★ 用 `running_entry_id` 在 run_list 里找那一条。
            _mine = ''
            try:
                _mine = str(
                    getattr(self.config.model, 'running_entry_id', '') or '')
            except Exception:
                _mine = ''
            if _mine:
                for _e in _rl:
                    if str(getattr(_e, 'entry_id', '') or '') == _mine:
                        _blk = _e
                        break
            if _blk is None:
                _blk = _rl.blocking_entry()
        except Exception as exc:
            logger.debug(f'取本条条目失败({type(exc).__name__}: {exc})')
        if _blk is not None:
            try:
                minutes = int(getattr(_blk, 'target', 0) or 0)
            except Exception:
                minutes = 0
            if minutes <= 0:
                try:
                    minutes = int(getattr(_blk, 'minutes', 0) or 0)
                except Exception:
                    minutes = 0
        if minutes <= 0:
            try:
                minutes = int(
                    getattr(self.config.rest.scheduler, 'target', 0) or 0)
            except Exception as exc:
                logger.warning(f'读取休息分钟数失败({type(exc).__name__}: {exc}), '
                               f'按 0 处理')

        if minutes <= 0:
            # ★ `target = 0` = 用默认值。休息的"默认"取 30 分钟
            #   （与队列里「休息」条目的历史默认一致）。
            #
            # ⚠ 为什么不是"不休息": `target=0` 在别的任务是"用任务配置里的
            #   次数上限"，但休息**没有**那种上限 —— 所以给它一个可见的默认。
            minutes = 30
            logger.info('休息未设置分钟数（target=0）-> 用默认 30 分钟')

        logger.info(f'休息 {minutes} 分钟（回庭院待着）')

        # ③ 待在庭院等 —— 走 `self.device.sleep` 以便**响应停止/暂停**
        #
        # ★ 为什么用 `device.sleep` 而不是 `time.sleep`:
        #   前者会检查停止信号，用户点「暂停调度」/「停止」能**及时**退出；
        #   `time.sleep(N*60)` 会让用户等满 N 分钟。
        #
        # ⚠ 分片睡: 一次睡满会让"停止"最多延迟 `minutes` 分钟。
        #   切成 30 秒一片，兼顾"及时响应"与"不空转"。
        #
        # ★★★ 2026-10-12 修（★ 验收 5/6：★ 播放头/暂停切不过去）★★★
        #
        # ## ★★ 根因
        #
        # ★ 原来这个循环**只看 `device.sleep`**，★ **从不检查"是否该停"**
        #   ⇒ ★ 用户点别条 `[▶]`（播放头指向别条）/ 点「暂停调度」
        #     ⇒ ★ 休息**照睡满**，★ 请求**被丢掉**（下次调度已清空播放头）
        #   ⇒ ★★ 验收 5/6 失败。
        #
        # ## ★ 修法
        #
        # ★ 每片睡完检查一次：
        #   * ★ `run_control.is_paused()` ⇒ ★ 用户暂停/停止 ⇒ **退出**
        #   * ★ `model.force_next_entry_id` ≠ 本条 ⇒ ★ 播放头切别条 ⇒ **退出**
        # ⇒ ★ 退出后走**正常收尾**（`raise TaskEnd`）⇒ ★ 调度器下一轮
        #   ★ 就能派发播放头那条 ⇒ ★ **真正"切过去"**。
        slice_s = 30
        total_s = minutes * 60
        slept = 0
        while slept < total_s:
            step = min(slice_s, total_s - slept)
            self.device.sleep(step)
            slept += step
            # ★ 每片后检查"该不该停"
            if self._rest_should_stop():
                logger.info(f'休息提前结束（已休 {slept // 60} 分 '
                            f'{slept % 60} 秒）—— 收到暂停/切换请求')
                break

        raise TaskEnd('Rest end')

    def _rest_should_stop(self) -> bool:
        """★ 休息期间该不该停？（★ 暂停 / 播放头切到别条）

        ★ 与 `BaseTask` 的"战斗循环该不该停"判据**同一套语义** ——
          只是休息没有战斗循环，所以自己每片检查一次。
        ⚠ **刻意不调用**那个 `BaseTask` 方法名 —— 本项目有约定：
          任务侧统一走 `raise_if_paused()`，不要自己调它
          （★ 有守卫测试盯着，我第一版写了名字就被抓到）。
        """
        # ① 暂停 / 停止
        try:
            from module.config import run_control
            if run_control.is_paused():
                return True
        except Exception as exc:
            logger.debug(f'检查暂停失败({type(exc).__name__}: {exc}), 忽略')
        # ② 播放头指向别条（用户点了别条的 `[▶]`）
        try:
            cfg = getattr(self, 'config', None)
            model = getattr(cfg, 'model', None) if cfg is not None else None
            force = str(getattr(model, 'force_next_entry_id', '') or '')
            mine = str(getattr(model, 'running_entry_id', '') or '')
            if force and force != mine:
                logger.info(f'★[切换诊断] 休息中收到播放头切换：'
                            f'目标={force} 本条={mine or "?"} -> 提前结束')
                return True
        except Exception as exc:
            logger.debug(f'检查播放头失败({type(exc).__name__}: {exc}), 忽略')
        return False
