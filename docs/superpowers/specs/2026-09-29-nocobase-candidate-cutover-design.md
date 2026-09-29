# NocoBase 人才库切换设计

日期：2026-09-29  
状态：待用户书面复核

## 1. 目标与使用场景

在不改动前端现有操作习惯的前提下，让招聘系统的人才库通过 NocoBase HTTP API 读取和写入主表、教育经历、工作经历、项目经历及简历附件。设计电脑仅用于开发和自动化测试，默认继续使用 SQLite，并且不得向正式 NocoBase 写入数据。固定 IP 电脑完成部署和配置后，才允许显式切换到 NocoBase。

本阶段不迁移固定 IP 电脑中已有的 SQLite 数据。历史数据迁移需作为独立任务，在字段、数量、附件和回滚方案都核对完成后实施。

## 2. 方案选择

采用“单一后端、显式切换”方案：

- `sqlite` 模式维持当前行为，作为设计电脑默认值。
- `nocobase` 模式下，人才库以 NocoBase 为唯一权威数据源。
- 禁止同时向 SQLite 和 NocoBase 双写，避免部分成功后形成两套冲突数据。
- NocoBase 请求失败时返回明确错误，不静默写回 SQLite。

不采用双写同步，也不采用先写 SQLite 再异步推送。这两种方案虽然上线快，但无法保证主表、三类经历和附件在失败重试时保持一致。

## 3. 配置与启用边界

新增独立的数据源选择配置，取值只能是 `sqlite` 或 `nocobase`，默认 `sqlite`。NocoBase URL 和 API Key 继续保存到可移动 `data` 目录，API Key 使用当前 Windows 帐户的 DPAPI 加密。

只有同时满足下列条件时才能启用 `nocobase`：

1. 数据源选择明确为 `nocobase`；
2. URL、API Key 和启用开关有效；
3. 只读预检通过；
4. API 文档中存在人才主表及四个关联字段；
5. 当前字段映射与远端 Schema 一致。

设计电脑不配置正式 API Key，测试统一使用本地假 HTTP 服务。固定 IP 电脑通过配置脚本写入自身 DPAPI 密文；配置文件不能从设计电脑直接复制。

## 4. 服务端结构

前端仍调用现有 `/api/candidates`，不接触 NocoBase 地址或密钥。服务端增加以下边界：

- `candidate_backend.py`：根据运行配置选择 SQLite 或 NocoBase 实现，并在进程启动时固定选择，运行中不自动切换。
- `remote_candidate_service.py`：实现人才列表、详情、新增、编辑、删除的组合业务操作，保持现有 HTTP 响应格式。
- `relation_repository.py`：统一封装 `Education_Background`、`Work_experience` 和 `Project_Experience` 的读取、创建、替换和删除。
- `attachment_repository.py`：以 multipart 方式调用 `attachments:create?attachmentField=campus_talent_pool.biographical_notes` 上传文件，再通过 `biographical_notes:set` 关联附件 ID。
- `preflight.py`：只读检查连接、权限、集合、关联端点和 Schema，不创建记录。

现有字段校验、年月格式、手机号唯一性提示和校园/社会招聘业务规则继续在本服务端执行，避免前后端行为因数据源变化而改变。

## 5. 字段和关联映射

人才主表沿用已经验证的显式白名单映射。三类经历使用 NocoBase 已公开的关联端点：

- `campus_talent_pool/{id}/Education_Background:*`
- `campus_talent_pool/{id}/Work_experience:*`
- `campus_talent_pool/{id}/Project_Experience:*`
- `campus_talent_pool/{id}/biographical_notes:*`

本地字段保持不变：

- 教育经历：`education`、`school_name`、`major`、`enrollment`、`graduation`
- 工作经历：`organization`、`position`、`start_date`、`end_date`、`description`
- 项目经历：`project_name`、`role`、`start_date`、`end_date`、`description`

远端字段键不通过猜测生成。预检从当前 NocoBase Swagger Schema 读取属性与中文标题，转换为一份确定的字段映射；缺少字段、标题重复或类型不符时拒绝启用。运行期只使用预检确认后的白名单，不透传未知字段。

校园招聘保存教育经历，不保存项目经历；社会招聘可保存三类经历。由社会招聘改为校园招聘时，远端项目经历必须清空，保持与当前系统行为一致。

