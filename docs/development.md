# 源码与构建

本分支包含尚未通过目标平台完整验收的访问隔离开发代码。默认安装入口和对外打包均关闭发布资格；不要把历史 Release 当作已具备同等保护的替代品。开发测试只用虚构材料和一次性环境，不给开发者日常电脑部署。

## 构建安装包

使用 Python 3.9 或更新版本，在仓库根目录运行：

```sh
python3 tools/prepare_runtime.py
python3 tools/bundle_local_runtime.py
python3 tools/bundle_protected_runtime.py
python3 tools/build_release.py
```

依次准备固定 Windows 运行库、推理组件、Mac 双架构便携 Python 与本地窗口，最后生成完整性清单。Mac 窗口构建需要 macOS 和 Swift 编译器。下载均使用固定 SHA-256 并保留许可，构建缓存不纳入 Git。此过程只在构建目录写文件，不注册服务。`--archive` 会在发布资格未满足时拒绝生成对外 ZIP。

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

这段45秒动画是流程重绘，不是软件界面录屏。画面中的数字、原文摘录与自检结果来自0.10.0真实后台流程；动画顺序、亮灯和低内存分支为示意。公开核验记录在 `docs/assets/demo-verification.json`。

在 Apple Silicon Mac 上准备完整0.10.0包及 `openpyxl`、Pillow。以下命令使用一个尚不存在的新临时目录，不改动日常安装；首次需要下载固定本地模型：

```sh
python3 tools/build_readme_demo.py verify \
  --package-dir privacy-assistant \
  --workdir /tmp/privacy-demo-fresh
python3 tools/render_readme_demo.py \
  --report /tmp/privacy-demo-fresh/demo-verification.json \
  --output /tmp/privacy-demo-rendered
```

已有模型缓存时，可在第一个命令添加 `--model-cache /path/to/model.gguf`，脚本先核对固定SHA-256，再复制到临时安装；此时自检耗时不包含下载。图中文字使用macOS的 Hiragino Sans GB 系统字体。

脚本从固定虚构内容生成8条表格记录和6段纪要，完成真实首次安装自检、表格筛选及身份回填、两次本地模型调用与原文摘录比对。原件散列必须保持不变。低内存分支另用模拟资源数值验证，不能替代8GB实机验收。只将经过核对的虚构内容和限定设备指标写入公开记录，不发布运行配置、任务编号或日志。

生成目录中的 `privacy-workflow.gif`、`demo-summary.png` 和 `demo-verification.json` 用于首页；`qa-*` 仅供本地检查。仓库附带的公开结果来自Apple M5 / 24GiB，不能代替其他设备的运行结果。

## 功能模块

`privacy-assistant/features/table/` 和 `features/document/` 共用后台入口，按本地文件后缀自动分流。旧版手动向导和云端交换代码仅保留为兼容实现，不由0.10.0默认入口启动。

## 0.10.0 后台入口

使用 `scripts/background.py submit --input <虚构文件> --task <任务>` 提交，用 `status --id <编号>` 读取完成状态。公开回复不含原文、脱敏稿或映射。数据处理由 `background_worker.py` 在OS断网环境执行；表格计算在 `background_engine.py`，文档调用固定的本地推理程序。

完整分享包需包含三种平台的推理压缩包及许可证。运行 `python3 tools/bundle_local_runtime.py` 下载、核对并打包这些固定组件，再运行 `python3 tools/build_release.py --archive`。模型权重不进Git或ZIP，由首次安装从固定ModelScope版本下载。运行 `python3 -m unittest discover -s tests -p 'test_*.py' -v`；真实模型验收单独记录，不能用单元测试或模拟输出替代。

首次验收由 `self_check.py` 在实际断网环境调用表格/文档引擎与本地模型。`performance.py` 自动检查可用内存并监测推理进程；运行资源超限、超时、输出不一致或隔离失败都不能写入ready。版本和运行参数变更使旧检查失效。硬件边界测试中的8GB信息是模拟输入，必须与真实模型试跑、8GB实机验收区分。

## 访问隔离组件

独立权限组件位于 `privacy-assistant/protector/`，验证范围见 [实现与验收](access-isolation.md)，复现说明见 [隔离测试](../tests/protector/README.md)。它已接入默认安装入口，首次自检与访问权限检查通过前不接受文件；在 `qualification.json` 的发布条件全部满足前，构建器拒绝生成对外安装包。源码测试、临时虚拟机试跑和正式部署是不同状态。
