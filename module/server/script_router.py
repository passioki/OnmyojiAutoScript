# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
from module.config.utils import convert_to_underscore

from module.logger import logger
from module.server.main_manager import mm
from module.server.script_process import ScriptProcess, ScriptState

from tasks.Component.config_base import TimeDelta


script_app = APIRouter()


@script_app.get('/test')
async def script_test():
    return 'success'

@script_app.get('/script_menu')
async def script_menu():
    return mm.config_cache('template').gui_menu_list
# ----------------------------------   配置文件管理   ----------------------------------
@script_app.get('/config_list')
async def config_list():
    return mm.all_script_files()

@script_app.post('/config_copy')
async def config_copy(file: str, template: str = 'template'):
    mm.copy(file, template)
    return mm.all_script_files()

@script_app.get('/config_new_name')
async def config_new_name():
    return mm.generate_script_name()

@script_app.get('/config_all')
async def config_all():
    return mm.all_json_file()


@script_app.put('/config')
async def config_rename(old_name: str = '', new_name: str = ''):
    """
    update config name
    :param old_name: old config name
    :param new_name: new config name
    :return: True or False
    """
    if old_name == new_name or new_name == '':
        return False
    if old_name in mm.script_process:
        if mm.script_process[old_name].state != ScriptState.INACTIVE:
            # 必须 await: 否则旧配置的子进程不会被终止, 重命名后它会继续在后台操作模拟器。
            await mm.script_process[old_name].stop()
        del mm.script_process[old_name]
    if not mm.rename(old_name, new_name):
        raise HTTPException(status_code=400, detail='Rename failed')
    return True


@script_app.delete('/config')
async def config_delete(name: str = ''):
    """
    delete config file
    :param name: config name
    :return: True or False
    """
    if name == '' or name == 'template':
        raise HTTPException(status_code=400, detail='Delete failed')
    if name in mm.script_process:
        if mm.script_process[name].state != ScriptState.INACTIVE:
            # 必须 await: 否则删除配置后子进程仍在运行, 变成无人管理的孤儿进程。
            await mm.script_process[name].stop()
        del mm.script_process[name]
    if not mm.delete(name):
        raise HTTPException(status_code=400, detail='Delete failed')
    return True


@script_app.put('/config/task/copy')
async def task_copy(task_name: str, dest_config_name: str, source_config_name: str):
    if dest_config_name not in mm.script_process or source_config_name not in mm.script_process:
        return False
    source_task = getattr(mm.config_cache(source_config_name).model, convert_to_underscore(task_name), None)
    if source_task is None:
        return False
    return mm.config_cache(dest_config_name).model.copy_script_task(task_name, source_task)


@script_app.put('/config/task/group/copy')
async def task_group_copy(task_name: str, group_name: str, dest_config_name: str, source_config_name: str):
    if dest_config_name not in mm.script_process or source_config_name not in mm.script_process:
        return False
    source_task = getattr(mm.config_cache(source_config_name).model, convert_to_underscore(task_name), None)
    if source_task is None:
        return False
    return mm.config_cache(dest_config_name).model.copy_task_group(task_name, group_name, source_task)


# ---------------------------------   脚本实例管理   ----------------------------------
@script_app.get('/{script_name}/start')
async def script_start(script_name: str):
    if script_name not in mm.script_process:
        mm.script_process[script_name] = ScriptProcess(script_name)
    # ScriptProcess.start() 是 async 的, 漏掉 await 会让协程被创建后直接丢弃,
    # 表现为"点了启动没有反应"且不留下任何日志。
    await mm.script_process[script_name].start()
    return

@script_app.get('/{script_name}/stop')
async def script_stop(script_name: str):
    if script_name not in mm.script_process:
        logger.warning(f'[{script_name}] script process does not exist')
        return
    # 同上: 漏掉 await 会让停止变成空操作, 子进程会一直留在后台继续操作模拟器。
    await mm.script_process[script_name].stop()
    return

@script_app.get('/{script_name}/{task}/args')
async def script_task(script_name: str, task: str):
    return mm.config_cache(script_name).model.script_task(task)


