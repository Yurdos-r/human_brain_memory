# 发布 1.0 Beta

显示名称：**Human Brain Memory Framework（人脑记忆框架）**。

- GitHub 仓库：`Yurdos-r/human_brain_memory`
- AstrBot 部署目录／插件 ID：`astrbot_plugin_human_brain_memory`
- Git tag / Release：`v1.0.0-beta.1`
- Python 包版本：`1.0.0b1`（同一 Beta 的 PEP 440 表示）
- 许可证：MIT

## 首次推送

1. 在自己的 GitHub 账号下创建空仓库（公开开源项目选择 Public）。
2. `metadata.yaml` 已填写 `https://github.com/Yurdos-r/human_brain_memory` 与作者 `Yurdos-r`。
3. 在当前项目目录执行：

   ```bash
   git init -b main
   git add .
   git commit -m "Release Human Brain Memory Framework 1.0 Beta"
   git remote add origin https://github.com/Yurdos-r/human_brain_memory.git
   git push -u origin main
   ```

   仓库已初始化时省略 `git init`；若已经配置 origin，不要重复添加。其他用户 fork 后使用自己的仓库地址。

4. 推送 tag，GitHub Actions 会执行测试、打包并创建 **Prerelease**：

   ```bash
   git tag v1.0.0-beta.1
   git push origin v1.0.0-beta.1
   ```

也可以手工创建 Release，勾选 Pre-release，上传 `dist/` 中的 ZIP 和 `SHA256SUMS.txt`，正文使用 `docs/RELEASE_NOTES.md`。
Actions 无需配置个人令牌，使用仓库自带的 `GITHUB_TOKEN`，需要允许 workflow 写入仓库内容。

## 发布前的真实环境验证

自动化测试不能替代真实 AstrBot 部署。建议使用测试账号完成：

1. 从 ZIP 安装，确认插件显示 1.0 Beta，配置面板可保存，四个工具被识别。
2. 私聊记录“我不是医生”，确认原话保留；群里检索不到私聊内容。
3. 换一个平台实例／账号，确认同名用户不会复用其他实例的私聊。
4. 管理员执行 `/memory consolidate`，确认事实、画像和游标更新；普通用户不能调用此管理命令。
5. 关闭向量提供商后，聊天仍可正常回复并使用关键词召回。
6. 关闭、重载插件，确认没有重复后台任务，之前记忆仍在。
7. 新建备份，在停机状态下使用备份副本恢复，确认记录可读取。

## 与原 QQ Bot 的关系

这是独立的新仓库。发布包不包含原 QQ Bot 的配置、QQ 号、聊天记录、数据库、环境变量或 API Key。
不要将原项目整个目录复制进这个仓库，也不要将运行数据提交到 GitHub。
原数据库不自动导入；需要迁移时，应明确目标会话映射、脱敏规则和备份策略后另做迁移工具。
