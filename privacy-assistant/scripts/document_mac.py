"""Local macOS document UI. Original text and identity review never enter chat."""
import hashlib
from pathlib import Path
import subprocess
import uuid
import task_channel as ch


def run(agent, base, selected=None):
    import assistant
    import mac_workflow as ui
    assistant.check_package(); agent=ui.pick_agent(agent)
    probe=subprocess.run([ui.sys.executable,'-B',str(ui.ROOT/'scripts/python_entry.py'),
        str(ui.ROOT/'skill/scripts/agent_boundary.py'),'--vault',str(base/'Vault'),
        '--exchange',str(base/'Exchange'),'--check'],capture_output=True,timeout=30)
    if probe.returncode:raise ValueError('boundary_failed')
    identifier=uuid.uuid4().hex;task=base/'Vault'/identifier;p=task/'private';p.mkdir(parents=True,mode=0o700)
    if selected is None:
        selected=ui.dialog('''set picked to choose file with prompt "选择 Word、文本或纯文字 PDF；原文件不进入聊天。"
return POSIX path of picked''')
    source=Path(selected)
    ch.regular(source)
    if source.suffix.lower() not in ('.txt','.md','.docx','.pdf'):raise ValueError('document_format')
    # Supplement rules locally. Empty input is valid, but still requires review.
    value=ui.dialog('''display dialog "补充需要隐藏的姓名、机构、地点或事件短语，每行一个。自动规则不能识别所有隐私；下一步仍须检查脱敏稿。" default answer "" with title "文档保护" buttons {"取消", "继续"} default button "继续"
return text returned of result''')
    terms=[v.strip() for v in value.splitlines() if v.strip()]
    ch.put_json(p/'input.json',{'source':str(source),'terms':terms})
    ui.worker('document_prepare',task)
    subprocess.run(['/usr/bin/open','-a','TextEdit',str(p/'draft.txt')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    ui.choose('已在本地打开脱敏稿。检查并删除仍可识别身份的细节，保存文件；不要改动 ⟦PVT_…⟧ 代号。确认后才会交给 Agent。', ['已检查并保存，允许提供给 Agent'])
    # Re-read and freeze after edits, then show exactly the reviewed snapshot.
    reviewed=ch.read(p/'draft.txt',1024*1024).decode('utf-8-sig')
    ch.put_json(p/'approval.json',{'text':reviewed,'sha256':hashlib.sha256(reviewed.encode()).hexdigest()})
    ui.worker('document_approve',task)
    exchange=base/'Exchange'/identifier;exchange.mkdir(mode=0o700)
    ch.write(exchange/'document.txt',ch.read(p/'approved.txt'),True)
    instructions=(ui.ROOT/'features/document/AGENT_TASK.md').read_bytes()
    ch.write(exchange/'AGENTS.md',instructions,True)
    ui.launch_agent(agent,task,exchange,base,document=True)
    ui.choose('在新开的受保护 Agent 窗口说明摘要、改写或整理任务。保存 result.txt 后回到这里。', ['结果已生成，开始本地核验'])
    ch.write(p/'returned.txt',ch.read(exchange/'result.txt',1024*1024),True)
    restore=ui.choose('导出时是否恢复本地保存的身份信息？摘要可能省略部分代号，请核对人与事件的对应关系。', ['保留代号','本地恢复身份'])=='本地恢复身份'
    ch.put_json(p/'result-options.json',{'restore':restore})
    ui.worker('document_preview',task)
    subprocess.run(['/usr/bin/open','-a','TextEdit',str(p/'review-result.txt')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    kind=ui.choose('已打开完整结果。请核对事实、遗漏和身份对应；程序无法判断 AI 是否改变了原意。确认后选择导出格式。',['已核对，导出 Word','已核对，导出文本'])
    extension='.docx' if kind.endswith('Word') else '.txt'
    reviewed=ch.read(p/'review-result.txt').decode()
    ch.put_json(p/'export-options.json',{'sha256':hashlib.sha256(reviewed.encode()).hexdigest(),'extension':extension})
    ui.worker('document_export',task)
    destination=base/'Vault/Exports'/('文档结果-'+identifier[:8]+extension)
    ch.write(destination,ch.read(p/('final'+extension)),True)
    subprocess.run(['/usr/bin/open','-R',str(destination)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    assistant.notify('文档结果已保存在本地。导出为干净正文，不保留原始批注、附件或复杂版式。')
