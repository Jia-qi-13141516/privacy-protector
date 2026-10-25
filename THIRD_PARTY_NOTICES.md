# 第三方组件

本项目原创代码采用 Apache 2.0，原创文档采用 CC BY 4.0；具体范围见 LICENSING.md。以下第三方组件保留各自许可证，不受本项目许可变更影响。

安装包中的 Python 运行环境来自 Python 官方 NuGet 包。相关文件与原许可证随包保留：

| 组件 | 版本 | 许可或说明 |
| --- | --- | --- |
| CPython | 3.12.10 | PSF 及所包含组件的许可，见 `runtime/LICENSE.txt` |
| pip | 25.0.1 | MIT；供应商代码保留各自声明 |
| openpyxl | 3.1.5 | MIT，见对应 dist-info 的 `LICENCE.rst` |
| et_xmlfile | 2.0.0 | 见对应 dist-info 的 `LICENCE.rst` 与 `LICENCE.python` |
| pycdlib | 1.14.0 | LGPLv2，见对应 dist-info 的 `COPYING`；Python 源码随包提供 |

Python 官方包的说明：[Using Python on Windows](https://docs.python.org/3.12/using/windows.html#the-nuget-org-packages)。上述运行环境和库的下载地址、版本及 SHA-256 保存在 [运行库依赖清单](https://github.com/Jiaqi-Guo-0114/privacy-protector/blob/v0.7.0/tools/runtime-lock.json)。

VirtualBox 基础程序、Ubuntu 镜像、Microsoft Visual C++ 运行库和 WorkBuddy 在首次安装时从其官方来源下载，未作为本项目源代码重新许可。版本、下载地址及 SHA-256 见 [隔离组件清单](https://github.com/Jiaqi-Guo-0114/privacy-protector/blob/v0.7.0/privacy-assistant/backend/assets.json)。不安装 VirtualBox Extension Pack。

WorkBuddy 为第三方产品，使用其账号和服务须遵循对应条款。本项目不隶属于这些组件的提供方。

- pypdf：PDF 正文提取，BSD-3-Clause；固定版本及 SHA-256 见 tools/runtime-lock.json，许可证随 runtime/Lib/site-packages/pypdf-*.dist-info/licenses/LICENSE 分发。

0.9.0 的本地推理组件：

- llama.cpp b11856，MIT，来自 ggml-org 官方构建。三个平台的固定压缩包随安装 ZIP 提供，原许可证位于 runtime/inference-assets/LICENSE-llama.cpp.txt。
- Qwen2.5-1.5B-Instruct-GGUF（Q4_K_M），Apache 2.0，首次从 ModelScope 的官方 Qwen 仓库下载；不把权重塞入分享包。许可证位于 runtime/inference-assets/LICENSE-Qwen.txt。下载版本、大小和 SHA-256 固定在 privacy-assistant/backend/local-model.json。
- 模型出处：https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF 。推理程序出处：https://github.com/ggml-org/llama.cpp/releases/tag/b11856 。
