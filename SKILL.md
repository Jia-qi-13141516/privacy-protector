---
name: privacy-protector
description: 通过独立权限的本地保护组件处理表格和文档，原 Agent 仅提交任务并查询状态；原件选择、核对和导出在受保护窗口完成。
metadata:
  version: "0.11.0-dev"
---

# Privacy Protector · 隐私保护 Skill

这是尚在平台验收中的开发源码。先检查 `privacy-assistant/protector/qualification.json`；未达到发布条件时，不安装、不宣称可用，也不下载较弱的历史安装包替代。现有 `release-lock.json` 指向的 0.10.0 不具备这里要求的原件访问隔离。

正式安装和任务流程见 `privacy-assistant/SKILL.md`。用户操作保持“说任务、选文件、确认结果”。任何权限、自检或资源检查失败时停止；不得退回同账号处理、上传材料或降低保护。

开发和测试只使用虚构材料与一次性测试环境。读取这个仓库不等于得到在开发者日常电脑部署服务、创建账号或改变文件权限的授权。
