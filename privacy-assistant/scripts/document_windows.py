"""Host-only document flow using the same offline/online VM boundary."""
import base64,hashlib,subprocess
from pathlib import Path
import task_channel as ch


def handle(base, backend, jobs, request, dialogue, safe_source):
    identifier=ch.task_id(request['id'])
    def status(phase):backend.rpc('online',{'action':'status','id':identifier,'phase':phase})
    def cancel():jobs.advance(identifier,'cancel');status('cancelled')
    if request['action']=='new_document':
        if jobs.path(identifier).exists():return
        jobs.create(identifier,'document')
        selected=dialogue(base,{'mode':'document_file'})
        if selected.get('cancelled'):cancel();return
        source=Path(selected['path']);data=safe_source(source,document=True)
        fields=dialogue(base,{'mode':'document_terms'})
        if not fields.get('confirmed'):cancel();return
        jobs.advance(identifier,'selected');backend.start('offline')
        draft=backend.rpc('offline',{'action':'document_prepare','id':identifier,'extension':source.suffix.lower(),
                           'data':base64.b64encode(data).decode(),'terms':fields['terms']})
        del source,data,selected
        review=dialogue(base,{'mode':'document_review','text':draft['draft']})
        if not review.get('confirmed'):cancel();return
        text=review['text'];digest=hashlib.sha256(text.encode()).hexdigest()
        approved=backend.rpc('offline',{'action':'document_approve','id':identifier,'text':text,'sha256':digest})
        backend.refresh_network()
        if backend.rpc('online',{'action':'health'}).get('status')!='online':raise ValueError('boundary_changed')
        backend.rpc('online',{'action':'deliver_document','id':identifier,'data':approved['data']})
        jobs.advance(identifier,'released')
        return
    if request['action']!='submit_result' or jobs.kind(identifier)!='document' or jobs.phase(identifier)!='ready_for_agent':
        raise ValueError('task_not_ready')
    options=dialogue(base,{'mode':'document_options'})
    if not options.get('confirmed'):cancel();return
    returned=backend.rpc('online',{'action':'document_result','id':identifier})
    backend.start('offline')
    preview=backend.rpc('offline',{'action':'document_preview','id':identifier,'data':returned['data'],'restore':options['restore']})
    jobs.advance(identifier,'result_received');status('waiting_for_confirmation')
    confirmation=dialogue(base,{'mode':'document_confirm','text':preview['text']})
    if not confirmation.get('confirmed'):cancel();return
    extension=confirmation['extension']
    if extension not in ('.txt','.docx'):raise ValueError('document_format')
    digest=hashlib.sha256(preview['text'].encode()).hexdigest()
    result=backend.rpc('offline',{'action':'document_export','id':identifier,'sha256':digest,'extension':extension})
    folder=base/'Vault/Exports'
    ch.write(folder/('文档结果-'+identifier[:8]+extension),ch.decode_blob(result['data']),exclusive=True)
    jobs.advance(identifier,'local_confirmed');status('completed')
    subprocess.Popen(['explorer.exe',str(folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
