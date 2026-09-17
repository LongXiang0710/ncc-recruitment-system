const assert = require('assert');
const fs = require('fs');
const ui = require('../web/features/candidate_project_experiences.js');

assert.deepStrictEqual(ui.projectExperienceConfig(), {
  key: 'project_experiences',
  title: '项目经历',
  nameLabel: '项目名称',
  roleLabel: '担任角色',
  descriptionLabel: '项目描述'
});
const projects=[{project_name:'化工项目',role:'负责人',start_date:'2022-01',end_date:'',description:'全过程管理'}];
const state=ui.createProjectExperienceState('社会招聘',{project_experiences:projects});
assert.strictEqual(state.visible(),true);
assert.deepStrictEqual(state.payload(),{project_experiences:projects});
state.setType('校园招聘');
assert.strictEqual(state.visible(),false);
assert.deepStrictEqual(state.payload(),{project_experiences:[]});
state.setType('社会招聘');
assert.deepStrictEqual(state.payload(),{project_experiences:projects});

const emptyState=ui.createProjectExperienceState('社会招聘',{project_experiences:[]});
assert.deepStrictEqual(emptyState.payload(),{project_experiences:[]});
const source=fs.readFileSync(require.resolve('../web/features/candidate_project_experiences.js'),'utf8');
assert.ok(!/data-project="(?:project_name|role|start_date)"[^>]*\brequired\b/.test(source),'空项目列表不得被浏览器 required 校验阻断');
