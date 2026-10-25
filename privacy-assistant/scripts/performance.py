"""Automatic resource checks and bounded local inference; no material contents."""
import ctypes
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MIB = 1024 ** 2
GIB = 1024 ** 3
PROFILE = {'name': 'compact', 'context': 8192, 'batch': 128, 'ubatch': 64,
           'threads': 2, 'max_rss_bytes': 2 * GIB, 'timeout_seconds': 120}
ERROR_MESSAGES = {
    'memory_below_requirement': '这台电脑的总内存低于8GB，本版暂不支持；尚未读取业务文件。',
    'available_memory_low': '当前可用内存不足。请关闭占内存的应用后重试，程序会自动重新检查，无需设置参数。',
    'resource_probe_failed': '无法可靠检查本机资源，已停止处理；未关闭隐私保护。',
    'memory_monitor_unavailable': '无法监测本地推理的内存占用，已停止处理。',
    'inference_memory_limit': '本地推理超过省内存模式的占用上限，已停止；没有转到云端。',
    'worker_memory_limit': '材料处理超过本地内存占用上限，已停止；没有上传材料或降低隐私保护。',
    'inference_timeout': '本地推理未能在规定时间内完成，已停止；没有转到云端。',
    'local_inference_failed': '本地模型未能正常运行，可能存在资源或组件兼容问题，已停止处理。',
    'self_test_slow': '虚构材料试跑耗时过长，这台电脑暂未通过性能自检；尚未读取业务文件。',
    'self_test_result_mismatch': '虚构材料的处理结果未通过核验，已停止启用；尚未读取业务文件。',
    'self_test_failed': '首次虚构材料自检未通过，尚未启用业务文件处理。',
    'isolation_failed': '未通过本地断网保护检查，已停止处理；不会放宽保护或上传原件。',
    'runtime_integrity': '本地组件校验失败，已停止处理。',
    'windows_x64_required': '本版Windows组件需要Intel或AMD的64位电脑；当前设备架构不支持。',
    'windows_version_unsupported': 'Windows版本过旧，需要Windows 10 2004或更新版本。',
    'firmware_virtualization_disabled': '本机未提供所需的硬件虚拟化支持，无法启用Windows隔离环境；已停止。',
    'disk_space_insufficient': '可用磁盘空间不足，无法准备或运行隔离组件；释放空间后可直接重试。',
    'restart_required': '系统组件安装需要重启电脑，重启后重新启动即可；无需手工设置参数。',
    'local_runtime_unsupported': '当前设备或系统架构不受本地运行组件支持，已停止处理。',
    'component_timeout': '本地组件未能在规定时间内响应，已停止处理；没有降低隐私保护。',
    'component_command_failed': '本地组件未能正常完成，可能存在资源或兼容问题；已停止，未转到云端。',
}


def _command(args):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=10).stdout


def mac_available(text):
    page = re.search(r'page size of (\d+) bytes', text)
    counts = dict(re.findall(r'^(Pages (?:free|inactive|speculative)):\s+(\d+)\.', text, re.M))
    if not page or len(counts) != 3:
        raise ValueError('resource_probe_failed')
    # Conservative reclaimable-page estimate; never include compressed/swap memory.
    return int(page[1]) * sum(int(v) for v in counts.values())


def hardware():
    try:
        if sys.platform == 'darwin':
            total = int(_command(['/usr/sbin/sysctl', '-n', 'hw.memsize']))
            cores = int(_command(['/usr/sbin/sysctl', '-n', 'hw.physicalcpu']))
            available = mac_available(_command(['/usr/bin/vm_stat']))
        elif sys.platform == 'win32':
            class Memory(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                    (n, ctypes.c_ulonglong) for n in ('total', 'available', 'page_total',
                    'page_available', 'virtual_total', 'virtual_available', 'extended')]
            info = Memory(); info.length = ctypes.sizeof(info)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
                raise ValueError('resource_probe_failed')
            total, available, cores = info.total, info.available, os.cpu_count() or 1
        elif sys.platform == 'linux':
            fields = dict(re.findall(r'^(MemTotal|MemAvailable):\s+(\d+) kB',
                                    Path('/proc/meminfo').read_text(), re.M))
            total, available, cores = int(fields['MemTotal']) * 1024, int(fields['MemAvailable']) * 1024, os.cpu_count() or 1
        else:
            raise ValueError('resource_probe_failed')
        if not 0 < available <= total or cores < 1:
            raise ValueError('resource_probe_failed')
        return {'platform': sys.platform, 'total_bytes': total, 'available_bytes': available, 'cores': cores}
    except Exception:
        raise ValueError('resource_probe_failed') from None


def require_capacity(info, vm_running=False, guest=False):
    if not guest and info['total_bytes'] < 7 * GIB:
        raise ValueError('memory_below_requirement')
    # Windows reserves 3 GiB for the offline VM; do not reserve it twice once running.
    needed = 1792 * MIB if guest else (512 * MIB if vm_running else 3584 * MIB) if info['platform'] == 'win32' else 2560 * MIB
    if info['available_bytes'] < needed:
        raise ValueError('available_memory_low')
    return info


def resident_bytes(pid):
    if sys.platform == 'darwin':
        # PROC_PIDTASKINFO, as declared in Apple's sys/proc_info.h.
        class TaskInfo(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ('virtual', 'resident', 'user', 'system', 'threads_user', 'threads_system')] + [
                (n, ctypes.c_int32) for n in ('policy', 'faults', 'pageins', 'cow', 'sent', 'received', 'mach', 'unix', 'csw', 'threads', 'running', 'priority')]
        lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        lib.proc_pidinfo.restype = ctypes.c_int
        info = TaskInfo()
        if lib.proc_pidinfo(pid, 4, 0, ctypes.byref(info), ctypes.sizeof(info)) != ctypes.sizeof(info):
            return None
        return info.resident
    if sys.platform == 'linux':
        try:
            match = re.search(r'^VmRSS:\s+(\d+) kB', Path('/proc').joinpath(str(pid), 'status').read_text(), re.M)
            return int(match[1]) * 1024 if match else None
        except OSError:
            return None
    return None


def guard_worker(pid):
    value = resident_bytes(pid)
    if value is None:
        raise ValueError('memory_monitor_unavailable')
    if value > PROFILE['max_rss_bytes']:
        raise ValueError('worker_memory_limit')


def inference(command, stdout_path, stderr_path):
    """Poll only the fixed inference child. Abort on excess RSS, timeout or probe failure."""
    import task_channel as ch
    ch.regular(stdout_path); ch.regular(stderr_path)
    start = time.monotonic(); peak = 0; misses = 0
    with stdout_path.open('xb') as out, stderr_path.open('xb') as err:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                   close_fds=True, env={k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG') if k in os.environ})
        try:
            while process.poll() is None:
                value = resident_bytes(process.pid)
                if value is None:
                    misses += 1
                    if misses >= 10 and process.poll() is None:
                        raise ValueError('memory_monitor_unavailable')
                else:
                    misses = 0; peak = max(peak, value)
                    if peak > PROFILE['max_rss_bytes']:
                        raise ValueError('inference_memory_limit')
                if time.monotonic() - start > PROFILE['timeout_seconds']:
                    raise ValueError('inference_timeout')
                time.sleep(.05)
            if process.returncode:
                raise ValueError('local_inference_failed')
            if not peak:
                raise ValueError('memory_monitor_unavailable')
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    return {'elapsed_seconds': round(time.monotonic() - start, 3), 'peak_rss_bytes': peak}
