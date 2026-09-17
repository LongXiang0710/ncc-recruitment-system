# 简历收集与批量识别

管理端左侧“简历收集”可新增 PDF 简历，每份最大50MB。文件保存在 SQLite 附件表中，包含在 data 文件夹备份内。点击文件名可预览。

## 工作流嵌入

系统默认嵌入 `http://biaozhun.njncc.com/workflow/e3JaA7Tg8GrWKJi5`。如需替换，在启动服务前设置环境变量 `DIFY_EMBED_URL` 为新的工作流网页链接，再运行 `start.bat`。链接必须是 HTTP 或 HTTPS。工作流本身须允许嵌入；服务器只向登录用户展示入口。

网页嵌入仅作为手动备用入口。单条和批量自动识别使用工作流 API；不要把 API Key 写入前端代码或嵌入 URL。

## 核对入库

点击简历行的“识别结果入库”，粘贴 JSON 对象，再核对表单并保存。支持人才库字段英文 key 或中文标签，如：

```json
{"name":"姓名","phone":"13900000000","school_name":"毕业院校","education":"本科","major":"土木工程","birthdate":"2003-01-02","graduation":"2026-07","email":"example@example.com","position":"工程师"}
```

系统不会把识别文本当作指令执行。人才库必填项及重复手机号由服务端校验。确认保存时，原 PDF 自动作为人才简历附件；删除文件库记录不会删除仍被人才档案引用的 PDF。

批量识别的服务端接口已接入当前发布工作流，并包含 Dify 嵌套结果到人才库字段的转换层。

## source_id 与处理状态

source_id 与档案编号一致，例如 20260701182308、20260701182308-1，不允许前端修改。文件内容的 SHA-256 单独保存在隐藏字段 file_hash 中，防止同一份文件重复上传。已有 source_id 和入库去重记录自动迁移，保留历史去重凭据。历史记录自动补齐标识；能通过相同附件对应到人才档案的历史记录标记为已入库。

所有接口需登录认证；当前没有免登录 Dify API Token，工作流接入时仍需配置认证方式。

- GET /api/resume_documents/pending：仅返回待识别记录，包含 id、source_id、resume 附件标识。
- GET /api/attachments/{resume}：下载对应 PDF。
- PUT /api/resume_documents/{id}，JSON {"status":"已识别"}：识别成功后的状态；也可设置失败或待识别重试。
- POST /api/resume_documents/{id}/candidate：提交人才字段。服务端使用该记录的 source_id 去重，成功在同一事务内保存人才、附件引用、去重记录和已入库状态。

重复入库返回 HTTP 200、原人才 id 和 already_imported=true；首次成功返回201。入库校验失败会回滚新增数据并保留原处理状态，方便继续核对；只有 Dify 识别或结果转换失败才标为失败。已入库不能手工改回待识别，也不能替换PDF。人才仍存在时，同一简历不会重复创建人才；原人才删除后，关联简历自动恢复为待识别、保留附件并释放旧去重标记，可以重新识别录入。系统启动时也会修复历史遗留的孤立去重标记。

pending 是筛选接口，不是任务占用锁；多个工作流同时读取时可能重复识别，但入库事务保证同一 source_id 不会重复创建人才。管理端识别操作通过进程内互斥锁限制为一次执行一份。


## 批量识别配置

首次使用时双击 `配置Dify.bat`，在隐藏输入框中填写工作流 API Key，然后关闭旧服务并重新运行 `start.bat`。API Key 只保存在当前 Windows 用户环境变量中，不会写入网页或项目文件。

当前工作流默认配置如下，无需重复设置：

- API 地址：`http://biaozhun.njncc.com/v1`
- 简历文件变量：`resume_file`（单文件）
- 招聘类型变量：`recruitment_type`
- 招聘渠道变量：`source_channel`
- 岗位变量：`position_name`

当前 Dify 服务未开放 HTTPS，已按部署决定暂时使用 HTTP。HTTP 会明文传输 API Key 和包含个人信息的简历，只应在受控网络中使用；建议限制 Dify 服务来源 IP、使用最小权限密钥并定期轮换。服务端支持 HTTPS 后应立即将 `DIFY_API_URL` 改为 `https://.../v1`。

系统会自动从结束节点的多个输出中寻找包含 `candidate` 的 JSON，并将 `basic`、`education`、`work_experience`、`projects` 分别转换为人才基础信息、教育经历、工作经历和社会招聘项目经历。教育经历的入学时间仅识别到年份时自动补为当年9月，毕业时间仅识别到年份时自动补为当年7月；已有月份保持不变，无有效年份时仍留空。识别出的教育经历按毕业时间倒序（缺少时使用入学时间），工作经历和项目经历按开始时间倒序（缺少时使用结束时间）；完全没有有效时间的记录排在最后并保持简历原顺序，时间相同的记录也保持简历原顺序。

如需切换到其他 Dify 工作流，可通过环境变量覆盖：

- DIFY_API_URL：Dify 的 API 基础地址（包含 /v1，不是网页嵌入链接）。
- DIFY_API_KEY：工作流 API Key，仅存于服务端，勿发到聊天或写入前端。
- DIFY_FILE_VARIABLE：工作流开始节点的文件变量名。
- DIFY_FILE_LIST：文件变量为文件列表时设为 1；单文件可不设置。
- DIFY_OUTPUT_VARIABLE：结束节点包含人才字段 JSON 的输出变量名；若 outputs 本身就是人才字段对象，可不设置。
- DIFY_SOURCE_VARIABLE：可选，工作流用于接收档案编号的文本输入变量名。

接口按 Dify 官方工作流 API 上传文件后执行工作流：
https://github.com/langgenius/dify/blob/main/web/app/components/develop/template/template_workflow.zh.mdx

待识别或失败记录的操作栏均可点击“识别”。点击后，系统自动上传该记录的 PDF、运行 Dify，成功后直接打开识别结果核对入库页面；再次失败时继续保持失败状态，仍可直接重试。也可勾选单条或多条后点击“识别（数量）”批量处理。识别期间请保持页面打开。未配置时不会发送附件或修改状态；已识别及已入库记录不能再发起识别。当前一次仅允许一个识别请求运行，其他成员遇到占用提示可稍后重试。
