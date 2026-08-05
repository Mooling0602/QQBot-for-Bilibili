# QQBot for Bilibili

基于 NoneBot2 的 QQ 群机器人，用于按群配置哔哩哔哩 UP 主动态推送。当前主通信链路为 NapCat + OneBot v11；QQ 官方适配器仍保留注册和配置入口，但动态推送目前只会选择 OneBot 机器人发送。

项目仍处于开发阶段。当前已经实现动态监听、群级配置和基础管理命令；`features.yml` 中的 `live_alert` 仅为预留配置，直播提醒插件尚未实现。

## 当前功能

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| UP 主动态推送 | 可用 | 优先使用登录账号的关注时间线；没有登录态或未关注目标时回退到按 MID 查询 |
| 群级配置 | 可用 | 每个群可独立设置关注的 mid、提示文案、直链和功能开关 |
| 帮助和状态命令 | 可用 | 提供 `/帮助`、管理员状态检查和群配置命令 |
| 动态截图 | 可选 | 调用独立截图服务；未配置或调用失败时自动发送标题和直链 |
| QQ 官方机器人 | 备用 | 适配器已注册，但当前动态推送发送链路仅支持 OneBot v11 |
| 开播提醒 | 未实现 | `live_alert` 目前只有配置定义，不会启动监听或发送消息 |

## 直播提醒规划

常规的 `live_alert` 将按订阅 MID 轮询直播状态，适用于任意可查询的 UP 主。B 站没有面向普通订阅者、可主动推送任意 UP 主开播事件的官方接口。

对于愿意自行授权的主播，可在后续增加独立的官方直播开放平台提供方：开发者应用使用自身的 `app_id` 和密钥，结合该主播提供的 `room_owner_auth_code` 启动官方 WebSocket 会话，接收开播和下播事件。该路径只能覆盖已授权的房间，不能替代普通 MID 订阅；授权码和应用密钥只能作为部署侧运行时机密保存，不能出现在群配置、命令参数或日志中。

## 工作区依赖

开发三个项目时建议保持如下兄弟目录结构：

```text
QBWorkspace/
├── QQBot-for-Bilibili/
├── bilibili-feed-apis/
└── bilibili-dynamic-screenshot/
```

- `bilibili-feed-apis` 是必需依赖，发行包名为 `bilibili-feed-api`。QQBot 的 `pyproject.toml` 已使用其公开 GitHub 仓库，单独检出 QQBot 也可以运行 `uv sync`。
- `bilibili-dynamic-screenshot` 是独立 HTTP 服务，不是本项目的 Python 包依赖。只有需要动态卡片图片时才需要单独部署。
- 如果同时开发 feed API，可在本地保留兄弟 checkout；它不会改变 QQBot 的 Git 源依赖。

## 运行要求

