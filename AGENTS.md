# AGENTS.md - QQBot for Bilibili

这是独立的 Git 仓库，使用 `main` 分支。它是基于 NoneBot2 的 QQ 群机器人，负责
按群配置推送 UP 主动态；入口为 `qqbot.main`，动态推送位于
`qqbot/plugins/dynamic_push.py`。

## 依赖与边界

- 依赖 `bilibili-feed-api`，其公开 Git 源定义在 `pyproject.toml` 的
  `[tool.uv.sources]`。Python 导入名为 `bilibili_feed_api`。
- 本地的 `bilibili-feed-apis` 兄弟目录不会自动替代该 Git 依赖。API 的公开接口变更
  必须同步评估本项目调用并分别验证、提交。
- 动态截图服务是独立 HTTP 服务。QQBot 通过 `screenshot.url` 或
  `BILI_SCREENSHOT_URL` 调用；服务未配置或请求失败时必须保持标题和直链回退。
- `live_alert` 负责直播开播和可选下播通知。它只轮询 `get_live_status()`；检测到需要
  投递的开播事件后才调用 `get_live_room_info()` 获取分区和开播时间。不要把 QQ 群配置、
  状态机或轮询逻辑放入 feed API。

## 动态推送语义

- 配置有效登录态时，已关注 MID 使用 `feed/all` 关注时间线；未关注 MID 必须记录警告，
  提示管理员使用该账号**手动**关注后回退 `feed/space`。未配置登录态时仅使用
  `feed/space`。后者遭遇风控只能按既有退避处理，不得自动关注、切换代理或调整请求频率。
- 新增 mid 时记录群级订阅时间，只推送发布时间晚于该时间的动态。`cache/seen_<mid>.json`
  必须持久化；删除或丢失缓存会使已处理动态重新进入候选集。`push_dry_run` 也会更新
  已见状态。
- 每次只请求一次 `feed/all`，再按 mid 并行处理；同一 mid 必须保持串行。QQBot 复用同一
  动态的截图，截图失败时消息必须附加标题和直链，即使群配置关闭了 `add_url`。
- 群配置从 `config/<群号>/config.yml` 动态读取。发送逻辑只选择已连接的 OneBot v11
  机器人，改动时须保留这一约束。
- 直播状态存放在 `cache/live_<mid>.json`。首次观察和新订阅只建立基线；同一 MID 查询
  必须串行、不同 MID 可以并行，并共享全局请求限速。详情失败仍应发送可用的基础开播消息，
  随后退避重试详情；下播只通知已成功收到本场开播消息且仍启用下播提醒的群。

## 开发与验证

在本仓库根目录执行：

```bash
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q qqbot
uv build --wheel --out-dir dist
```

构建部署镜像时，`dist/` 中必须同时有本项目和 `bilibili-feed-api` 的 wheel：

```bash
docker build -f docker/Dockerfile.qqbot -t qqbot-for-bilibili:local .
```

CI 会在推送或拉取请求时检查编译和 wheel 构建；推送到 `main` 时还会构建并发布 GHCR
镜像。不要在未获明确授权时执行生产部署或镜像推送。

## 配置与提交

- 不提交真实 `SESSDATA`、OneBot access token、QQ 官方机器人密钥、代理认证或运行环境
  标识。使用 `config.yml.example`、环境变量和占位符。
- `config.yml`、`.env`、`config/`、`cache/` 和 `dist/` 均为忽略的运行时或构建数据；
  除非任务明确涉及，勿修改、删除或加入版本控制。
- 版本升级使用 `python -m qqbot.core.updater` 在短生命周期、可写配置挂载的容器中执行。
  主机器人容器必须继续将 `config.yml` 与 `features.yml` 以只读方式挂载；迁移器会保留首次
  修改前的 `.bak` 文件。
- 提交使用英文 Conventional Commits。提交前运行 `git diff --check`，并执行与改动匹配的
  验证。
