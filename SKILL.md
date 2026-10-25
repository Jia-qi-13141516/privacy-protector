---
name: privacy-assistant
description: 下载、校验并安装隐私保护Skill，在本地后台处理表格或摘录文档；只读取安装包和状态，不把真实材料交给云端模型。
metadata:
  version: "0.10.0"
---

# 隐私保护Skill

用户要求安装本仓库时，完成以下步骤，不让用户选择技术参数。

1. 读取本目录 `release-lock.json`，把其中完整 ZIP 下载到新的本地临时目录。仅接受锁定的本仓库 HTTPS Release 地址及 GitHub 官方资产重定向，限制下载大小。先核对 SHA-256，一致后才解压、执行；失败即停止。
2. 读取解压后的 `privacy-assistant/SKILL.md`。在该目录执行 `scripts/auto_setup.py --agent codex|claude|workbuddy`，根据当前客户端选定参数。Windows 使用包内 `runtime/python.exe -I -B`；Mac 使用 Python 3.9+。不追加 `--open`，不启用旧向导。Mac 缺少 Python 时使用官方安装渠道，遇到系统授权或单位限制如实说明，不绕过。
3. 等待本机 `Settings/background-setup.json`。只有 `phase: ready` 且 `self_test_passed: true` 才报告自检通过；安装已启动不等于可用。`self_testing` 时继续等待；`blocked` 时说明固定 `message`。复用记录不能说成重新试跑。
4. 后续使用已安装的后台入口提交任务。只传本地路径和任务，不读取真实原件；未提供路径时让程序打开本地文件选择器。只读取任务状态，返回本地结果链接，不读取真实结果、映射、日志或代号稿。

完整包自动准备本地组件，首次模型下载约1.1GB，之后复用。任务自动排队，资源或保护检查失败时停止；不切换云端、不降低保护、不让教师手工调参。无需重新登录原Agent；Windows首次系统管理员授权或重启仍需本人完成，不索取或迁移凭据。

0.10.0为公开测试版：已在Apple M5 / 24GiB Mac上实测；8GB电脑、Windows / WorkBuddy和Intel Mac尚未完成实机验收。不可把代码适配或模拟测试说成整机通过。纯云端Agent没有本机执行通道时无法安装。此流程不撤销宿主Agent原有文件权限。

能力、用法与边界见 `README.md`；不要承诺任意表格分析、生成式文档改写或自动提交业务系统。
