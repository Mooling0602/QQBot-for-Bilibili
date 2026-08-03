# QQ 机器人框架调研

> 调研日期：2026-08-01
> 调研对象：QQ 官方机器人 API、Python 生态第三方框架、OneBot 协议与协议端
> 目标场景：本项目（Python、QQ **群**机器人、B 站动态/直播推送等运维辅助功能）选择技术栈，避免重复造轮子
> 数据来源：GitHub API/网页、PyPI、QQ 官方文档（bot.q.qq.com）、各项目 README，见文末参考链接

---

## 一、官方方案

### 1. QQ 开放平台机器人（推荐首选）

- **官网**：https://q.qq.com ｜ **文档**：https://bot.q.qq.com/wiki/develop/api-v2/
- **协议类型**：官方 HTTP REST API + WebSocket 长连接事件推送（被动接收事件，主动调接口发消息）
- **适用场景**：机器人可被添加到 **单聊 / 群聊 / 频道** 三种场景（官方文档原文确认）
  - 群聊事件：`GROUP_AT_MESSAGE_CREATE`（群聊 @ 机器人）、`GROUP_MESSAGE_CREATE`
  - 消息类型：文本（msg_type=0）、Markdown（2）、富媒体（7，需先上传获取 file_info，支持图片/视频/语音/文件）
- **接入票据**：AppID + AppSecret（旧 Token 已弃用）
- **消息限制（对本项目很关键）**：
  - 被动回复：群聊 5 分钟内可回复 5 次；单聊 60 分钟 4 次
  - 主动消息：可无条件主动触达，但**用户可在客户端关闭「允许主动发送」**，关闭后发送失败
  - 群聊主动消息频控：Bot 维度 30~60/qpm（认证 60，未认证 30）、单群 20/qpm、每日上限 1000 条/群 —— 对运维推送足够
