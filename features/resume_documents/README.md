# 简历收集与识别

本目录保存“简历收集与识别”功能的后端字段定义。`dify_mapping.py` 独立负责把 Dify 的嵌套简历 JSON 转换为人才库及教育、工作、项目经历数据；对应的前端专用交互位于 `web/features/resume_documents.js`。

Dify HTTP 上传与工作流调用封装在项目根目录的 `dify_client.py`。当前工作流地址、输入变量和本机密钥配置方法见 `DIFY接入说明.md`。

如需停用该功能，请将 `resume_documents` 加入 `features/config.json` 的 `disabled` 数组；数据表及已有数据不会被删除。
