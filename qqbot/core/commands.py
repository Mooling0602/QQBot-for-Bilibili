"""命令注册表：动态收集所有已注册命令名。

用于命令提示功能（@机器人 发无斜杠命令名时提示补充斜杠）。
"""

from nonebot.internal.matcher import matchers
from nonebot.rule import CommandRule


def get_command_names() -> set[str]:
    """返回所有已注册命令的命令名（不含斜杠，如 {"帮助", "检查状态"}）。"""
    names: set[str] = set()
    for matcher_list in matchers.values():
        for matcher in matcher_list:
            for checker in matcher.rule.checkers:
                call = getattr(checker, "call", None)
                if isinstance(call, CommandRule):
                    for cmd in call.cmds:
                        names.add(cmd[0])
    return names
