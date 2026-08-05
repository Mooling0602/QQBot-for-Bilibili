# qqbot 远程容器化部署规划

> 规划日期：2026-08-03
> 目标：机器人从本机迁到云服务器（<服务器域名>）容器运行，配置无缝迁移

## 一、现状与目标架构

```
                    ┌────────────────── <服务器域名>（Podman）──────────────────┐
  公网/QQ           │  napcat 容器 (127.0.0.1:3001)     ← 收群消息/发消息         │
  服务器 Nginx ←─── │  bili-shot 容器 (127.0.0.1:8600)  ← 动态截图服务             │
                    │  qbot2bili 容器（新） (新)                   ← 轮询 B 站 + 推送        │
                    └─────────────────────────────────────────────────────────────┘
```

- qbot2bili 容器（新）**出站连接**：NapCat WS（`wss://<域名>/napcat/ws`）、截图服务（`https://<域名>/bili-shot/screenshot`）、B 站 API
- **无需暴露入站端口**（纯出站客户端）

## 二、镜像设计

```dockerfile
FROM python:3.12-slim
ENV TZ=Asia/Shanghai LANG=C.UTF-8
WORKDIR /app
# 安装项目（wheel 依赖独立的 bilibili-feed-api 包）
COPY dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl
CMD ["python", "-m", "qqbot.main"]
```

- GitHub Actions 会构建 QQBot 和 `bilibili-feed-api` wheel，再打包并推送 `ghcr.io/mooling0602/qqbot-for-bilibili`。
- 普通 `main` 构建推送 `latest` 与短 commit SHA 标签；Git tag 或手动选择稳定版时还推送版本号与 `stable`。生产部署应记录实际使用的版本或 SHA，便于回滚。
- 本地或离线构建仍可执行 `uv build --wheel --out-dir dist`，将两个 wheel 放在同一个 `dist/` 后再运行 `podman build`。
- 版本显示：tag 构建会将版本 tag 写入镜像的 `QQBOT_RELEASE_TAG`，`/检查状态` 显示
  `(stable)`；普通分支镜像显示 `(git)`。手工部署可覆盖该环境变量，但其值必须与安装包
  版本一致才会显示稳定版。
- 手动运行 GitHub Actions 的 CI 时，可勾选 `stable` 输入。工作流会从 `pyproject.toml`
  读取版本号，并发布该版本号、`stable` 和 `latest` 三个标签；未勾选时仍发布短 SHA 与
  `latest`。

## 三、挂载与配置迁移（无缝迁移核心）

| 宿主机目录（服务器） | 容器内 | 内容 |
|---|---|---|
| `<部署目录>/config.yml` | `/app/config.yml` | 主配置（域名/管理员/开关） |
| `<部署目录>/features.yml` | `/app/features.yml` | 功能定义 |
| `<部署目录>/config/` | `/app/config/` | 群配置（config/<群号>/） |
| `<部署目录>/cache/` | `/app/cache/` | 已见动态 id（seen_*.json，防重复推送） |

**迁移步骤**（本机 → 服务器）：
```
scp config.yml features.yml → <部署目录>/
scp -r config/ → <部署目录>/config/
scp -r cache/ → <部署目录>/cache/   # seen 状态，避免重启漏推
```
> 注意：`config/` 中 测试目录 等测试目录不迁移（仅 <群号> 等真实群）

## 四、容器运行参数

每次使用新镜像重建主容器前，先运行配置迁移器。这里挂载整个部署目录而不是单个文件，确保 `.bak` 备份也写回宿主机；迁移失败时保留旧主容器，不继续重建：

```bash
podman run --rm --entrypoint python \
  -v <部署目录>:/config:rw \
  localhost/qqbot2bili:latest \
  -m qqbot.core.updater \
  --config /config/config.yml \
  --features /config/features.yml
```

该迁移器只添加新字段、保留自定义值，可在每次部署前重复执行。部署编排应将它作为主容器启动前的强制步骤，因此旧用户和以后首次部署的用户在发生后续配置升级时都不需要手动补新增字段。首次部署仍需要按模板准备两个配置文件。

```bash
podman run -d --name qqbot2bili --restart=always \
  -e TZ=Asia/Shanghai \
  -v <部署目录>/config.yml:/app/config.yml:ro \
  -v <部署目录>/features.yml:/app/features.yml:ro \
  -v <部署目录>/config:/app/config \
  -v <部署目录>/cache:/app/cache \
  localhost/qqbot2bili:latest
```

- 配置查找逻辑（cwd → 仓库根）在容器内：cwd=/app，`/app/config.yml` 命中 ✅
- 日志：容器 stdout（`podman logs qqbot2bili`）

## 五、部署步骤

1. GitHub Actions 完成后，在服务器拉取指定的 `latest` 或 commit SHA 镜像。
2. 确认宿主机 `config.yml`、`features.yml`、`config/` 和 `cache/` 已存在并可写。
3. 使用新镜像运行上方的配置迁移器；它失败时不要停止旧容器或启动新容器。
4. 停止旧的 `qqbot2bili`，使用相同只读主配置挂载重新创建容器；不要删除业务目录或容器卷。
5. 验证日志显示 OneBot 连接成功、动态轮询任务和按配置启用的直播轮询任务启动。
5. 需要回滚时，改用之前记录的 commit SHA 标签重新创建容器。

## 六、风险与注意

| 项 | 说明 |
|---|---|
| **内存** | 服务器 1.9G（当前已用 978M，可用 ~1G）。qbot2bili 容器（新）预计 +150-250MB，需观察；紧张时调低 NoneBot 日志/限制并发 |
| 群配置路径 | 容器内群配置读写 `/app/config/<群号>/`——挂载卷可写（napcat 卷经验：需 ACL 或容器用户权限） |
| 域名配置 | `config.yml` 的 `screenshot.url`、`onebot.ws_urls` 在容器内**同样适用**（公网域名，无 localhost 依赖）✅ |
| 时区 | TZ=Asia/Shanghai（动态时间显示） |
| 调试 | `podman exec qqbot2bili` 进入容器排查 |

## 七、待确认项

1. GHCR 镜像包是否保持公开；若改为私有，服务器需配置只读拉取凭据。
2. 生产部署是否固定使用 commit SHA，而不是浮动的 `latest`。
3. `cache/` 是否持续挂载（推荐保留，防止重启重复推送）。