@script_app.get('/{script_name}/task_status')
async def script_task_status(script_name: str, task: str = '', peer: str = ''):
    """
    任务状态总览: 调度器时间 + 完成记忆(period) + 挑战次数, 一次取全。

    背景: 完成记忆与次数存在 module/config/task_state.py 的状态文件里, 但此前
    没有任何 HTTP 出口(WS 只推 {name, next_run}), 因此界面无法显示
    "本周期是否已完成""还剩几次"。本接口把它们暴露出来。

    :param script_name: 配置名(账号)
    :param task: 可选, 单个任务(下划线形式); 留空返回该账号全部任务
    :param peer: 可选, 只看指定对方账号
    :return: {config, at, tasks:[{name,command,enable,period,priority,next_run,
             slot,last_success,completed}], peers:[{config,online}]}
    """
    from module.config import task_state

    config = mm.config_cache(script_name)
    now = datetime.now()

    try:
        config.update_scheduler()
    except Exception as exc:
        logger.warning(f'task_status: update_scheduler 失败: {exc}')

    def _slot_of(command: str) -> str:
        for bucket, attr in (('pending', 'pending_task'), ('waiting', 'waiting_task')):
            for f in getattr(config, attr, None) or []:
                if getattr(f, 'command', None) == command:
                    return bucket
        return ''

    summary = task_state.summarize(script_name, now=now)
    state_bucket = summary.get('global') or {}

    wanted = convert_to_underscore(task) if task else ''
    tasks = []
    for key, value in config.model.model_dump().items():
        if not isinstance(value, dict):
            continue
        scheduler = value.get('scheduler')
        if not isinstance(scheduler, dict):
            continue
        if wanted and key != wanted:
            continue

        command = ''.join(p.capitalize() for p in key.split('_'))
        period = scheduler.get('period')
        period_str = getattr(period, 'value', period) or 'none'
        rec = state_bucket.get(key) or {}

        tasks.append({
            'name': key,
            'command': command,
            'enable': bool(scheduler.get('enable')),
            'period': period_str,
            'priority': scheduler.get('priority'),
            'next_run': str(scheduler.get('next_run') or ''),
            'slot': _slot_of(command),
            'last_success': rec.get('last_success'),
            'completed': bool(rec.get('period_key')) and period_str != 'none',
        })

    peers = task_state.peers_status(script_name, task=wanted or None, now=now)
    if peer:
        peers = [p for p in peers if p.get('config') == peer]

    return {
        'config': script_name,
        'at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'tasks': tasks,
        'peers': peers,
    }


@script_app.get('/{script_name}/common_groups')
async def script_common_groups(script_name: str, min_tasks: int = 2):
    """
    列出被多个任务重复使用的字段分组("公共分组")。

    动机: 实测 56 个任务共下发 1402 个字段, 其中 4 类公共分组占 60.9% ——
    仅 scheduler 一个 10 字段分组就被逐字复制 54 份。用户要在多个任务上用同一
    设置时只能逐页改; 本接口给出"哪些分组是公共的、被哪些任务用、有哪些字段",
    供前端做批量修改。
    """
    groups = mm.config_cache(script_name).gui_common_groups(min_tasks=min_tasks)
    return {'config': script_name, 'min_tasks': min_tasks, 'groups': groups}


@script_app.put('/{script_name}/common/{group}/{argument}/value')
async def script_common_arg(script_name: str, group: str, argument: str,
                            types: str, value, only_tasks: str = '',
                            exclude_tasks: str = ''):
    """
    把公共分组里的某个参数一次写入**所有引用该分组的任务**。

    例: group=scheduler, argument=float_time, types=time, value=00:03:00
        -> 所有含 scheduler 的任务的"防封浮动时间"都会被设为 3 分钟。

    :param only_tasks: 可选, 逗号分隔的任务名(下划线形式), 只写这些
    :param exclude_tasks: 可选, 逗号分隔的任务名, 排除这些
    """
    try:
        if types == 'integer':
            value = int(value)
        elif types == 'number':
            value = float(value)
        elif types == 'boolean':
            if isinstance(value, str):
                if value.lower() in ['true', '1']:
                    value = True
                elif value.lower() in ['false', '0']:
                    value = False
            value = bool(value)
        elif types == 'time':
            value = datetime.strptime(value, '%H:%M:%S').time()
        elif types == 'date_time':
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        elif types == 'time_delta':
            day = int(value[1])
            dt = datetime.strptime(value[3:], '%H:%M:%S')
            value = TimeDelta(days=day, hours=dt.hour, minutes=dt.minute,
                              seconds=dt.second)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Argument type error: {e}')

    only = [t for t in (only_tasks or '').split(',') if t.strip()]
    exclude = [t for t in (exclude_tasks or '').split(',') if t.strip()]
    result = mm.config_cache(script_name).set_common_arg(
        group, argument, value,
        only_tasks=only or None, exclude_tasks=exclude or None)
    result['config'] = script_name
    result['group'] = group
    result['argument'] = argument
    return result


