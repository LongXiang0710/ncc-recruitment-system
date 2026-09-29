# NocoBase API 主数据库接入设计

日期：2026-09-29  
状态：用户已确认直接开始

## 1. 目标

招聘系统通过 NocoBase HTTP API 读写数据，逐步将 NocoBase 设为全系统的唯一权威业务数据源。不再使用 Playwright 做数据同步。

第一阶段建立可测试的 API 基础层，接入“招聘人才库”主表 `campus_talent_pool`。教育经历、工作经历、项目经历和简历附件在后续阶段接入，在这些关联完整前，不把现网人才库强制切换为 API 读写，以免丢字段。

## 2. 已确认的 NocoBase 接口

- 基础地址：`http://cloud.njncc.com:443/api/`
- 授权：`Authorization: Bearer <API Key>`
- 主表：`campus_talent_pool`
- 查询：`GET /campus_talent_pool:list` 和 `GET /campus_talent_pool:get`
- 新增：`POST /campus_talent_pool:create`
- 修改：`POST /campus_talent_pool:update`
- 删除：`POST /campus_talent_pool:destroy`
- `get`/`update`/`destroy` 用 `filterByTk` 传递主键，不得同时发送空的 `filter={}`。
- 主表 CRUD 已使用虚构数据人工验证，全部返回 HTTP 200，测试记录已删除。

## 3. 架构

在 `features/nocobase/` 中建立与 HTTP 服务器解耦的数据访问层：

- `config.py`：保存基础 URL、加密 API Key 和是否启用的开关。
- `client.py`：负责 Bearer 授权、JSON 编解码、超时、错误分类和响应校验。
- `candidate_mapping.py`：本地字段与 NocoBase 英文字段名的显式白名单映射。
- `candidate_repository.py`：封装人才主表列表、单条、新增、修改、删除操作。

HTTP 服务器继续向前端提供现有 `/api/candidates` 契约。后续通过仓库接口替换 SQLite 实现，前端不需要知道 NocoBase API Key。

## 4. 配置与安全

- API Key 只能在服务端使用，禁止返回前端、写入日志或提交 Git。
- Windows 上使用 DPAPI 加密 API Key，配置文件位于可移动 `data` 目录。
- 默认 URL 可配置，不写死在业务代码中。
- 旧的 Playwright 用户名/密码配置不得被当作 API Key 加载；需明确提示重新配置。
- 连接或认证失败时向管理员返回可理解的错误，不回退到本地写入，避免双主数据分叉。

## 5. 主表字段映射

第一阶段仅映射已由 API Schema 确认的字段：

| 本地字段 | NocoBase 字段 |
| --- | --- |
| `archive_no` | `Number` |
| `name` | `name` |
| `gender` | `gender` |
| `birthdate` | `birthday` |
| `age` | `age` |
| `phone` | `phone` |
| `email` | `email` |
| `political_status` | `political_status` |
| `hometown` | `area` |
| `recruitment_type` | `Type` |
| `channel` | `channel` / `Social_recruitment_channels` |
| `channel_detail` | `detailed` |
| `position` | `post` |
| `position_detail` | `Other_job_titles` |

NocoBase 的 `id`、`createdAt`、`updatedAt`、`createdById`、`updatedById` 由 NocoBase 管理，客户端不允许写入。尚未确认语义的 `date`、`time`、`year` 不猜测映射。

## 6. 错误与超时

- 连接超时 5 秒，整体请求超时 30 秒。
- 401：API Key 无效或过期。
- 403：角色权限不足。
- 400/422：字段或查询参数错误。
- 5xx/网络错误：NocoBase 暂时不可用。
- 错误对象和日志只包含状态码、端点和诊断编号，不包含 API Key 或人才字段。

## 7. 测试和切换

- 自动化测试使用本地假 HTTP 服务，禁止向真实 NocoBase 写数据。
- 每个新功能先写失败测试，再实现。
- 第一阶段只交付配置、客户端、映射和人才主表仓库，不默认改变现有线上读写。
- 关联表和附件完成后，再对人才库进行一次可回滚的整体切换。
- 切换前要有 SQLite 历史数据导入、数量校验和档案编号唯一性校验。

## 8. 验收标准

- 配置工具可保存 URL 和加密 API Key，输出不泄露密钥。
- 客户端会生成正确 Bearer 头，不发送空 `filter={}`。
- 仓库层能通过假服务验证列表、单条、新增、修改和删除。
- 字段映射为白名单，未知和系统字段不会被上传。
- 现有 174 项基线测试继续通过。
