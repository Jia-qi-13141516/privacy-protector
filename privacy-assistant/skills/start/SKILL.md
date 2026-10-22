---
name: privacy-assistant
description: 安装或打开隐私保护Skill。自动配置后台组件，只接收安装包，原始表格由本地窗口选择。
metadata:
  version: "0.7.0"
---

# 隐私保护Skill

执行插件根目录 `scripts/auto_setup.py --agent codex|claude|workbuddy`，选择当前客户端；Windows 使用包内 `runtime/python.exe -I -B`，macOS 使用本地 Python 3。不要让老师抄命令或编辑配置。完整操作边界见根目录 `SKILL.md`。

Windows 自动安装持久环境后打开受保护 WorkBuddy。已有环境与登录资料保留。安装开始、文件复制完成不等于隔离就绪；以本地自动验收结果为准。当前宿主聊天窗口不会因此受到隔离。只处理安装包，不读取原表、映射、私有状态文件或实名导出表；失败不能退回不隔离模式。

macOS 使用 Codex 或 Claude Code 命令行入口；先在本地窗口选表，再到受保护的新会话说任务，结果回到本地确认。不要从当前聊天读取用户原表。
