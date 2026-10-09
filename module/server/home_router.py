# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import json
from fastapi import APIRouter, Body
from pathlib import Path

from module.config.utils import write_file
from module.logger import logger
from module.ocr.rpc import shutdown_ocr_server
from module.server.main_manager import MainManager
from module.server.updater import Updater
from module.server.i18n import I18n

home_app = APIRouter(
    prefix="/home",
    tags=["home"],
)


@home_app.get('/test')
async def home_test():
    return {'message': 'test'}


#  gcc -Wall -pedantic -shared -fPIC -o group_work.so group_work.c -lwiringPi
@home_app.get('/home_menu')
async def home_menu():
    return {'Home': [], 'Updater': [], 'Tool': []}


@home_app.post('/notify_test')
async def notify_test(setting: str, title: str, content: str):
    from module.notify.notify import Notifier
    try:
        notifier = Notifier(setting, True)
        if notifier.push(title=title, content=content):
            del notifier
            return True
        else:
            del notifier
            return False
    except Exception as e:
        logger.exception(e)
        return str(e)


@home_app.get('/kill_server')
async def kill_server():
    shutdown_ocr_server()
    MainManager.signal_kill_server = True
    return 'success'


@home_app.get('/update_info')
async def update_info():
    try:
        updater = Updater()
        result = {'is_update': updater.check_update(),
                  'branch': updater.current_branch(),
                  'current_commit': updater.current_commit(),
                  'latest_commit': updater.latest_commit(),
                  'commit': updater.get_commit(n=15),
                  }
        return result
    except Exception as e:
        logger.error(e)
        return None


@home_app.get('/execute_update')
async def execute_update():
    # 下拉仓库 -> 关闭所有脚本进程 -> 最后重启oasx
    try:
        updater = Updater()
        updater.execute_pull()
    except Exception as e:
        logger.error(e)
    return '手动更新将会立即结束运行中的脚本服务, 最后你还需重启oasx'


@home_app.put('/chinese_translate')
async def chinese_translate(data: dict = Body(...)):
    """
    ⚠ **不要再用这个接口覆盖整份翻译表。**

    背景(踩过的坑): OASX 启动时会 `PUT` 它自己那份 `i18n_cn.dart`(746 条),
    而这里做的是 `I18n.save_zh_cn(data)` —— **整份覆盖**。
    结果是 `module/config/i18n/zh-CN.json`(1090 条)每次启动都被削到 746 条,
    **丢 344 条**。翻译也就永远补不齐。

    现在改为**增量合并**: 只补充"后端还没有的 key",
    **绝不删除**后端已有的条目。整份覆盖请用 `PUT /home/chinese_translate/replace`。
    """
    try:
        existing = I18n.load_zh_cn()
        added = {k: v for k, v in (data or {}).items()
                 if k not in existing or not existing[k]}
        if added:
            existing.update(added)
            I18n.save_zh_cn(existing)
        logger.info(f'chinese_translate: 合并 {len(added)} 条新增, '
                    f'现有 {len(existing)} 条')
    except Exception as e:
        logger.error(e)
    return True


@home_app.put('/chinese_translate/replace')
async def chinese_translate_replace(data: dict = Body(...)):
    """**整份替换**翻译表(危险, 会丢掉 data 里没有的 key)。

    只在明确知道自己在做什么时使用; 正常流程不需要它。
    """
    try:
        I18n.save_zh_cn(data)
    except Exception as e:
        logger.error(e)
    return True


@home_app.get('/chinese_translate')
async def chinese_translate_all() -> dict:
    """
    **权威全量**的中文翻译表(单一数据源)。

    OASX 启动时改为**拉取它**, 而不是推自己那份 —— 这样:
      * 翻译只有一处维护(`module/config/i18n/zh-CN.json`)
      * 前端缺什么, 后端补一次就全局生效
      * 不会再出现"前端覆盖后端"导致条目丢失

    含 `module/config/i18n/zh-CN.json` 与 `assets/i18n/zh-CN.json` 两层,
    后者优先(它是额外的补充词条)。
    """
    try:
        merged = dict(I18n.load_zh_cn())
        additions = I18n.load_additions().get('zh-CN') or {}
        merged.update(additions)
        return merged
    except Exception as e:
        logger.error(e)
    return {}


@home_app.post('/missing_translate')
async def missing_translate(data: dict = Body(...)) -> dict:
    """
    接收**前端运行时发现缺失的翻译 key**。

    ## 为什么需要

    界面文案是 `Text(model.title.tr)` —— GetX 的 `.tr` 在**查不到 key 时
    原样返回 key**，于是 `charge_enable_help` 就赤裸裸显示在界面上，
    **没有任何报错**。这种"静默降级"正是翻译长期补不齐的原因之一。

    前端现在会记录未命中的 key 并上报到这里；后端写到
    `log/missing_translate.txt`（去重、带计数），便于持续补齐。

    :param data: {"keys": ["key1", "key2", ...]}
    :return: {"accepted": n, "file": 路径}
    """
    from pathlib import Path as _Path
    keys = (data or {}).get('keys') or []
    if not isinstance(keys, list):
        return {'accepted': 0, 'file': ''}
    keys = [str(k) for k in keys if k][:500]

    out = _Path.cwd() / 'log' / 'missing_translate.txt'
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        known = set()
        if out.exists():
            for line in out.read_text(encoding='utf-8').splitlines():
                if '|' in line:
                    known.add(line.split('|', 1)[0].strip())
        new = [k for k in keys if k not in known]
        if new:
            with open(out, 'a', encoding='utf-8') as f:
                for k in new:
                    f.write(f'{k}|前端上报\n')
            logger.warning(f'缺失的翻译 key ({len(new)} 个新): {new[:10]}')
    except Exception as e:
        logger.error(e)
    return {'accepted': len(keys), 'file': str(out)}


@home_app.get('/additional_translate')
async def additional_translate() -> dict:
    try:
        data = I18n.load_additions()
        return data
    except Exception as e:
        logger.error(e)
    return {}


@home_app.get('/export_diagnostic')
async def export_diagnostic(config_name: str = ''):
    from module.server.diagnostic import build_diagnostic_zip
    try:
        zip_path = build_diagnostic_zip(config_name)
        return {'success': True, 'path': str(zip_path)}
    except Exception as e:
        logger.exception(e)
        return {'success': False, 'path': '', 'error': str(e)}
