---
name: privacy-assistant
description: 后台安装并运行隐私保护Skill。让用户说任务、选文件，自动完成本地表格处理或文档摘录，不把原件传给云端模型。
metadata:
  version: "0.10.0"
---

# 隐私保护Skill

安装时运行包内 `scripts/auto_setup.py --agent codex|claude|workbuddy`。Mac 使用 Python 3.9+；Windows 使用包内 `runtime/python.exe -I -B`。默认后台安装，不追加 `--open`，不打开旧向导或让用户选择技术选项。

安装后轮询 `Settings/background-setup.json`；只有 `ready` 且 `self_test_passed: true` 才算通过。程序会自动用虚构表格/文档试跑、测量资源并启用省内存模式。`self_testing` 时继续等待；`blocked` 时说明 `message`，不让用户选技术参数、不转云端或放宽隔离。后续同版本复用合格检查，每个任务仍重新检查当前可用内存与断网保护。

使用安装目录的 `scripts/background.py submit --task "用户任务"`。只在用户未提供路径时出现一次本地文件选择；已给路径就传 `--input`，不要读取其内容。根据返回 id 用 `background.py status --id` 查看进度。只读状态，给用户本地结果链接，不读取真实输出、映射、日志或脱敏稿。

表格支持明确数值筛选、数值排序、统计和统一跟进/优先级列；文档支持提取式摘要、待办摘录。分析在本地断网环境进行，代号稿也不交给云端模型。原 Agent 无需重新登录。首次模型下载约 1.1 GB。系统管理员授权不能由 Skill 绕过。

详细能力与限制见安装包根目录 SKILL.md。保护只覆盖此流程，不会撤销其他工具已获准的文件访问。不得把失败任务改成上传原件，也不得声称 Windows 已通过实机验收。
