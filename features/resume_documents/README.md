# 简历收集与识别

本目录保存“简历收集与识别”功能的后端字段定义。`dify_mapping.py` 独立负责把 Dify 的嵌套简历 JSON 转换为人才库及教育、工作、项目经历数据；对应的前端专用交互位于 `web/features/resume_documents.js`。

Dify HTTP 上传与工作流调用封装在项目根目录的 `dify_client.py`。当前工作流地址、输入变量和本机密钥配置方法见 `DIFY接入说明.md`。

如需停用该功能，请将 `resume_documents` 加入 `features/config.json` 的 `disabled` 数组；数据表及已有数据不会被删除。

启用统一 NocoBase 后端后，`Resume_Collection` 及其 `Resume` 附件关系是简历收集的唯一业务数据源。创建、修改和附件替换由服务端聚合服务完成：系统先校验完整提交内容和文件指纹，再写主记录和附件；后续步骤失败时会补偿本次请求创建的远端对象，避免留下半条简历。

`source_id`、`file_hash`、`recognition_result` 和 `linked_candidate` 是服务端维护的隐藏技术字段，浏览器提交同名字段不会覆盖它们。公开投递只接受业务白名单字段，创建人固定为“公开投递”。NocoBase 地址、API 密钥和角色配置仅保存在服务端配置或环境变量中，不得写入页面、日志或版本库。
