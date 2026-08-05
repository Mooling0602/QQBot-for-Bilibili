# QQ 机器人命令规范

> 适用范围：`qqbot/` 所有命令插件
> 关联模块：`qqbot/core/permissions.py`（权限）、`qqbot/.env`（配置）

## 1. 命令定义

- 命令前缀：`/`（NoneBot 默认，`on_command`）
- **@触发由命令按需声明**：需要 @ 的命令加 `rule=to_me()`；不需要 @ 的命令（如广播/管理类）不加
  - 例：`/检查状态` 需 @（`rule=to_me()`）
  - 例：`禁言`、`/禁言` 和 `/恢复服务` 必须 @ 机器人，且仅在发送命令的群生效
- 命令命名：中文短词（如 `/检查状态`），见各命令文档

## 2. 权限模型

| 级别 | 范围 | 配置 |
|---|---|---|
| 管理员（ADMIN） | `permissions.admin_users` 中的账号；**或** `permissions.auto_admin=true` 时群聊内的群主/管理员（role: owner/admin） | `qqbot/config.yml` → `permissions.admin_users`、`permissions.auto_admin` |
| 普通用户（PUBLIC） | 所有群成员 | 无需配置 |

- 管理员判断统一走 `qqbot.core.permissions.is_admin(user_id, role)`，群内角色自动从事件 `sender.role` 提取
- 管理员专属命令使用 `admin_only()` 权限工厂（`permissions.py`）

## 3. 权限验证

命令声明权限时在 `on_command` 的 `permission` 参数中注入（静默拒绝）：

```python
from qqbot.core.permissions import admin_only

admin_cmd = on_command("示例", rule=to_me(), permission=admin_only(), ...)
```

需要可见提示的命令在 handler 开头检查：

```python
from qqbot.core.permissions import ensure_admin


@admin_cmd.handle()
async def handler(event: Event):
    await ensure_admin(event, admin_cmd)  # 无权限时回复提示并中断
    ...
```

- 未声明 `permission` 的命令默认 PUBLIC

## 4. 群级静默

- 管理员在群内 @ 机器人发送 `禁言` 或 `/禁言` 后，该群进入内存静默状态；机器人不回复确认，也不会向该群发送动态、直播或命令消息。
- 静默不影响其他群，不写入配置或缓存，机器人重启后自动失效。
- 管理员在同一群 @ 机器人发送 `/恢复服务` 可立即解除静默，并收到“服务已恢复”。
- 静默期间的后台通知作为已处理事件丢弃，恢复后不会补发。

## 5. 无权限拒绝行为（敲定）

| 模式 | 实现 | 行为 |
|---|---|---|
| 静默（默认） | `permission=admin_only()` | 匹配器不匹配，**不做任何响应** |
| 提示 | handler 内 `ensure_admin()` | **明确回复**：`权限不足：该命令仅管理员可用` 并中断 |

- 两种模式共用 `DENY_MESSAGE` 常量（`permissions.py`）
- 拒绝时记录 DEBUG 日志（含用户 ID），不产生其他副作用

## 6. 响应格式

- 成功：正常文本消息（可含富文本，见各命令）
- 参数错误：`用法：/命令 <参数说明>` + 简述
- 执行失败：`错误：<原因>`，不暴露内部堆栈

## 7. 变更流程

- 新增命令：新建 `qqbot/plugins/<name>.py`，遵循本节规范（to_me + 权限 + 响应格式）
- 修改行为：先更新本规范再改代码
