# -*- coding: utf-8 -*-
"""(b) 动态 days: `AvailabilityWindow.days_from_config` + 运行时解析。

用户裁定:
> "窗口是唯一排期依据, 这个 B 并不冲突吧, **窗口仍然是唯一排期依据**。
>  (b) **AvailabilityWindow 支持动态 days（运行时从配置读）**
>   让窗口能**引用配置字段**"
"""
from pathlib import Path

# ---------- ① AvailabilityWindow 加字段 ----------
P = Path(r'D:\OAS-dev\OnmyojiAutoScript\module\config\availability.py')
t = P.read_text(encoding='utf-8')

OLD = """    # ★ 空元组 = 不限月内日（**不是**"都不允许"）
    days_of_month: tuple = ()"""
NEW = """    # ★ 空元组 = 不限月内日（**不是**"都不允许"）
    days_of_month: tuple = ()
    # ★★ 动态 days（用户裁定 (b)）: 运行时从**任务配置**读星期 ★★
    #
    # 值是 `Config` 上的点分路径**元组**, 每项指向一个"星期"字段, 如:
    #     ('guild_banquet.guild_banquet_time.day_1',
    #      'guild_banquet.guild_banquet_time.day_2')
    #
    # `Config.resolve_windows()` 在运行时读成 0-6 的整数, 与静态 `days`
    # **取并集** —— 于是**窗口仍是唯一排期依据**, 只是它的 `days` 可能
    # **运行时求值**（用户原话: "这个 B 并不冲突"）。
    days_from_config: tuple = ()"""
assert OLD in t, 'AvailabilityWindow 字段未匹配'
t = t.replace(OLD, NEW, 1)

# 校验
OLD2 = """        # 月内日: 1-31; 空 = 不限
        if self.days_of_month:"""
NEW2 = """        # 动态 days: 每项必须是"非空的配置路径字符串"
        if self.days_from_config:
            for pth in self.days_from_config:
                if not isinstance(pth, str) or not pth.strip():
                    raise ValueError(
                        f'days_from_config 的项必须是配置路径字符串, '
                        f'实际 {pth!r}')
            object.__setattr__(
                self, 'days_from_config',
                tuple(str(pth).strip() for pth in self.days_from_config))
        # 月内日: 1-31; 空 = 不限
        if self.days_of_month:"""
assert OLD2 in t, '__post_init__ 未匹配'
t = t.replace(OLD2, NEW2, 1)

# describe: 标出"来自配置"
OLD3 = """        if len(self.days) == 7:
            return f'每天 {span}'
        names = ''.join(DAY_NAMES[d] for d in self.days)
        return f'{names} {span}'"""
NEW3 = """        if len(self.days) == 7 and not self.days_from_config:
            return f'每天 {span}'
        names = ''.join(DAY_NAMES[d] for d in self.days)
        if self.days_from_config:
            # ★ 实际值**运行时**才知道 -> 标出来, 别让界面显示错的星期
            names = f'{names}+配置' if names else '来自配置'
        return f'{names} {span}'"""
assert OLD3 in t, 'describe 未匹配'
t = t.replace(OLD3, NEW3, 1)

# is_unrestricted: 有动态项 -> 保守地不当作"不限"
OLD4 = """        if len(self.days) != 7 or self.restricts_month_day:
            return False"""
NEW4 = """        if len(self.days) != 7 or self.restricts_month_day:
            return False
        if self.days_from_config:
            # 动态 days 运行时才知道 -> 保守地**不**当作"不限"
            return False"""
assert OLD4 in t, 'is_unrestricted 未匹配'
t = t.replace(OLD4, NEW4, 1)

P.write_text(t, encoding='utf-8')
print('  OK availability.py: days_from_config 已加')

# ---------- ② Config: 运行时解析 ----------
C = Path(r'D:\OAS-dev\OnmyojiAutoScript\module\config\config.py')
tc = C.read_text(encoding='utf-8')

ANCHOR = '    def in_window(self'
assert ANCHOR in tc, '找不到 in_window'

RESOLVER = '''    # ------------------------------------------------------------------ 动态窗口
    def resolve_windows(self):
        """把**动态** `days`（`days_from_config`）在**运行时**解析成实际星期。

        ★ 用户裁定 (b):
          "AvailabilityWindow 支持动态 days（运行时从配置读）, 让窗口能引用配置字段"
          "窗口是唯一排期依据, 这个 B 并不冲突"

        例: `GuildBanquet` 的宴会日是**用户在任务配置里选的**:
            guild_banquet.guild_banquet_time.day_1 = 星期三
            guild_banquet.guild_banquet_time.day_2 = 星期六

        本方法把它们读成 0-6 的整数, 与静态 `days` **取并集**, 返回新的
        `AvailabilityWindow` 元组。没有动态项时**原样返回**（零开销）。

        解析失败（路径不存在 / 值不是星期枚举）-> 记 WARNING 并**跳过该项**
        （不让配置错误让任务完全跑不了 —— 与 `in_window` 的容错策略一致）。
        """
        out = []
        for w in (self.windows or ()):
            paths = tuple(getattr(w, 'days_from_config', ()) or ())
            if not paths:
                out.append(w)
                continue
            extra = set()
            for path in paths:
                try:
                    node = self.model
                    for part in str(path).split('.'):
                        node = getattr(node, part)
                    # 值可能是 `Weekday` 枚举（星期三）或已经是 0-6
                    val = getattr(node, 'value', node)
                    idx = _WEEKDAY_INDEX.get(str(val))
                    if idx is None:
                        idx = WEEKDAY_INDEX.get(str(val))
                    if idx is None:
                        idx = int(node)          # 已经是 0-6
                    extra.add(int(idx))
                except Exception as exc:
                    logger.warning(
                        f'{self.command}: 动态窗口路径 {path!r} 解析失败'
                        f'（{type(exc).__name__}: {exc}）, 已跳过')
            if not extra:
                out.append(w)
                continue
            try:
                merged = tuple(sorted(set(w.days) | extra))
                out.append(AvailabilityWindow(
                    enabled=w.enabled, start=w.start, end=w.end,
                    days=merged, days_of_month=w.days_of_month,
                    days_from_config=()))
            except Exception as exc:
                logger.warning(f'{self.command}: 合并动态星期失败'
                               f'（{type(exc).__name__}: {exc}）, 用原窗口')
                out.append(w)
        return tuple(out)

'''
tc = tc.replace(ANCHOR, RESOLVER + ANCHOR, 1)
C.write_text(tc, encoding='utf-8')
print('  OK config.py: resolve_windows() 已加')
