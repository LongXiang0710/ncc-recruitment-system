# Task 2: 可修改网址和 Windows DPAPI 凭据配置

## Global constraints

- 第一阶段只同步 `resume_documents` 和 `candidates`，方向仅为招聘系统到 NocoBase。
- 配置文件位于 `RECRUIT_DATA_DIR` 指定目录，未指定时使用项目 `data` 目录。
- 密码不得以明文写入文件、日志、异常或测试输出；真实用户名和密码不得进入测试。
- 当前工作目录没有 `.git`；不要初始化 Git，不要提交。
- 严格 TDD：测试先写并确认 RED，再写最小实现并确认 GREEN。
- Task 4 才创建 `browser.py`；因此 `configure.py` 只能在用户明确选择“测试连接”时惰性导入 `browser.test_login`，导入失败要给出可理解提示，不能破坏保存/读取配置。

## Files

- Create: `features/nocobase_sync/config.py`
- Create: `features/nocobase_sync/configure.py`
- Create: `配置NocoBase.bat`
- Create: `tests/test_nocobase_config.py`

## Interfaces

- Produces immutable `NocoBaseConfig(url, username, password)`.
- Produces `normalize_url(value)`, `save(data_dir, url, username, password, protect=None)`, `load(data_dir, unprotect=None)`, `configured(data_dir)`.
- Config filename: `nocobase-config.json`.
- Default protection uses Windows `CryptProtectData`; default unprotection uses `CryptUnprotectData`; ciphertext is Base64 in JSON.

## Required behavior

1. `normalize_url` trims whitespace/trailing slash and accepts only valid `http` or `https` URLs with a network location. `http://cloud.njncc.com:443/` normalizes to `http://cloud.njncc.com:443` without silently changing scheme or port.
2. `save` validates nonblank username/password, creates the data directory if necessary, protects the UTF-8 password, and atomically replaces the JSON file. JSON contains only version, normalized URL, username and Base64 ciphertext (plus non-secret metadata only if justified).
3. `load` validates schema/version/Base64, decrypts password, and returns `NocoBaseConfig`. Any decryption failure must raise a clear Chinese error instructing the user to reconfigure under the current Windows account. It must never treat ciphertext or stored text as a plaintext fallback.
4. `configured` returns true only when `load` succeeds and all three values are nonblank; missing/corrupt/wrong-account config returns false without exposing secrets.
5. DPAPI implementation must correctly allocate/free Windows `DATA_BLOB` memory using `LocalFree`. On non-Windows or unavailable DPAPI, raise an explicit platform/configuration error.
6. Test dependency injection via `protect`/`unprotect` must not bypass production validation. Protector input/output types must be explicit and tested.
7. Interactive `configure.py` reads URL and username using `input()`, password with `getpass.getpass()`, saves first, then offers an explicit read-only connection test. The test path lazily imports `features.nocobase_sync.browser.test_login`; because Task 4 is later, missing browser module produces a friendly “配置已保存，连接测试将在浏览器模块完成后可用” message rather than failure or deletion.
8. `配置NocoBase.bat` contains only:

```bat
@echo off
cd /d "%~dp0"
python -m features.nocobase_sync.configure
pause
```

## Mandatory RED tests

Include at minimum:

- `test_save_uses_protector_and_never_writes_plain_password`
- URL normalization and invalid scheme/blank/netloc cases
- blank username/password rejection before writing
- atomic replacement leaves no temporary file on success
- missing/corrupt JSON and invalid Base64
- decrypt failure message instructs current Windows account reconfiguration and does not echo secret/ciphertext
- `configured` true/false cases
- injected protector type validation
- CLI uses `getpass`, saves configuration, and lazily handles unavailable browser module
- batch file exact content

Reference core test:

```python
def test_save_uses_protector_and_never_writes_plain_password(self):
    with TemporaryDirectory() as directory:
        config.save(Path(directory), 'http://cloud.njncc.com:443/', 'sync-user', 'secret-value',
                    protect=lambda value: b'ciphertext')
        raw = (Path(directory) / 'nocobase-config.json').read_text(encoding='utf-8')
        self.assertNotIn('secret-value', raw)
        loaded = config.load(Path(directory), unprotect=lambda value: b'secret-value')
        self.assertEqual((loaded.url, loaded.username, loaded.password),
                         ('http://cloud.njncc.com:443', 'sync-user', 'secret-value'))
```

## Verification

- RED: `python -m unittest tests.test_nocobase_config -v` before production implementation.
- GREEN: same command must pass.
- Regression: `python -m unittest discover -s tests -v`.
- Compile: `python -m py_compile features/nocobase_sync/config.py features/nocobase_sync/configure.py tests/test_nocobase_config.py`.

## Report

Write `.superpowers/sdd/2026-09-16-nocobase-playwright-sync/task-2-report.md` with RED/GREEN evidence, implementation summary, exact file list, security self-review, regression output and concerns. Do not connect to the real NocoBase, do not create a real config containing credentials, and do not spawn subagents.
