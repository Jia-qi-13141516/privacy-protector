---
name: privacy-table
description: 隐私保护Skill的独立表格功能。处理XLSX/CSV的数值统计、分类汇总、筛选、限定新增列与本地身份回填。
---

# 表格保护

从包根目录安装并打开隐私保护Skill，在本地选择“表格保护”。只接触安装包，不从聊天读取原表。安装入口与平台条件遵循根目录 SKILL.md。

Mac 独立入口是 `scripts/mac_workflow.py codex table`（或 `claude table`）；Windows 隔离 WorkBuddy 内使用 `guest_client.py new --kind table`。这些入口只能由已经校验安装的包调用。

保留全部原代号、原列和原值；可筛选记录，新增 follow_up（yes/no）、priority（0—3）。保存 result.csv 后由本地窗口核验、回填、确认导出。任意新列、自由文本和公式不在此功能范围。
