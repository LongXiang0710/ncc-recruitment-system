# 人才库

本目录保存“人才库”功能的后端字段定义。校园招聘与社会招聘通用的工作经历子表、校验和保存规则位于 `experiences.py`；对应的前端专用交互位于 `web/features/candidates.js`，独立工作经历编辑组件及样式位于 `web/features/candidate_experiences.js` 和 `web/features/candidate_experiences.css`。

社会招聘专属的项目经历子表、校验和切换删除规则位于 `project_experiences.py`；独立项目经历编辑组件及样式位于 `web/features/candidate_project_experiences.js` 和 `web/features/candidate_project_experiences.css`。

如需停用该功能，请将 `candidates` 加入 `features/config.json` 的 `disabled` 数组；数据表及已有数据不会被删除。