- **官方 SDK**：Python [botpy](https://github.com/tencent-connect/botpy)（PyPI 包名 `qq-botpy`，v1.2.1）、Go botgo、Node bot-node-sdk
- **当前状态**：官方主推、文档持续更新（api-v2 已涵盖群聊/单聊/频道统一接口）；免费注册，支持个人/企业认证

### 2. 旧版「QQ 频道机器人 API」（历史沿革）

- 早期独立开放的 QQ 频道（guild）机器人 WebSocket API，已并入上述统一开放平台
- 频道消息事件（频道消息、频道 @ 机器人 `at_messages`、表态、审核）在 api-v2 中仍保留，但**新项目直接按统一 API 开发即可，无需区分**旧频道体系

---

## 二、第三方框架（Python 优先）

### 1. NoneBot2 —— 最活跃的 Python 机器人框架

- **GitHub**：https://github.com/nonebot/nonebot2 ｜ **PyPI**：`nonebot2` v2.5.0 ｜ 文档：https://nonebot.dev
- **协议**：协议无关，通过适配器对接。与 QQ 相关的两个适配器：
  - **[nonebot/adapter-qq](https://github.com/nonebot/adapter-qq)**（277★，PyPI `nonebot-adapter-qq` v1.7.1，活跃）：**直连 QQ 官方 API**，支持 WebSocket / WebHook，支持 `c2c_group_at_messages`（私聊与群聊 @ 消息）、`at_messages`（频道）等事件，含沙盒模式
  - **[nonebot/adapter-onebot](https://github.com/nonebot/adapter-onebot)**（119★，活跃）：连接 OneBot v11 协议端（NapCat/go-cqhttp 等）
- **优点**：MIT 协议、插件生态丰富、异步（基于 asyncio + pydantic）、文档完善、社区活跃（7.6k★）
- **缺点**：走官方 API 时群聊只能收 @ 消息；走 OneBot 需额外部署协议端

### 2. aiocqhttp（OneBot v11 Python SDK，不活跃）

- **GitHub**：https://github.com/nonebot/aiocqhttp ｜ PyPI `aiocqhttp` v1.4.4
- **协议**：OneBot v11（CQHTTP）客户端 SDK，需配合 go-cqhttp 等协议端
- **状态**：300★，2023-06 后基本无更新，已被 NoneBot2 + adapter-onebot 取代；新项目不建议直接使用

### 3. Mirai 生态（JVM + HTTP API 插件架构，部署重）

- **mirai**（mamoe/mirai，14.8k★，2024-09 后维护放缓）：Kotlin 实现的 QQ 协议端（源自 MiraiGo），需 Java 运行环境
- **mirai-api-http**（project-mirai，1.7k★）：为 mirai 提供 HTTP API 的插件
- **python-mirai**（snamper，42★）：已停止维护；继任者为 **[YiriMirai](https://github.com/YiriMiraiProject/YiriMirai)**（124★，基于 mirai-api-http 的轻量 SDK）
- **GraiaProject/Ariadne**（763★，活跃）：基于 mirai-api-http 的 Python 框架，API 优雅但同样依赖 mirai
- **缺点**：部署链长（JVM + mirai 控制台 + 插件 + Python 桥接），协议逆向风险高，已非主流选择

### 4. 协议端（配合 NoneBot/aiocqhttp 等使用，⚠️ 逆向风险）

| 协议端 | 语言 | Star/状态 | 说明 |
|---|---|---|---|
| **go-cqhttp** | Go | 10.7k★，**已停止维护** | README 明确声明「无力继续维护」；协议库遭 QQ 官方围堵，勿用于新项目 |
| **NapCatQQ** | TS | 10.0k★，活跃 | 基于 NTQQ 的现代协议端，完整实现 OneBot 11 接口，社区活跃、低内存运行 |
| **LLOneBot → LuckyLilliaBot** | TS | 3.5k★，活跃 | 原名 LLOneBot，支持 OneBot 11 + Satori + Milky 协议 |
| **Lagrange.Core** | C# | 3.0k★，活跃 | NTQQ 协议实现；OneBot 支持已转向自研 Milky 协议（Lagrange.Milky）；另有 Go 版 LagrangeGo、Python 版 lagrange-python（131★） |
| **oicq** | Node | 2.6k★，**已归档** | Node.js QQ 库，项目已归档 |
| **OpenShamrock** | — | 官方仓库已删除（404） | 已停更，不再考虑 |

- 协议端本质是逆向 QQ 客户端协议，存在封号与失效风险；NapCat 是目前其中社区最活跃的选择

### 5. AstrBot（泛化 AI 助手框架，可作备选）

- **GitHub**：https://github.com/AstrBotDevs/AstrBot（38.4k★，非常活跃）
- **协议**：支持 QQ 官方机器人 + OneBot（NapCat/LLOneBot）+ Telegram/Discord 等多平台，内置 LLM 编排
- **定位**：面向 AI Agent 的现成助手框架，功能远重于本项目所需（B 站推送+运维），但插件生态大，若后续要接 LLM 可考虑

---

## 三、OneBot 协议与生态

- **OneBot v11**：规范 https://github.com/botuniverse/onebot-11（688★），事实标准（CQHTTP 演进），协议端/框架支持最广
- **OneBot v12**：规范 https://github.com/botuniverse/onebot（2.0k★），文档 https://12.onebot.dev ，通用多平台抽象，支持事件/API 标准统一；实现相对 v11 少
- **Python SDK 现状**：
  - v11：`aiocqhttp`（停更）、`YiriOneBot`（YiriMiraiProject，活跃）、NoneBot `adapter-onebot`
  - 老的 `onebot-sdk-python` 仓库已不可用；v12 官方 Python SDK 生态仍弱
  - **结论：Python 侧不建议裸用 OneBot SDK，直接上 NoneBot2 适配器更省事**

---

## 四、推荐方案（针对本项目：Python 群机器人 + B 站动态/直播推送）

### 方案 A：NoneBot2 + adapter-qq（直连 QQ 官方 API）⭐ 首选

```
botpy 思路的官方 API 由 NoneBot2 封装 → qq 群 @ 机器人触发查询 / 主动推送动态
```

- **理由**：官方 API 免费合规、无封号风险；NoneBot2 生态成熟、异步性能好、插件化利于后续扩展（如加指令、定时任务）；群聊主动消息频控（每日 1000 条/群）完全满足推送量
- **注意**：群聊内机器人仅在**被 @ 时**收到事件（`GROUP_AT_MESSAGE_CREATE`）；主动推送可用主动消息接口（用户可关闭），文档中已有明确频控与时效说明
- **部署**：申请官方机器人（q.qq.com 免费）→ AppID/AppSecret → NoneBot2 + adapter-qq，无需跑逆向协议端

### 方案 B：NoneBot2 + OneBot（NapCatQQ）—— 追求无 @ 限制的完整群体验

- **理由**：NapCat 活跃、OneBot 11 消息收发不受「必须 @」限制，可自由发群消息、看全部群消息；框架层与方案 A 共用 NoneBot2，切换成本低
- **代价**：需部署 NapCat（基于 NTQQ 逆向，有封号/失效风险）；协议端升级需要跟随 QQ 客户端版本
- **适用**：若需求依赖「群内全部消息」（如统计、自动回复）而非仅 @ 指令，选此方案

### 方案 C：官方 botpy 裸开发 —— 最轻量

- **理由**：本项目功能单薄（动态推送 + 直播提醒 + 少量指令），用 `qq-botpy` + aiohttp 直接写 200 行内即可，零框架依赖
- **代价**：botpy 更新缓慢（v1.2.1，2024-03 发布后官方更新少），断线重连、参数校验等需自行处理；文档以官方 API 文档为准

### 综合建议

> 若本项目定位为「长期维护的群机器人」，选 **方案 A**；若确定需要监控群内全部消息，选 **方案 B**；若只想快速跑通推送，选 **方案 C**。三者代码目录（`qqbot/`）可先按 NoneBot2 结构组织，保留切换余地。

### 部署与平台限制（实测 2026-08）

- **进群权限**：只有**群主/管理员**能拉机器人进群并配置权限，普通成员无法操作；个人开发者无法开启「对所有群开放」（需企业认证）→ 机器人很难部署到**非自己当群主的群**
- **沙盒/正式环境**：沙盒网关（sandbox.api.sgroup.qq.com）只收测试群/私聊事件；手机 QQ 添加的机器人是正式实例，必须 `QQ_IS_SANDBOX=false` 连正式网关才能收到正式群消息
- **intent 订阅**：`c2c_group_at_messages`（1<<25，覆盖群@/群消息/私聊）默认关闭，必须显式开启（`QQ_BOTS` 中 `"intent": {"c2c_group_at_messages": true}`）
- **权限开关**：群主在机器人管理页可关闭「允许主动回复」→ 主动推送会失败，代码需处理发送失败（记录+重试或跳过）
- **部署指引**：目标群群主需操作——添加机器人 → 设置「接收全部消息」+「允许主动回复」

---

## 五、参考链接

- QQ 开放平台（注册）：https://q.qq.com
- QQ 机器人官方文档（api-v2，消息收发/频控/主动消息）：https://bot.q.qq.com/wiki/develop/api-v2/ 、https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/overview.html
- 官方 Python SDK botpy：https://github.com/tencent-connect/botpy ｜ PyPI：https://pypi.org/project/qq-botpy/
- NoneBot2：https://github.com/nonebot/nonebot2 ｜ adapter-qq：https://github.com/nonebot/adapter-qq ｜ adapter-onebot：https://github.com/nonebot/adapter-onebot
- aiocqhttp：https://github.com/nonebot/aiocqhttp
- Mirai：https://github.com/mamoe/mirai ｜ mirai-api-http：https://github.com/project-mirai/mirai-api-http ｜ YiriMirai：https://github.com/YiriMiraiProject/YiriMirai ｜ Ariadne：https://github.com/GraiaProject/Ariadne
- 协议端：go-cqhttp https://github.com/Mrs4s/go-cqhttp ｜ NapCatQQ https://github.com/NapNeko/NapCatQQ ｜ LuckyLilliaBot https://github.com/LLOneBot/LuckyLilliaBot ｜ Lagrange.Core https://github.com/LagrangeDev/Lagrange.Core ｜ oicq https://github.com/takayama-lily/oicq
- OneBot 规范：v11 https://github.com/botuniverse/onebot-11 ｜ v12 https://github.com/botuniverse/onebot 、https://12.onebot.dev 、https://onebot.dev
- AstrBot：https://github.com/AstrBotDevs/AstrBot
