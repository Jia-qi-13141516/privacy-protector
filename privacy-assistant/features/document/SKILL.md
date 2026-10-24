---
name: privacy-document
description: 隐私保护Skill的文档功能。本地提取TXT、Markdown、基础DOCX或纯文字PDF，经脱敏预览确认后进行摘要、改写或整理，本地核验并可选恢复身份。
---

# 文档保护

从包根目录后台安装隐私保护Skill。仅明确需要旧版本地向导时打开 `--open`；选定文件后自动识别文档功能。只接触安装包；不能读取原件、词表、脱敏前的预览或身份映射。安装入口与平台条件遵循根目录 SKILL.md。

Mac 独立入口为 `scripts/mac_workflow.py codex document`（或 `claude document`）；Windows 隔离 WorkBuddy 内使用 `guest_client.py new --kind document`。

原件在本地提取正文，使用者补充需要隐藏的姓名、机构、地点、事件短语，并检查脱敏稿。只有本地确认后，document.txt 才可进入受保护 Agent 会话。规则不能保证识别全部隐私，更不能保证剩余叙述无法重识别。标密材料不进入联网流程。

受保护会话使用本目录 AGENT_TASK.md 的文档约束，输出纯文本 result.txt。摘要可能省略代号；本地验证不等于事实或语义正确，使用者须核对人与事件对应。默认保留代号，恢复身份须在本地单独选择，再确认导出干净 DOCX 或 TXT。

仅支持 UTF-8 TXT/MD、基础 DOCX 和可提取文字且不带图片/表单/附件的 PDF。拒绝加密文件、扫描件、图片、宏、外链、修订、批注、脚注等暂不支持内容；导出不保留复杂版式。自由文本能力不属于表格功能，不将其 CSV 新增列限制混用到文档。
