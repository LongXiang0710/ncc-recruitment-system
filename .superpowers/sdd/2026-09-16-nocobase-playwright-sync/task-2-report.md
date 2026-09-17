# Task 2 报告：可修改网址和 Windows DPAPI 凭据配置

## 状态

实现完成。未连接真实 NocoBase，未创建包含真实凭据的配置文件。

## 审查修复

引用根目录 `task-2-review.md` 的结论：此前为 **CHANGES_REQUESTED**。本次按其四项发现完成 RED→GREEN 修复：

- 拒绝 URL userinfo，避免内嵌 URL 密码绕过 DPAPI 并被写入 JSON。
- URL 改为仅移除 path 尾随斜杠；拒绝空白/控制字符主机、空主机、非法或范围外端口，同时保留 query 和 fragment 值。
- 保护函数返回空 bytes 时在任何写入前失败，既不创建也不替换配置。
- `CryptUnprotectData` 第二参数改为 `POINTER(c_wchar_p)`；假 DLL 成功路径验证输出数据由 `LocalFree` 恰好释放一次。

## TDD 证据

- RED 1：`python -m unittest tests.test_nocobase_config -v` 在 `config.py` 仅可导入时失败，缺少 `save`、`load`、`normalize_url`、`NocoBaseConfig` 和 `configured` API。
- GREEN 1：实现配置模块后，同一命令 10 项通过。
- RED 2：新增交互入口和批处理启动器测试后，同一命令出现 1 个失败（启动器缺失）和 1 个错误（`configure` 模块缺失）。
- GREEN 2：新增 `configure.py` 和指定批处理文件后，同一命令 12 项通过。
- RED 3：针对布尔版本号与空密文新增 schema 测试，`load` 错误地接受该值，测试失败。
- GREEN 3：严格校验 `version` 的实际整数类型且拒绝空密文后，测试通过。
- RED 4：模拟 `CryptProtectData` 失败时，测试得到通用 `OSError`，而不是清晰的平台/配置错误。
- GREEN 4：DPAPI 调用失败改为显式 `_DPAPIUnavailable` 后，配置测试共 13 项通过。
- RED 5（审查修复）：新增 URL userinfo、主机/端口和 query/fragment、空保护结果、解密 API 原型测试后，配置测试出现 4 个预期失败。
- GREEN 5（审查修复）：最小实现修复后，配置测试共 17 项通过。

## 实现摘要

- `NocoBaseConfig` 是冻结的数据类；URL 仅接受带网络位置的 HTTP/HTTPS 地址，并保留用户所选 scheme 和端口。
- `save` 在验证输入后使用 DPAPI（或 bytes-only 测试注入器）保护 UTF-8 密码，以 Base64 密文写入 JSON，并通过临时文件和 `os.replace` 原子替换。
- `load` 严格验证字段、版本和 Base64；不会把存储文本或密文当作密码回退。错误账户/解密错误会要求在当前 Windows 帐户下重新配置。
- Windows ctypes 调用使用 `DATA_BLOB`；输出缓冲区在 `finally` 中以 `LocalFree` 释放。
- `configure.py` 先保存，再只在用户明确选择时惰性导入浏览器登录测试；浏览器模块尚未完成时保留配置并给出友好提示。

## 修改文件

1. `features/nocobase_sync/config.py`
2. `features/nocobase_sync/configure.py`
3. `tests/test_nocobase_config.py`
4. `配置NocoBase.bat`
5. `.superpowers/sdd/2026-09-16-nocobase-playwright-sync/task-2-report.md`（任务书要求的交付报告）

## 安全自检

- JSON 仅存版本、规范化 URL、用户名和 Base64 密文；密码不会明文写入 JSON。
- 测试使用虚构值和注入式保护/解密函数，测试输出不包含密码或密文。
- `configured` 吞掉读取/解密错误，只返回布尔值，不暴露秘密。
- 没有访问 NocoBase、没有写入真实用户名/密码、没有初始化或使用 Git。

## 验证

- `python -m unittest tests.test_nocobase_config -v`：17 项通过。
- `python -m unittest discover -s tests -v`：174 项通过，`OK`。
- `python -m py_compile features/nocobase_sync/config.py features/nocobase_sync/configure.py tests/test_nocobase_config.py`：退出码 0。

## 关注项

受管 Codex 运行上下文对实际 `CryptProtectData` 返回 Windows 错误 2，表明该进程的用户配置文件/DAPI 上下文不可用；未向任何服务器发送数据。该情况现在会产生明确的 Windows DPAPI 配置错误。真实桌面用户应在其正常 Windows 登录会话运行 `配置NocoBase.bat`；仍建议在该会话完成一次端到端 DPAPI 保存/读取的验收。
