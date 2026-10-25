"""SYSTEM-owned VM state; reuse the existing no-NIC processing engine."""
import json,os,shutil,uuid
from pathlib import Path
import windows_store as permissions

class Worker:
    def __init__(self,root,state,backend):
        self.root=Path(root);self.state=Path(state);self.backend=backend
        permissions.secure_dir(state)
    def self_test(self):
        # Guest runs the same real model and the existing nine synthetic checks.
        return self.backend.rpc('offline',{'action':'self_test','id':uuid.uuid4().hex})
    def __call__(self,private_job,source,instruction):
        permissions.root_only();permissions.assert_private_file(source)
        from background_windows import execute
        from document_engine import docx_text
        reply=execute(self.state,private_job,{'source':str(source),'instruction':instruction},lambda *unused:None,self.backend)
        if reply.get('kind')=='document':
            text=docx_text((private_job/'result.docx').read_bytes())
            (private_job/'result.txt').write_text(text,encoding='utf-8')
        for name in ('result.xlsx',) if reply.get('kind')=='table' else ('result.docx','result.txt'):
            permissions.assert_private_file(private_job/name)
        return reply
