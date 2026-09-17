# Task 2 独立审查

## 结论

**CHANGES_REQUESTED**

配置测试、全量回归和编译均通过；Windows DPAPI 失败的错误 2 也已确认来自当前受管账户的 DPAPI/用户配置文件上下文，而不是 `CryptProtectData` 当前调用参数造成。但 URL 校验仍能把 URL 内嵌密码明文写入配置文件，并接受若干无效地址；另外测试注入器可以让 `save` 落盘一个自身无法读取的空密文配置。这些问题需要在 Task 2 合入前修复。

## Findings

### [HIGH] URL 用户信息可绕过密码加密并以明文落盘

- 位置：`features/nocobase_sync/config.py:35-43`，写入点 `features/nocobase_sync/config.py:130-145`
- 原因：`normalize_url` 只检查 scheme 和 `netloc`。`urlparse` 会把 `https://user:password@host/` 视为合法 `netloc`，随后 `save` 将整个 URL 原样写入明文 `url` 字段。这违反“密码不得以明文写入文件”的安全约束，也绕过了独立密码字段的 DPAPI 边界。
- 复现：

  ```python
  with TemporaryDirectory() as directory:
      data_dir = Path(directory)
      config.save(
          data_dir,
          "https://alice:visible-secret@example.test/",
          "alice",
          "fixture-password",
          protect=lambda _: b"cipher",
      )
      raw = (data_dir / "nocobase-config.json").read_text(encoding="utf-8")
      assert "visible-secret" in raw  # 当前成立
  ```

- 最小修复：在写文件前拒绝任何 URL userinfo（`parsed.username is not None` 或 `parsed.password is not None`），并增加回归测试，确认异常后配置文件不存在且输出不含该秘密。

### [MEDIUM] `normalize_url` 会接受无效主机/端口，并可能改写查询参数

- 位置：`features/nocobase_sync/config.py:35-43`；现有覆盖仅到 `tests/test_nocobase_config.py:65-75`
- 原因：非空 `parsed.netloc` 不等于有效网络地址；另外在解析前对整串执行 `rstrip("/")` 会删除 query/fragment 末尾本属于值的斜杠。
- 复现（当前全部被接受，或被静默改写）：

  ```python
  normalize_url("http://exa mple.test/")       # -> "http://exa mple.test"
  normalize_url("https://example.test:bad/")  # -> "https://example.test:bad"
  normalize_url("https://example.test:99999/")
  normalize_url("http://user@:80/")
  normalize_url("https://example.test/?next=/")  # -> query 被改成 next=
  ```

- 最小修复：解析后校验 `hostname` 非空、主机/整串不含空白或控制字符，并读取 `parsed.port` 触发非法/越界端口校验；明确拒绝 query/fragment（更适合作为 NocoBase 基址）或只规范化 path 的尾斜杠，再通过 `urlunsplit` 重组。为上述边界补测试。

### [MEDIUM] 空 bytes 保护结果会被保存为必然不可用的配置

- 位置：`features/nocobase_sync/config.py:107-110, 128-135`
- 原因：`_require_bytes` 只验证类型，不验证保护结果非空。于是测试注入器可绕过生产 DPAPI 必然产生非空密文的约束；`save` 成功写入 `"password":""`，而同模块的 `load` 在 `features/nocobase_sync/config.py:179-180` 必然拒绝它。调用方会看到“配置已保存”，但 `configured` 立即为 false。
- 复现：

  ```python
  with TemporaryDirectory() as directory:
      data_dir = Path(directory)
      config.save(data_dir, "https://example.test", "user", "password", protect=lambda _: b"")
      assert (data_dir / "nocobase-config.json").exists()
      assert not config.configured(data_dir, unprotect=lambda _: b"password")
  ```

- 最小修复：在构造 payload 前拒绝空保护结果（建议独立校验 `ciphertext`，不要让通用 `_require_bytes` 影响允许空值的其他潜在调用），并增加“空保护结果不创建/不替换配置”的测试。

### [LOW] `CryptUnprotectData` 的第二个 ctypes 参数类型声明不精确

- 位置：`features/nocobase_sync/config.py:73-83`
- 原因：同一套 `argtypes` 被同时用于 `CryptProtectData` 和 `CryptUnprotectData`。前者第二参数是 `LPCWSTR szDataDescr`，可声明为 `c_wchar_p`；后者第二参数实际是输出参数 `LPWSTR *ppszDataDescr`，应为 `POINTER(c_wchar_p)`。当前始终传 `None`，其 ABI 值仍是空指针，因此不会解释本次错误 2，也不会破坏当前路径；但声明与 Windows API 原型不一致，未来一旦读取描述字符串就会错误。
- 复现：调用 `_protect_password` 或 `_unprotect_password` 后检查赋给 DLL 函数的 `argtypes[1]`，两者当前都是 `ctypes.c_wchar_p`。
- 最小修复：为两个函数分别声明原型；`CryptUnprotectData.argtypes[1]` 使用 `ctypes.POINTER(ctypes.c_wchar_p)`，继续传 `None` 即可避免描述字符串分配。补一个成功路径假 DLL 测试，同时断言输出通过 `LocalFree` 恰好释放一次。

## 已验证且无阻塞问题的部分

- `DATA_BLOB` 的 DWORD 长度和指针布局在 64 位 Windows 上具有正确对齐；输入缓冲区生命周期覆盖整个调用。
- `CryptProtectData` 的七个参数与 BOOL 返回类型正确；`CryptUnprotectData` 除上述第二参数声明外，当前 NULL 调用路径可用。
- `LocalFree` 使用指针宽度的 `c_void_p` 参数和返回类型，并在 `finally` 中释放非空 DPAPI 输出。本地假 DLL 成功路径探针得到一次加密调用和一次释放调用。
- DPAPI 错误 2：实际 `CryptProtectData` 返回错误 2；同一进程独立调用 .NET `ProtectedData.Protect(..., CurrentUser)` 也失败，并明确提示当前线程用户上下文未加载可用用户配置文件/可能处于模拟身份。因此报告对受管 Codex 账户环境限制的判断成立，仍需在正常桌面登录账户做真实往返验收。
- 原子写：`os.replace` 失败探针确认旧配置保持不变，临时文件被清理；成功路径也只留下目标文件。
- JSON 使用严格字段集合和实际整数版本校验；Base64 使用 `validate=True` 并拒绝空密文；解密及错误消息不回显密码或密文。
- `configured` 仅在完整 `load` 成功且三个值均非空时返回 true，缺失、损坏及解密失败均只返回 false。
- CLI 仅在用户明确选择测试后惰性导入浏览器模块；缺失模块时保留已保存配置并输出约定提示。批处理内容与任务书四行逐字一致。

## 验证证据

- `python -m unittest tests.test_nocobase_config -v`：13 项通过，退出码 0。
- `python -m unittest discover -s tests -v`：170 项通过，退出码 0。实现报告记录的 169 是审查时其他任务测试增加前的旧计数，不是本次回归失败。
- `python -m py_compile features/nocobase_sync/config.py features/nocobase_sync/configure.py tests/test_nocobase_config.py`：退出码 0。
- 未连接真实 NocoBase，未使用真实用户名或密码，未创建真实配置文件。
