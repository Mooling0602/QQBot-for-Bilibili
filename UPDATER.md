# 版本更新兼容规范

此文档记录配置文件版本更新时，应采取的兼容方案。

更新适配模块应放置在 qqbot/core/updater.py

# 0.2.0

配置文件版本 `0.2.0` 在配置结构升级时启用，相较于先前版本，config.yml.example 模板和 features.yml 特性文件都有结构变化，且仅添加了新增配置项。其中配置增加了 `version`（配置结构版本，不等于 Python 包版本）和 `live_monitor`，特性文件增加了 `features.live_alert.notify_on_close` 用于控制是否发送下播事件，增加了 `features.live_alert.prompt_on_close` 用于设置下播提示词。

**注意：**`features.live_alert.description` 的默认值发生了修改，需要检查当前的选项值是否匹配先前的默认值，若匹配则进行自动修正，否则不动。

`python -m qqbot.core.updater` 负责该迁移。它只补充缺失字段，并在同一目录写入首次修改前的 `config.yml.bak`、`features.yml.bak`；重复执行不会覆盖备份或自定义值。生产环境应由短生命周期的可写迁移容器执行该命令，主机器人继续使用只读的配置文件挂载。迁移失败必须阻止新主容器启动。
