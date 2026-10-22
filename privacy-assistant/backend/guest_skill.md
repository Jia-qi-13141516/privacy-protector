---
name: privacy-assistant
description: 在本地隐私助手的隔离环境内处理学生表格；自动请求选文件、分析代号数据，并提交本地回填。真实原表由本机窗口处理。
---

# 本地表格隐私保护 Skill

当用户提出含身份信息的表格任务，先了解所需分析和结果，再执行：

`python3 /opt/privacy-bridge/guest_client.py new`

本机将自动打开文件选择和字段窗口。不要让用户把原表拖入聊天，也不要尝试访问主机、内网、其他资料库或保护区。只能处理本次用户允许提供的代号表；去掉姓名不等于不可识别。

用 `python3 /opt/privacy-bridge/guest_client.py status --id 任务编号` 查看进度。在等待用户时不重复新建任务；状态为 ready_for_agent 后，读取返回工作目录中的 columns.json 和 data.csv。columns.json 只给出受控的常见字段含义；不得要求用户把完整原表列名复制进来。数值保留原精度，分类值使用中性代号。根据任务分析，需要的字段含义不明时先确认，不猜测分类代号含义。

生成同一目录的 result.csv，保留全部原列和列序、原代号与原值。允许筛选记录；允许在末尾增加 follow_up（yes/no）和 priority（0—3），不支持自由文本、公式或其他新增列。输出应与用户任务有关，不能自动把学生分数解释成心理诊断。

然后执行 `python3 /opt/privacy-bridge/guest_client.py submit --id 任务编号`。本机自动回填身份并请用户核对，生成导入 Excel。读取 status 直到 completed / cancelled / blocked。实名结果保存在本机，不请求打开、不上传、不复制到本工作目录。用户确认与系统导入是两件事，未实际导入不能称已经提交系统。
