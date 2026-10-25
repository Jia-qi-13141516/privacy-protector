# 访问隔离测试

本目录只用于开发验证，不是 Skill 安装入口。所有素材由测试代码生成；不要替换为真实学生资料。

组件测试不会安装产品或创建系统账号：

```sh
python3 -B -m unittest discover -s tests/protector -p 'test_*.py'
```

`kernel_e2e.py` 必须在**无宿主目录挂载、可随时销毁的 Linux 虚拟机**内运行。它使用 `pp-agent` 和 `pp-worker` 两个不同账号，向真实系统权限发起读取、修改权限和私有接口请求；表格、文档均使用原有引擎，文档实际调用固定的本地模型。测试的私人窗口由测试程序模拟人类选择和确认，不能据此声称真实桌面窗口已经验收。

重现条件：Ubuntu ARM64、Python 3、`libgomp1`、`unshare`、`setpriv`，以及已核验的固定模型和 Linux ARM64 推理压缩包。程序源目录需有构建阶段生成的 `privacy-assistant/skill` 和纯 Python 运行库。模型、推理程序和依赖均在读取测试材料前准备完成。

`provision_guest.py` 仅接受新建的临时 Linux 虚拟机，并要求 root 所有的 `/etc/privacy-protector-disposable-test` 内容为 `fictional-materials-only`。它读取 `/tmp/protector-code.tar`、`/tmp/model.gguf` 和 `/tmp/llama-b11856-bin-ubuntu-arm64.tar.gz`，通过既有散列锁核验组件，建立仅用于测试的账号与目录。代码 tar 只包括 `privacy-assistant/` 与 `tests/protector/`，不包含个人安装目录、账号资料或业务文件。

在虚拟机内部准备完成后，先启动 `protector/service.py --config /etc/privacy-protector-test.json`，再运行 `/opt/privacy-protector/tests/kernel_e2e.py`。测试报告写到 `/tmp/protector-e2e-report.json`。保存报告后销毁虚拟机，不能把这一套测试配置用作办公电脑的安装方案。

虚拟机测试只证明所测系统权限和代码路径；Mac 与 Windows 的安装、真实 UI、实际客户端和 8GB 实机性能必须另验。

首次启动必须等待 `health.ready` 与 `self_test_passed` 都为真；本轮测试会真实运行虚构表格和文档自检，不注入自检答案。`restart_e2e.py` 在同一临时虚拟机内验证服务重启后复用有效检查且原件仍受保护。

`windows_native_probe.py` 与 `run_windows_probe.ps1` 只允许在一次性 GitHub 托管 Windows 测试机中运行，验证真实 ACL、文件句柄和命名管道身份；不模拟其成功，也不代表 VirtualBox、桌面窗口或 WorkBuddy 已验收。`.github/workflows/platform-validation.yml` 提供调度配置，必须以实际运行结果为准。
