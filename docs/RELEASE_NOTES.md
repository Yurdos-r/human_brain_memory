# Human Brain Memory Framework · 1.0 Beta

人脑记忆框架的首个独立 Beta，提供 AstrBot 插件和可复用的 Python 记忆核心。

- 分层记忆：事实、经历、人物画像、自我回顾、“那段时间”概括与待跟进事项。
- 关键词／语义召回，遗忘曲线，有上限的背景强化，选中后才唤醒冻结记忆。
- 全部派生数据按会话隔离；自动改写标为推断，不覆盖用户确认的事实。
- 原子批次、失败重试、审计撤销、回收站与数据库备份。
- AstrBot 配置面板、模型工具、管理命令、中文与英文说明。

要求 Python 3.11+、AstrBot 4.29.x。向量服务可选，复用 AstrBot 中配置的 embedding 提供商。

安装 ZIP 时使用目录 `astrbot_plugin_human_brain_memory`。
此版本为预发布：请先在测试账号中验证。没有自动导入原 QQ Bot 数据库、跨会话共享或独立 Web 控制台。
