"""群配置命令（管理员）：/群配置 查看，/群配置 设置 <键> <字段> <值> 修改。

各群配置独立存储于工作目录 config/<群号>/config.yml：
    group_id: "群号"
    dynamic_push:
      enable: false
      mids: []

可修改的键以根配置 features.yml 定义为白名单，不支持的键修改失败。
"""

import re

from nonebot import on_command
from nonebot.adapters import Bot, Event

from qqbot.core import features
from qqbot.core.group_config import (
    get_group_id,
    load_group_config,
    save_group_config,
)
from qqbot.core.permissions import admin_only, ensure_admin

group_cfg_cmd = on_command(
    "群配置",
    permission=admin_only(),
    priority=10,
    block=True,
)

USAGE = (
    "用法：/群配置\n"
    "      /群配置 设置 <键> enable <开/关>\n"
    "      /群配置 设置 <键> mids <mid1,mid2>（合并添加，!mid 删除）\n"
    "      /群配置 设置 <键> prompt <提示文案>\n"
    "      /群配置 设置 <键> add_url <开/关>"
)


def _normalize_feature_value(value, key: str | None = None):
    """兼容旧数据：bool 值转为 {enable, mids, prompt, add_url} 结构。"""
    if isinstance(value, dict):
        item = dict(value)
    else:
        item = {"enable": bool(value), "mids": []}
    if key:
        item.setdefault("enable", features.feature_default(key))
        item.setdefault("mids", list(features.feature_mids(key)))
        item.setdefault("prompt", features.feature_prompt(key))
        item.setdefault("add_url", features.feature_add_url(key))
    return item


@group_cfg_cmd.handle()
async def handle_group_config(bot: Bot, event: Event) -> None:
    await ensure_admin(event, group_cfg_cmd)
    group_id = get_group_id(event)
    if not group_id:
        await group_cfg_cmd.finish("该命令仅支持群聊使用")

    raw = str(event.get_message()).strip()
    args = re.sub(r"^/\S+\s*", "", raw).strip()
    parts = args.split(maxsplit=3)

    if not parts:
        await group_cfg_cmd.finish(render_config(group_id))
    elif parts[0] == "设置" and len(parts) == 4:
        key, field, value = parts[1], parts[2], parts[3]
        if not features.is_supported(key):
            await group_cfg_cmd.finish(
                f"不支持的配置项：{key}\n可用项：{'、'.join(features.feature_keys())}"
            )
        data = load_group_config(group_id)
        item = _normalize_feature_value(data.get(key), key)
        try:
            if field == "enable":
                item["enable"] = _parse_bool(value)
            elif field == "mids":
                for m in value.split(","):
                    m = m.strip()
                    if not m:
                        continue
                    if m.startswith("!"):
                        # 删除：!mid
                        target = m[1:]
                        if target in item["mids"]:
                            item["mids"].remove(target)
                    else:
                        # 合并添加（去重）
                        if m not in item["mids"]:
                            item["mids"].append(m)
            elif field == "prompt":
                item["prompt"] = value
            elif field == "add_url":
                item["add_url"] = _parse_bool(value)
            else:
                await group_cfg_cmd.finish(USAGE)
        except ValueError as e:
            await group_cfg_cmd.finish(f"配置失败：{key} {field} {e}")
        data[key] = item
        save_group_config(group_id, data)
        await group_cfg_cmd.finish(
            f"已设置：{key} {field} = {item[field]}"
        )
    else:
        await group_cfg_cmd.finish(USAGE)


def _parse_bool(raw: str) -> bool:
    if raw.lower() in ("true", "1", "开", "on", "yes"):
        return True
    if raw.lower() in ("false", "0", "关", "off", "no"):
        return False
    raise ValueError("值需为 true/false（或 开/关）")


def render_config(group_id: str) -> str:
    data = load_group_config(group_id)
    lines = [f"群 {group_id} 配置："]
    for key in features.feature_keys():
        item = _normalize_feature_value(data.get(key), key)
        enable = "开" if item.get("enable") else "关"
        mids = item.get("mids") or []
        prompt = item.get("prompt") or ""
        add_url = "开" if item.get("add_url") else "关"
        desc = features.feature_description(key)
        lines.append(f"  {key}（{desc}）")
        lines.append(f"    enable: {enable}")
        lines.append(f"    mids: {'、'.join(mids) if mids else '（无）'}")
        lines.append(f"    prompt: {prompt or '（无）'}")
        lines.append(f"    add_url: {add_url}")
    lines.append("修改：/群配置 设置 <键> enable/mids/prompt/add_url <值>")
    return "\n".join(lines)