- Python 3.10 或更高版本
- [uv](https://docs.astral.sh/uv/)
- 一个可连接的 OneBot v11 协议端，当前推荐使用 NapCat
- 动态监听可匿名运行；配置有效的 B 站 `SESSDATA` 并手动关注目标 UP 后，可使用更稳定、请求量更低的关注时间线
- 可选的动态截图服务

NapCat 基于 NTQQ 逆向实现，存在账号风控、版本失效等风险。建议使用专用 QQ 账号，并避免将 NapCat WebUI 暴露到公网。

## 源码运行

在本项目根目录执行：

```bash
uv sync
cp config.yml.example config.yml
uv run python -m qqbot.main
```

如果 `config.yml` 不存在，源码运行时会尝试从 `config.yml.example` 自动生成；仍建议先复制并检查配置。配置也可以通过环境变量 `QQBOT_CONFIG` 指向其他路径。

Linux 下可使用管理脚本在后台运行：

```bash
./scripts/qqbot.sh start
./scripts/qqbot.sh status
./scripts/qqbot.sh restart
./scripts/qqbot.sh stop
```

脚本日志固定写入 `/tmp/qqbot.log`。

## 连接 NapCat

模板默认使用正向 WebSocket，即本项目主动连接 NapCat 的 WebSocket 服务端。在 NapCat 中启用 OneBot v11 WebSocket 服务端后，填写可访问的地址：

```yaml
onebot:
  ws_urls:
    - "ws://127.0.0.1:3001"
```

如果两者运行在不同主机或容器内，不能直接照用 `127.0.0.1`，应填写机器人容器实际可访问的主机名、内网地址或 `wss://` 地址。

NapCat 启用了访问令牌时，通过环境变量或项目根目录下的 `.env` 设置：

```dotenv
ONEBOT_ACCESS_TOKEN=<access-token>
```

也可以让 NapCat 作为 WebSocket 客户端反向连接 NoneBot 的 `/onebot/v11/ws` 端点。两种连接方式及 NapCat 部署步骤见 [NapCat 部署说明](docs/napcat-deployment.md)。

## 主配置

完整模板见 `config.yml.example`。主要配置项如下：

| 配置项 | 作用 |
| --- | --- |
| `permissions.admin_users` | 显式指定机器人管理员 QQ 号 |
| `permissions.auto_admin` | 自动将群主和群管理员视为机器人管理员 |
| `framework.driver` | NoneBot 驱动组合，默认同时提供 HTTP、WebSocket 客户端和服务端能力 |
| `onebot.ws_urls` | NapCat 等 OneBot v11 WebSocket 服务端地址 |
| `qq_official` | QQ 官方机器人备用配置；`bots: []` 表示禁用 |
| `screenshot.url` | 独立截图服务的 `/screenshot` 接口；留空且未设置 `BILI_SCREENSHOT_URL` 时使用文字摘要 |
| `push_dry_run` | 只记录待发送消息，不实际向 QQ 群发送 |
| `dynamic_monitor` | 动态监听总开关，默认关闭，修改后需重启 |
| `bilibili.sessdata` | 可选 B 站登录态；已关注目标使用 `feed/all`，未关注目标回退 `feed/space` |
| `bilibili.proxy` | 可选的 B 站请求代理 |
| `bilibili.proxy_auth` | 代理认证，格式为 `["username", "password"]` |

`SESSDATA`、代理认证、OneBot 令牌和 QQ 官方机器人密钥均属于敏感信息，不要提交到版本库。B 站配置也可以使用 `BILI_SESSDATA`、`BILI_PROXY` 和 `BILI_PROXY_AUTH` 环境变量提供。

## 启用动态推送

动态推送有两级开关：

1. 根配置 `config.yml` 中的 `dynamic_monitor` 必须为 `true`。
2. 对应群的 `dynamic_push.enable` 必须开启，并配置至少一个 mid。

机器人连接群聊后，由群主、群管理员或 `admin_users` 中的管理员执行：

```text
/群配置 设置 dynamic_push mids <mid1>,<mid2>
/群配置 设置 dynamic_push prompt 你关注的 UP 主发布了新动态
/群配置 设置 dynamic_push add_url 开
/群配置 设置 dynamic_push enable 开
```

添加 mid 时会与现有列表合并；使用 `!mid` 删除：

```text
/群配置 设置 dynamic_push mids !<mid>
```

群配置保存在工作目录的 `config/<群号>/config.yml`。机器人会动态读取群配置，无需为群配置修改重启。

首次通过群配置添加某个 mid 时，机器人会记录该群的订阅开始时间；只会向该群推送发布时间晚于该时间的动态，不会推送历史内容。既有群配置升级后会在首次扫描时补齐该时间，效果相同。

动态来源按登录态和关注关系选择：

- 未配置 `SESSDATA` 时，所有 MID 使用 `feed/space`。该接口在部分服务器 IP 上会返回 412 风控；机器人只会指数退避重试，管理员需要自行调整网络环境。
- 配置 `SESSDATA` 后，机器人每 10 分钟复查一次登录账号的关注关系。已关注 MID 会被汇总为一次 `feed/all` 请求；未关注 MID 会在日志中警告管理员使用该账号**手动**关注，并暂时回退 `feed/space`。机器人不会代替账号执行关注操作；手动关注后，下次复查会自动切回 `feed/all`。
- `feed/all` 与 `feed/space` 的已见状态共用 `cache/seen_<mid>.json`，因此来源切换不会重复推送同一条动态。

监听状态保存在 `cache/seen_<mid>.json`，只会在动态已完成解析并决定投递或终态忽略后写入。每轮 `feed/all` 最多请求一次；`feed/space` 的不同 MID 可并行查询，同一 MID 始终按发布时间串行处理。基础轮询间隔为 10 秒，B 站请求失败时逐步退避，最长 160 秒。

正常消息按“提示词 + 动态标题 + 图片 + 可选直链”发送。每条动态的截图由 QQBot 在内存中复用，同一动态不会因多个群订阅而重复请求截图服务；截图服务不可用时，机器人发送“提示词 + 动态标题 + 分钟级发布时间 + 直链”，并强制附加直链，即使该群关闭了 `add_url`。发布时间按容器或宿主机的本地时区显示，无法取得本地时区时回退 Asia/Shanghai。内容无法解析时会向相关群发送简短错误提示，需管理员后续检查。

`cache/` 需要持久化，否则重启后会重新建立基线。`push_dry_run` 期间发现的动态同样会写入已见状态，关闭调试后不会补发。启动正式监听前应先确认 OneBot 已连接；当前实现不会自动重试连接未就绪时已经标记为已见的动态。

## 命令

| 命令 | 权限 | 行为 |
| --- | --- | --- |
| `/帮助` | 所有人 | 显示基础帮助 |
| `@机器人 /检查状态` | 管理员 | 显示版本与发布渠道、启动时间和运行时长 |
| `/群配置` | 管理员，仅群聊 | 查看当前群的功能配置 |
| `/群配置 设置 <功能> <字段> <值>` | 管理员，仅群聊 | 修改 `enable`、`mids`、`prompt` 或 `add_url` |

管理员来自 `permissions.admin_users`，或在 `permissions.auto_admin: true` 时由 OneBot 群角色自动识别。更完整的命令约定见 [命令规范](docs/qqbot-command-spec.md)。

## 数据目录

以下内容不会纳入 Git：

| 路径 | 内容 | 部署要求 |
| --- | --- | --- |
| `config.yml` | 主配置和凭据 | 必须妥善保管 |
| `config/` | 各群独立配置 | 容器部署时需可写并持久化 |
| `cache/` | 已见动态 ID | 容器部署时需可写并持久化 |
| `.env` | 可选环境变量和令牌 | 不要提交 |
| `dist/` | wheel 和源码构建产物 | 按需重新构建 |

## Docker / Podman

当前仓库提供 `docker/Dockerfile.qqbot`，没有 Compose 编排。GitHub Actions 会在 `main` 分支更新后构建并推送以下 GHCR 镜像：

```text
ghcr.io/mooling0602/qqbot-for-bilibili:latest
ghcr.io/mooling0602/bilibili-dynamic-screenshot:latest
```

也可以在本地构建 QQBot 镜像。先从 [bilibili-feed-apis](https://github.com/Mooling0602/bilibili-feed-apis)
检出源码并构建其 wheel，再将两个 wheel 放入 QQBot 的 `dist/` 目录：

```bash
uv build --wheel --out-dir dist .
uv build --wheel --out-dir dist /path/to/bilibili-feed-apis
docker build -f docker/Dockerfile.qqbot -t qqbot-for-bilibili:0.1.0 .
```

服务器部署优先拉取 GHCR 镜像；需要回滚时使用 Actions 推送的 commit SHA 标签，而不是覆盖宿主机业务数据。

运行时必须从宿主机挂载配置和状态目录：

```bash
docker run -d --name qqbot-for-bilibili \
  --restart unless-stopped \
  -e TZ=Asia/Shanghai \
  -v /path/to/deploy/config.yml:/app/config.yml:ro \
  -v /path/to/deploy/features.yml:/app/features.yml:ro \
  -v /path/to/deploy/config:/app/config \
  -v /path/to/deploy/cache:/app/cache \
  qqbot-for-bilibili:0.1.0
```

如需从 `.env` 注入令牌，可额外使用 `--env-file /path/to/deploy/.env`。使用正向 WebSocket 时机器人只需要出站连接；使用反向 WebSocket 时还需按部署环境暴露 NoneBot 端口。Podman 可使用等价参数，详细规划见 [QQBot 容器部署说明](docs/qqbot-docker-deploy.md)。

## 相关文档

- [NapCat 部署说明](docs/napcat-deployment.md)
- [QQBot 容器部署说明](docs/qqbot-docker-deploy.md)
- [命令规范](docs/qqbot-command-spec.md)
- [直播通知实现计划](docs/live-notify-plan.md)
- [QQ 机器人框架调研](docs/qqbot-frameworks.md)

## 许可与第三方组件

本仓库自行编写的源代码采用 [MIT License](LICENSE)。该许可只覆盖本仓库代码，不会改变第三方组件、服务或内容原有的权利状态。

- NoneBot2、NoneBot OneBot/QQ 适配器和 Python 依赖分别适用各自的许可证；分发包含依赖的镜像时应保留相应许可证和通知。
- NapCatQQ 是独立运行的外部软件，本项目仅通过 OneBot WebSocket 与其通信，不包含或修改 NapCat 源码。NapCatQQ 不是 MIT 项目，使用和再分发须单独遵守其 [Limited Redistribution License](https://github.com/NapNeko/NapCatQQ/blob/main/LICENSE)。
- 本项目与腾讯、QQ、哔哩哔哩及 NapCatQQ 无隶属或授权关系。本仓库的 MIT 许可不授予第三方商标、平台 API、账号数据、动态文字、图片或截图内容的权利；相关使用还需遵守各平台服务条款。

请合理控制请求频率并保护账号凭据，不要滥用本项目。
