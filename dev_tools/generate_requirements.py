# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
"""从 requirements-in.txt 生成 requirements.txt。

## 改动说明(死代码清扫)

原先有一个 `--qml` 参数, 用来决定要不要从 `requirements-in.txt` 里
**删掉 `pyside6==6.4.3`** —— 那是旧的内置 PySide6/QML GUI 的依赖。

该 GUI 已移除(见 `docs/architecture.md`), **PySide6 也早已不在依赖里**,
因此 `--qml` 的两条分支现在做的是同一件事, 而且:
  * 第一条的 `replace("pyside6==6.4.3\n", "")` 是**空操作**(文件里没这行)
  * 第二条(`qml=True`)有 bug: `content.index("pyside6==6.4.3\n")` 的结果
    **没有赋值**, 找不到时还会抛 `ValueError` —— 即"什么都不做、但可能崩"

已整体删除, 只保留真正需要的步骤。
"""
import argparse
import subprocess

from module.logger import logger


def generate():
    """规范化 requirements-in.txt, 再用 pip-compile 生成 requirements.txt。"""
    with open("requirements-in.txt", "r", encoding="utf-8") as f:
        content = f.read()
    # 去掉国内镜像参数(生成物里不应该带)
    content = content.replace(
        "--index-url https://pypi.tuna.tsinghua.edu.cn/simple\n"
        "--trusted-host pypi.tuna.tsinghua.edu.cn", "")
    with open("requirements-in.txt", "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("requirements-in.txt generated")

    # 执行命令 pip-compile --annotation-style=line --output-file=requirements.txt requirements-in.txt
    subprocess.run(["pip-compile", "--annotation-style=line",
                    "--output-file=requirements.txt", "requirements-in.txt"])

    with open("requirements.txt", "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace('''--index-url https://pypi.tuna.tsinghua.edu.cn/simple
--trusted-host pypi.tuna.tsinghua.edu.cn''', '')
    with open("requirements.txt", "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("requirements.txt generated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate requirements.txt")
    parser.parse_known_args()
    generate()
