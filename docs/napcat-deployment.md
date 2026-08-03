# NapCat 容器化部署方案

> 调研日期：2026-08-03
> 目的：将 QQ 机器人从官方 API（adapter-qq）切换到 OneBot 协议（NapCat），解决"机器人仅群主可添加、难部署到他人群"的限制。
> 状态：**调研完成，未部署**（本机尚无 Docker）

## 一、为什么切换

| | 官方 API（现方案） | NapCat + OneBot（目标） |
|---|---|---|
| 进群方式 | 仅群主可添加机器人 | 机器人是普通 QQ 号，**任何群主拉号即可进群** |
| 部署到他人群 | ❌ 极难（需企业认证开"对所有群开放"） | ✅ 无限制 |
| 群消息 | 需 @ 或群主开"接收全部消息" | ✅ 默认接收全部群消息 |
| 合规性 | ✅ 官方合规 | ⚠️ 逆向 NTQQ 协议，有封号/失效风险 |
| 账号 | 官方机器人（免费） | 需一个 QQ 号扫码登录 |

## 二、架构

```
[目标 QQ 群] ←→ NapCat（Docker 容器，机器人 QQ 号登录）
                    │  OneBot v11 协议（WS）
                    ▼
              NoneBot2（本项目 qqbot/）
                    │  动态推送/直播提醒（bilibili-feed-api）
                    ▼
              [QQ 群消息输出]
```

## 三、NapCat Docker 部署

### 3.1 镜像与端口（官方 NapNeko/NapCat-Docker，⭐789，活跃）

| 端口 | 用途 |
|---|---|
| 3000 | HTTP API 服务端（可选） |
| 3001 | WebSocket 服务端（正向 WS，OneBot） |
| 6099 | WebUI 管理界面（扫码登录） |

### 3.2 docker-compose.yml（官方模板简化）

```yaml
services:
  napcat:
    image: mlikiowa/napcat-docker:latest
    container_name: napcat
    restart: always
    environment:
      - NAPCAT_UID=${NAPCAT_UID}
      - ACCOUNT=<机器人QQ号>          # 必须设置：重启时自动快速登录，否则每次重启需重新扫码
      - NAPCAT_GID=${NAPCAT_GID}
    ports:
      - 3001:3001    # WS（OneBot 正向连接）
      - 6099:6099    # WebUI
    volumes:
      - ./napcat/config:/app/napcat/config   # NapCat 配置
      - ./ntqq:/app/.config/QQ               # QQ 登录态持久化
```

启动：`NAPCAT_UID=$(id -u) NAPCAT_GID=$(id -g) docker compose up -d`

> 若走反向 WS（推荐），NapCat 侧无需暴露 3001 端口，只留 6099 即可。

### 3.3 首次登录与 OneBot 配置

1. 访问 `http://<主机>:6099/webui`，获取 token：`docker logs napcat`（日志中形如 `WebUi User Panel Url: http://127.0.0.1:6099/webui?token=xxxx`）
2. WebUI → QQ 登录 → **二维码扫码登录机器人 QQ 号**
3. WebUI → 网络配置 → 新建 **WebSocket 服务端**（正向 WS）：
   - 监听端口 `3001`，`保存时启用`
   - （或新建 WebSocket 客户端走反向 WS，见 3.4）
4. 登录态持久化在 `./ntqq` 卷，重启不失效

> **⚠️ 重要（实测 2026-08）**：
> - 容器必须设置 `ACCOUNT=<QQ号>` 环境变量（入口脚本据此执行 `-q` 快速登录）；不设置则**每次重启都要重新扫码**
> - 优雅重启用 `podman stop -t 60`（NTQQ 退出慢，默认 10s 超时会 SIGKILL，可能损坏登录态导致需重登）

### 3.4 连接方式选择（NoneBot2 adapter-onebot v11）

**方案 A：反向 WS（官方推荐）**——NapCat 主动连 NoneBot，无需暴露 NapCat 端口

- NoneBot 侧：已有 fastapi 驱动（8080），无需改动驱动
- NapCat 侧：WebUI 新建 **WebSocket 客户端**，url 填 `ws://<NoneBot主机>:8080/onebot/v11/ws`

**方案 B：正向 WS**——NoneBot 主动连 NapCat

- NoneBot `.env`：
  ```
  ONEBOT_WS_URLS=["ws://127.0.0.1:3001"]
  ```
- 需 `~websockets` 驱动（本项目已有）

## 四、NoneBot2 接入改造（代码影响）

| 项 | 现状（adapter-qq） | 改造后（adapter-onebot v11） |
|---|---|---|
| 依赖 | `nonebot-adapter-qq` | `nonebot-adapter-onebot`（可共存） |
| `main.py` | `from nonebot.adapters.qq import Adapter` | `from nonebot.adapters.onebot.v11 import Adapter` |
| 事件类型 | `GroupAtMessageCreateEvent` | `GroupMessageEvent`（全量群消息，无需 @） |
| 群 ID | `group_openid`（不透明 ID） | `group_id`（数字群号，便于白名单） |
| 主动推送 | 官方主动消息接口（受群主开关限制） | `send_group_msg` API（群主可拉号进群即可收） |
| .env | `QQ_BOTS` / `QQ_IS_SANDBOX` | `ONEBOT_WS_URLS` / `ONEBOT_ACCESS_TOKEN` |
| 权限控制 | 需 `group_openid` 白名单 | `group_id` 数字白名单，更直观 |

## 五、本机环境注意（NixOS）

- **当前无 Docker**（`docker: 未找到命令`），需先启用：`nixos-rebuild` 配置 `virtualisation.docker.enable = true`（或使用 Podman/直接跑 NapCat Shell 版）
- 备选：**NapCat Shell 版**（官方推荐，低内存、无需 Docker）——Linux 一键脚本安装，与 Docker 版功能一致

## 六、风险与注意事项

1. **封号风险**：逆向协议，机器人 QQ 号存在风控/封号可能；建议用**小号**而非主号
2. **版本跟随**：NTQQ 升级后 NapCat 可能失效，需跟随更新
3. **WebUI 安全**：6099 端口勿暴露公网（WebUI 需 token 鉴权）
4. **多机器人**：OneBot 支持多账号（多个 WS URL）

## 七、实施步骤（待用户确认后执行）

1. 安装 Docker（NixOS 配置）或改用 NapCat Shell 版
2. 部署 NapCat 容器，WebUI 扫码登录机器人 QQ 号
3. 配置 OneBot WS（正向或反向）
4. `qqbot/` 切换 adapter（依赖 + `main.py` + 命令插件适配）
5. 群内拉机器人 QQ 号进群，验证 `/检查状态` 与全量群消息
6. 同步实现 `group_id` 白名单权限控制

## 八、参考链接

- NapCat 仓库：https://github.com/NapNeko/NapCatQQ
- NapCat Docker 仓库：https://github.com/NapNeko/NapCat-Docker ｜ DockerHub：https://hub.docker.com/r/mlikiowa/napcat-docker
- NapCat 文档：https://napneko.github.io/ （安装/配置/OneBot）
- NoneBot adapter-onebot：https://github.com/nonebot/adapter-onebot ｜ 文档：https://onebot.adapters.nonebot.dev/
