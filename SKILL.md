---
name: privacy-assistant
description: 下载并安装隐私保护 Skill，或打开已安装的本地助手。只读取安装包，原始表格必须由本地窗口选择。
metadata:
  version: "0.6.2"
---

# 隐私保护 Skill

用户要求安装本仓库的 Skill 时，自动获取完整安装包，不让用户手工配置运行环境。

1. 读取本目录 `release-lock.json`，从其中固定的 HTTPS 地址下载 ZIP 到新的本地临时目录。只允许该仓库的 Release 地址及 GitHub 官方资产重定向，不接受替换来源；下载大小不得超过锁文件上限。
2. 计算 ZIP 的 SHA-256，必须与锁文件一致后才能解压或执行。下载或校验失败则停止，不执行未核验的文件。Windows 可使用自带 PowerShell 的下载、散列与解压命令，无需先安装 Python。
3. 解压后，读取包内 `privacy-assistant/SKILL.md`。Windows 使用包内 `runtime/python.exe -I -B scripts/auto_setup.py --agent workbuddy|codex|claude`，按当前本地客户端选参数，工作目录为解压后的 `privacy-assistant`。
4. 安装器完成后台配置和本地自检。首次系统授权与服务商登录由本人操作；不要索取或迁移登录凭据。以程序回执为准，开始安装不等于已经启用隔离。

完整安装包已带有运行库。再次打开时使用本机已安装的启动入口，保留运行磁盘与账号资料。失败不能改走不隔离模式，也不能让用户上传原表替代。

Windows 发起安装的入口可以是 WorkBuddy、Codex 或 Claude Code；受保护工作环境统一使用独立 WorkBuddy。主机上的当前聊天窗口不会因此被隔离。macOS 只有包内明确说明的有限命令行隔离；纯云端 Agent 没有本机执行通道时不能完成本地部署。

仅接触安装包和固定状态回执。不要读取原表、身份映射或实名成果；实际使用通过“说任务 → 本地选文件 → 本地确认结果”完成。范围与验证状态见 `README.md` 和 `docs/compatibility.md`。