## 6. 读写流程与一致性

### 查询

列表请求从 NocoBase 同时读取 `data` 和 `meta`，转换为现有页面需要的记录、总数和分页信息。详情请求并行读取主表和四个关联，组合成现有候选人 JSON；任一必需关联读取失败时整个请求失败，不返回不完整详情。

### 新增

先完成全部本地校验，再创建主表；随后创建三类经历，最后上传并关联附件。若后续步骤失败，服务端删除本次新建的主表及已创建关联，返回失败且不把临时 ID 交给前端。补偿失败时记录不含密钥和人才内容的诊断编号，并阻止自动重试造成重复记录。

### 编辑

编辑前读取主表及关联快照。主表更新后，以“读取现有 ID、更新可复用记录、创建新增记录、删除移除记录”的方式同步经历，避免无条件删除重建。附件只有在用户新增或移除时才变化。任一步失败时尝试按快照恢复；恢复不完整则返回明确的“需要管理员核对”错误，禁止回退到 SQLite。

### 删除

删除前读取主表及关联摘要供现有删除预览使用。只有用户通过现有确认流程后才调用 NocoBase 删除接口。附件记录是否物理删除遵循 NocoBase 文件关联规则：先解除人才关联；只有确认附件没有其他引用时才删除文件记录和二进制。

## 7. 附件处理

文件上传使用 NocoBase 官方文件管理 HTTP API：向 `attachments:create` 发送 multipart `file`，并指定 `attachmentField=campus_talent_pool.biographical_notes`。上传成功返回的附件 ID 再关联到人才记录。

下载和预览继续通过本系统 `/api/attachments/{id}` 路由，由服务端鉴权后代理 NocoBase 文件内容或受控 URL，前端不直接获得 API Key。文件名、MIME、大小和扩展名须验证；沿用当前 50MB 单文件上限和允许的简历文件类型。

## 8. 错误处理和安全

- 401、403、参数错误、网络错误和远端 5xx 分别转换为稳定的中文错误。
- 日志只记录诊断编号、动作名、HTTP 状态和耗时，不记录 Authorization、API Key、请求正文、简历内容或个人联系方式。
- 所有 NocoBase 请求由服务端发出；浏览器永远看不到密钥。
- 写操作不进行无限自动重试。只有能够证明请求尚未被远端处理的连接前失败可以重试一次；结果未知时必须查询确认，避免重复创建。
- NocoBase 不可用时人才库显示服务不可用，不切换到另一数据源。

## 9. 部署和切换流程

1. 在设计电脑完成代码与假服务自动化测试，保持 `sqlite`。
2. 将代码部署到固定 IP 电脑，但仍保持 `sqlite`。
3. 在固定 IP 电脑运行配置脚本，填写 NocoBase URL 和 API Key。
4. 运行只读预检，输出连接、权限、集合、字段和关联检查结果。
5. 备份固定 IP 电脑的 `data` 目录。
6. 将数据源设置为 `nocobase` 并重启服务。
7. 使用一条虚构测试人才完成新增、读取、编辑、附件预览和删除验收；删除动作仍需用户当场确认。
8. 验收通过后开始录入真实数据；旧 SQLite 文件保留为只读备份，不再参与人才库读写。

## 10. 测试与验收

自动化测试不得访问正式 NocoBase，必须覆盖：

- 后端选择默认 SQLite，且只有显式配置才启用 NocoBase；
- 只读预检成功、字段缺失、权限不足和 Schema 冲突；
- 主表与三类经历的完整读写映射；
- 校园/社会招聘切换时项目经历处理；
- multipart 附件上传、关联、预览和安全删除；
- 新增失败补偿、编辑失败恢复和未知结果去重；
- 分页、搜索、手机号重复、日期格式及错误脱敏；
- NocoBase 故障时不写回 SQLite。

固定 IP 电脑的人工验收只使用虚构数据，确认成功并删除测试记录后才允许录入真实人才。

## 11. 本阶段不包含

- 迁移固定 IP 电脑现有 SQLite 人才数据；
- 将简历收集之外的其他业务模块全部切换到 NocoBase；
- 修改 NocoBase 数据表结构或角色权限；
- 在设计电脑保存正式 API Key 或写入正式人才数据。
