---
name: privacy-protector
description: 通过本地保护组件处理敏感表格和文档。只提交任务和读取状态，由独立权限窗口选文件、核对结果并在确认后导出。
metadata:
  version: "0.11.0-dev"
---

# Privacy Protector

用户只需说任务、选文件、确认结果。保留当前 Agent 的登录状态，不创建第二个在线聊天环境。

首次使用运行安装包的 `scripts/auto_setup.py --agent codex|claude|workbuddy`。安装器自动选择平台和组件；Windows 使用包内 `runtime/python.exe -I -B`，Mac 使用包内对应架构的 `runtime-macos-arm64/bin/python3` 或 `runtime-macos-x86_64/bin/python3`。操作系统首次授权必须由本人完成，不索取密码或绕过系统策略。安装器返回启动状态不等于自检通过。

随后用本机受保护入口执行 `health`。仅 `ready: true` 且 `self_test_passed: true` 才提交业务任务；准备和下载期间自动等待，约每10秒查询一次。`blocked` 时说明固定错误，不退回旧入口，不上传文件，不要求老师手工配置。`self_test_reused` 只能表述为复用已合格检查。

提交：`client.py submit --task "具体任务"`。不接受 `--input`，不打开真实原件或把它当聊天附件。选文件与确认导出由本地受保护窗口完成。用 `client.py status --id 任务编号` 查询；需要重开结果窗口时用 `client.py review --id 任务编号`。不要读取保护区、映射或结果正文替用户核对。

任务只包含工作要求，避免在聊天中粘贴学生姓名、账号或原文。表格支持明确数值筛选、排序、统计和已有跟进列功能；文档为本地模型选段与原文摘录。不承诺任意分析或改写，不把生成文件说成已经导入业务系统。

确认导出的普通文件可能被其他软件读取；原件继续受保护。主动取回原件会恢复其普通访问。这不能撤销保护前已复制、读取或上传的数据，也不防范管理员提权或屏幕读取。

开发源码尚未通过完整平台验收时，安装器必须停止。不得把源码、组件测试或临时测试机结果说成老师电脑已通过验收。
