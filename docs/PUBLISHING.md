# 发布 0.1.0

显示名称：**Human Brain Memory Framework（人脑记忆框架）**。

- GitHub 仓库：`Yurdos-r/human_brain_memory`
- AstrBot 部署目录／插件 ID：`astrbot_plugin_human_brain_memory`
- Git tag / Release：`v0.1.0`
- Python 包版本：`0.1.0`
- 许可证：MIT

## 开发验证与打包

```bash
python -m venv .venv
# 激活虚拟环境后：
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q
python scripts/package_release.py
```

GitHub Actions 覆盖 Windows/Linux、Python 3.11/3.12。自动化测试使用临时数据库、确定性模型和模拟 SDK；实际平台通信、模型输出质量及多插件协作需要在部署环境中验证。

打包脚本按源码白名单生成插件 ZIP、内容清单和 SHA-256 校验文件，输出到 `dist/`。

## 发布新版本

1. 更新 `metadata.yaml`、`pyproject.toml`、打包脚本中的版本号及版本记录，保持 Git 标签和 Python 包版本对应。
2. 完成开发验证与下方部署检查，将变更提交到仓库。
3. 为该提交创建新的版本标签并推送。GitHub Actions 会测试、打包并创建正式版本并标记为最新版本；已发布的标签保留不动。
4. 发布正文使用 `docs/RELEASE_NOTES.md`，围绕该版本的能力、安装与使用说明编写。

也可手工创建 Release，选择正式发行并设为 Latest，上传 `dist/` 中的插件 ZIP 和 `SHA256SUMS.txt`。
发布工作流使用仓库自带的 `GITHUB_TOKEN`，需要 `contents: write` 权限。

## 发布前的真实环境验证

自动化测试不能替代真实 AstrBot 部署。建议使用测试账号完成：

1. 从 ZIP 安装，确认插件显示 0.1.0，配置面板可保存，四个工具被识别。
2. 私聊记录“我不是医生”，确认原话保留；群里检索不到私聊内容。
3. 换一个平台实例／账号，确认同名用户不会复用其他实例的私聊。
4. 管理员执行 `/memory consolidate`，确认事实、画像和游标更新；普通用户不能调用此管理命令。
5. 关闭向量提供商后，聊天仍可正常回复并使用关键词召回。
6. 关闭、重载插件，确认没有重复后台任务，之前记忆仍在。
7. 新建备份，在停机状态下使用备份副本恢复，确认记录可读取。

## 发布文件

发布内容包含框架源码、AstrBot 适配入口、配置说明与使用文档。运行数据库、聊天记录、备份、环境变量和密钥保存在部署环境中，不纳入发布包。
