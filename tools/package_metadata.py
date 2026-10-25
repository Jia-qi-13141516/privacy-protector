"""Portable ZIP metadata: Mac entrypoints must retain execute permissions."""
import stat,zipfile

def member(name,executable=False):
    value=zipfile.ZipInfo(name,(2000,1,1,0,0,0))
    value.create_system=3
    value.compress_type=zipfile.ZIP_DEFLATED
    value.external_attr=(stat.S_IFREG|(0o755 if executable else 0o644))<<16
    return value
