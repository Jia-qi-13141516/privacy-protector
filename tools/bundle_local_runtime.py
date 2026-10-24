"""Bundle pinned inference binaries, never user files or model weights."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'privacy-assistant/scripts'))
from component_download import fetch, digest

LICENSES = {
    'LICENSE-llama.cpp.txt': (
        'https://raw.githubusercontent.com/ggml-org/llama.cpp/b11856/LICENSE',
        '94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d'),
    'LICENSE-Qwen.txt': (
        'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/LICENSE',
        '832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e'),
}


def main():
    dest = ROOT / 'privacy-assistant/runtime/inference-assets'
    dest.mkdir(parents=True, exist_ok=True)
    spec = json.loads((ROOT / 'privacy-assistant/backend/local-model.json').read_text())
    for platform, asset in spec['runtimes'].items():
        target = dest / (asset['sha256'] + '.gz')
        if target.exists():
            if digest(target) != asset['sha256']:
                raise ValueError('bundled_runtime_integrity')
        else:
            shutil.copyfile(fetch(asset, ROOT / '.build-cache/inference'), target)
        print(platform + ': verified')
    for name, (url, expected) in LICENSES.items():
        target = dest / name
        if target.exists():
            data = target.read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=45) as response:
                data = response.read(65537)
        if len(data) > 65536 or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('license_integrity')
        target.write_bytes(data)
        print(name + ': verified')


if __name__ == '__main__':
    main()