@script_app.put('/{script_name}/{task}/{group}/{argument}/value')
async def script_task(script_name: str, task: str, group: str, argument: str, types: str, value):
    try:
        match types:
            case 'integer':
                value = int(value)
            case 'number':
                value = float(value)
            case 'boolean':
                if isinstance(value, str):
                    logger.warning(f'[{script_name}] script argument {argument} value is string, try to convert to bool')
                    if value.lower() in ['true', '1']:
                        value = True
                    elif value.lower() in ['false', '0']:
                        value = False
                value = bool(value)
            case 'string':
                pass
            case 'date_time':
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            case 'time_delta':
                # strptime 是个好东西，但是不能解析00的天数
                day = int(value[1])
                date_time = datetime.strptime(value[3:], '%H:%M:%S')
                value = TimeDelta(days=day, hours=date_time.hour, minutes=date_time.minute, seconds=date_time.second)
            case 'time':
                value = datetime.strptime(value, '%H:%M:%S').time()
            case _: pass
    except Exception as e:
        # 类型不正确
        raise HTTPException(status_code=400, detail=f'Argument type error: {e}')
    return mm.config_cache(script_name).model.script_set_arg(task, group, argument, value)


@script_app.put('/{script_name}/{task}/sync_next_run')
async def sync_next_run(script_name: str, task: str, target_dt: str):
    if script_name not in mm.script_process:
        return False
    config = mm.config_cache(script_name)
    target = datetime.strptime(target_dt, '%Y-%m-%d %H:%M:%S') if target_dt else None
    config.task_delay(task=task, success=True, target=target)
    script_process = mm.script_process[script_name]
    config.get_next()
    await script_process.broadcast_state({"schedule": config.get_schedule_data()})
    return True


# --------------------------------------  SSE  --------------------------------------
@script_app.get('/{script_name}/state')
async def script_task_state(script_name: str):
    async def state_generate_events():
        while True:
            # 生成 SSE 事件数据
            event_data = "data: Hello, SSE!\n\n"
            yield event_data

            # 模拟异步操作，可以替换为您的实际处理逻辑
            await asyncio.sleep(1)

    response = StreamingResponse(state_generate_events(), media_type="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    return response

@script_app.get('/{script_name}/log')
async def script_task_log(script_name: str):
    async def log_generate_events():
        while True:
            # 生成 SSE 事件数据
            event_data = "data: log\n"
            yield event_data

            # 模拟异步操作，可以替换为您的实际处理逻辑
            await asyncio.sleep(1)

    response = StreamingResponse(log_generate_events(), media_type="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    return response

# -------------------------------------- websocket --------------------------------------

@script_app.websocket("/ws/{script_name}")
async def websocket_endpoint(websocket: WebSocket, script_name: str):
    if script_name not in mm.script_process:
        mm.script_process[script_name] = ScriptProcess(script_name)
    script_process = mm.script_process[script_name]
    await script_process.connect(websocket)

    try:
        await script_process.send_json(websocket, {"state": script_process.state})
        config = mm.config_cache(script_name)
        config.get_next()
        await script_process.send_json(websocket, {"schedule": config.get_schedule_data()})

        while True:
            # 初次进入，广播state schedule
            data = await websocket.receive_text()
            if data == 'get_state':
                await script_process.broadcast_state({"state": script_process.state})
            elif data == 'get_schedule':
                config = mm.config_cache(script_name)
                config.get_next()
                await script_process.broadcast_state({"schedule": config.get_schedule_data()})
            elif data == 'start':
                await script_process.start()
            elif data == 'stop':
                await script_process.stop()

    except WebSocketDisconnect:
        logger.warning(f'[{script_name}] websocket disconnect')
        await script_process.disconnect(websocket)
    except Exception as e:
        logger.exception(f'[{script_name}] websocket error: {e}')
        await script_process.disconnect(websocket)
