"""The Agent has only submit/status rights. Private operations need an OS identity."""
import json,re
MAX_REQUEST=8192
ID=re.compile(r'^[a-f0-9]{32}$')
PHASES={'waiting_for_file','sealing','queued','processing','waiting_for_confirmation','confirmed','blocked','cancelled'}
ERRORS={'invalid_request','forbidden','protection_unavailable','source_not_local','source_not_owned',
        'source_busy','linked_source','source_changed','source_too_large','source_acl_unsupported',
        'permission_probe_failed','private_store_insecure','task_missing','invalid_transition',
        'not_ready','self_test_failed','memory_below_requirement','available_memory_low','restart_required',
        'resource_probe_failed','memory_monitor_unavailable','inference_memory_limit','worker_memory_limit',
        'inference_timeout','self_test_slow','self_test_result_mismatch','runtime_integrity','windows_x64_required',
        'windows_version_unsupported','firmware_virtualization_disabled','disk_space_insufficient','local_runtime_unsupported',
        'component_timeout','component_command_failed','component_download_failed','local_inference_failed','isolation_failed','worker_failed','unsupported_platform','export_target_invalid','already_exists','ui_unavailable'}

def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise ValueError('invalid_request')
    return value

def decode(data):
    if not isinstance(data,bytes) or len(data)>MAX_REQUEST:raise ValueError('invalid_request')
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out:raise ValueError('invalid_request')
            out[key]=value
        return out
    try:obj=json.loads(data.decode('utf-8'),object_pairs_hook=unique)
    except (UnicodeError,TypeError,json.JSONDecodeError):raise ValueError('invalid_request') from None
    if not isinstance(obj,dict):raise ValueError('invalid_request')
    return obj

def public_request(obj):
    if obj.get('action')=='submit' and set(obj)=={'action','task'}:
        if not isinstance(obj['task'],str) or not 1<=len(obj['task'])<=2000 or '\x00' in obj['task']:raise ValueError('invalid_request')
    elif obj.get('action') in ('status','review') and set(obj)=={'action','id'}:identifier(obj['id'])
    elif obj.get('action')=='health' and set(obj)=={'action'}:pass
    else:raise ValueError('invalid_request')
    return obj

def private_request(obj):
    identifier(obj.get('id'))
    action=obj.get('action')
    allowed={'select':{'action','id','path'},'review':{'action','id'},
             'confirm':{'action','id','destination'},'cancel':{'action','id'},'restore':{'action','id'},'recover':{'action','id','destination'}}
    if action not in allowed or set(obj)!=allowed[action]:raise ValueError('invalid_request')
    for field in ('path','destination'):
        if field in obj and (not isinstance(obj[field],str) or not 1<=len(obj[field])<=4096 or '\x00' in obj[field]):raise ValueError('invalid_request')
    return obj

def status(record):
    """Never return a path, filename, text, schema, identity or private error detail."""
    out={'id':identifier(record['id']),'phase':record['phase'],'original_access':'os_denied' if record.get('sealed') else 'not_verified'}
    if out['phase'] not in PHASES:raise ValueError('invalid_transition')
    if out['phase']=='blocked':out['code']=record.get('code') if record.get('code') in ERRORS else 'worker_failed'
    return out

def failure(exc):
    code=str(exc)
    return {'error':code if code in ERRORS else 'worker_failed'}
