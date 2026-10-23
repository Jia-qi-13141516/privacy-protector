# 源码与构建

日常安装使用 Release 中的完整 ZIP。GitHub 的 Source code ZIP 不含 Windows 运行环境；仓库入口 Skill 可根据 `release-lock.json` 获取完整安装包。

## 构建安装包

使用 Python 3.9 或更新版本，在仓库根目录运行：

```sh
python3 tools/prepare_runtime.py
python3 tools/build_release.py --archive
```

第一个命令根据固定版本和 SHA-256 下载 Python 官方 NuGet 包及三个纯 Python wheel，并保留原许可证。第二个命令生成文件清单和安装 ZIP，输出到 `dist/`。构建缓存与运行环境不纳入 Git。

## 回归测试

完整测试套件需要 macOS 的 `sandbox-exec`：

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

其他系统可运行不依赖 macOS 隔离器的组件测试：

```sh
python3 -m unittest discover -s tests -p 'test_persistent_backend.py' -v
```

`tests/linux_roundtrip.py` 和 `tests/linux_security.py` 用于独立的临时 Linux 测试环境，需要 root、网络命名空间及已部署的固定处理脚本。不要在日常办公系统中直接运行它们。测试只使用代码生成的虚构记录。

## 目录

- `privacy-assistant/`：安装器、后台组件、插件入口和本地交互。
- `local-table-privacy/scripts/`：脱敏、结果校验和身份回填引擎。
- `tests/`：安装器与持久环境回归测试。
- `tools/`：依赖锁定和发布包构建。

更改程序内容后应增加版本号并重新构建文件清单，避免同一版本出现不同内容。包内散列用于发现文件损坏或变化，不替代发布者身份验证。

## 重现首页演示

在 macOS 上准备包内表格依赖及 Pillow，运行：

```sh
python3 tools/build_readme_demo.py
```

脚本现场生成 60 条虚构记录，调用本地离线处理程序，按固定规则模拟 Agent 结果，核对筛选、身份回填和原表完整性，再生成首页 GIF、静态结果图与核验记录。它不调用云端模型，也不读取业务资料。图中文字使用系统字体 Hiragino Sans GB。
