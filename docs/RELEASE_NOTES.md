# Human Brain Memory Framework · 1.0 Beta

人脑记忆框架为对话应用提供持久化记忆，支持直接接入 AstrBot，也可作为独立 Python 核心嵌入其他应用。

## 核心能力

- **记住事实与经历**：保存偏好、习惯和重要信息，将聊天整理为带有消息依据与情绪信息的经历。
- **形成长期认识**：定期整理人物画像、自我回顾和待跟进事项。
- **按话题召回**：关键词检索与可选向量召回，在回复前加入相关记忆背景。
- **遗忘、强化与概括**：普通记忆逐步淡化，相关回忆得到强化，逐渐淡忘的经历形成“那段时间”的概括。
- **管理记忆**：支持确认、纠正、置顶、回收站恢复、整理批次撤销和数据库备份。
- **会话隔离**：按平台实例、机器人账号和会话管理全部记忆。

## 安装与使用

1. 准备 Python 3.11+、AstrBot 4.29.x，并启用聊天模型。
2. 在 AstrBot 插件管理中使用仓库地址 `https://github.com/Yurdos-r/human_brain_memory` 安装；也可下载下方插件 ZIP，解压到 `data/plugins/astrbot_plugin_human_brain_memory/` 后重新加载插件。
3. 在配置面板设置 `summary_provider_id`，留空则跟随当前会话模型；填写 `embedding_provider_id` 可启用语义召回。
4. 发送以下命令，保存并查找第一条记忆：

```text
/memory status
/memory remember 我不喝咖啡
/memory search 咖啡
```

默认在空闲 30 分钟后整理经历，每天北京时间 04:00 后分批整理长期记忆。每轮最多加入 12 条记忆，背景总预算为 6000 字符，均可在配置面板调整。

完整命令、配置与 Python 接入示例见 [使用说明](https://github.com/Yurdos-r/human_brain_memory#readme)。
