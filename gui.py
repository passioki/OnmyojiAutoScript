# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

# 必须先于其余导入执行: Windows 中文版下标准输出默认按 GBK 编码,
# 而终端按 UTF-8 读取, 导致日志中文乱码。详见 module/base/encoding.py
from module.base.encoding import setup_utf8_stdio

setup_utf8_stdio()

from module.gui.utils import check_admin
from module.gui.context.add import Add
from module.gui.context.settings import Setting
from module.gui.context.process_manager import ProcessManager
from module.gui.context.utils import Utils
from module.gui.register_type.paint_image import PaintImage
from module.gui.register_type.rule_file import RuleFile
from module.gui.fluent_app import FluentApp
from module.ocr.rpc import ensure_ocr_server_started

if __name__ == "__main__":
    ensure_ocr_server_started()
    # 检查是不是以管理员身份运行，脚本启动的其他进程会继承权限
    # 但是貌似有问题的这个函数
    # check_admin()
    # 启动一个UI交互的线程，因为信号槽不可跨进程
    # 后面选择注入上下文快
    app = FluentApp()
    add_config = Add()
    setting = Setting()
    process_manager = ProcessManager()
    utils = Utils()

    app.set_context_property(setting, 'setting')
    app.set_context_property(add_config, 'add_config')
    app.set_context_property(process_manager, 'process_manager')
    app.set_context_property(utils, 'utils')
    app.qml_register_type(PaintImage, 'PaintImage')
    app.qml_register_type(RuleFile, 'RuleFile')
    # 启动一个GUI
    app.run()
