const assert = require('assert');

global.window = {RecruitmentFeatures: {}};
const candidates = require('../web/features/candidates.js');

assert.strictEqual(typeof candidates.prepareCandidateEditor, 'function');
const fields = [
  {key: 'travel_acceptance', section: '一筛情况', editorRequired: true},
  {key: 'screening_result', editorRequired: true},
  {key: 'follow_up_owner', editorRequired: true, readonly: true},
  {key: 'screening_reason', editorRequired: true, type: 'textarea', fullWidth: true},
  {key: 'recruitment_type', section: '基础信息'},
  {key: 'name'},
  {key: 'graduation', readonly: true},
  {key: 'cohort', readonly: true, virtual: true},
  {key: 'phone'},
];
const storedRow = {
  id: 7,
  name: '测试人才',
  graduation: '2026-07',
  cohort: '2026届',
  follow_up_owner: '高蕾',
};
const prepared = candidates.prepareCandidateEditor({
  formFields: fields,
  formRow: storedRow,
  row: storedRow,
  user: {username: 'chen', nickname: '陈苏宁'},
});

assert.deepStrictEqual(
  prepared.formFields.map(field => field.key),
  ['travel_acceptance', 'screening_result', 'follow_up_owner', 'screening_reason', 'recruitment_type', 'name', 'phone'],
);
assert.strictEqual(
  prepared.formFields[0].section,
  '一筛情况',
  '一筛情况应显示在人才库弹窗最上方',
);
assert.strictEqual(prepared.formFields[0].required, true, '一筛必填字段应限制人才库弹窗提交');
assert.strictEqual(prepared.formFields[4].section, '基础信息', '基础信息应紧随一筛情况');
assert.notStrictEqual(prepared.formRow, storedRow, '编辑已有记录时应使用独立草稿');
assert.strictEqual(prepared.formRow.follow_up_owner, '陈苏宁', '打开已有记录时跟进人应预填当前账号昵称');
assert.strictEqual(storedRow.follow_up_owner, '高蕾', '关闭或取消前不得改写原记录');
const preparedOwnerField = prepared.formFields.find(field => field.key === 'follow_up_owner');
assert.strictEqual(preparedOwnerField.readonly, true, '跟进人应显示为不可手动修改的文本框');
assert.strictEqual('options' in preparedOwnerField, false, '跟进人不应再显示下拉选项');

const usernameFallback = candidates.prepareCandidateEditor({
  formFields: fields,
  formRow: storedRow,
  row: storedRow,
  user: {username: 'member_without_nickname', nickname: ''},
});
assert.strictEqual(
  usernameFallback.formRow.follow_up_owner,
  'member_without_nickname',
  '账号未设置昵称时应使用登录账号作为跟进人',
);

const newDraft = {name: '新人才'};
const preparedNew = candidates.prepareCandidateEditor({
  formFields: fields,
  formRow: newDraft,
  row: null,
  user: {username: 'new_owner', nickname: '新跟进人'},
});
assert.strictEqual(preparedNew.formRow.follow_up_owner, '新跟进人', '新增人才时也应自动填写当前账号');
assert.strictEqual(newDraft.follow_up_owner, undefined, '自动填写跟进人不得改写传入的新建草稿');

const recognitionDraft = {name: '识别人才'};
const preparedRecognition = candidates.prepareCandidateEditor({
  formFields: fields,
  formRow: recognitionDraft,
  row: null,
  user: {username: 'recognizer', nickname: '识别操作人'},
  resumeSource: 23,
});
assert.ok(
  preparedRecognition.formFields.filter(field => field.editorRequired).every(field => field.required !== true),
  '简历识别入库时一筛情况不得启用必填校验',
);
assert.strictEqual(
  preparedRecognition.formRow.follow_up_owner,
  undefined,
  '简历识别入库时不得自动填写跟进人',
);
assert.strictEqual(recognitionDraft.follow_up_owner, undefined, '识别入库准备过程不得改写原始草稿');

assert.strictEqual(typeof candidates.placeExperienceEditorsBeforeResume, 'function');

assert.strictEqual(typeof candidates.bindCandidateDates, 'function');
global.today = () => '2026-09-15';
const listeners = {};
const field = (value = '') => ({
  value,
  addEventListener(event, handler) { listeners[event] = handler; },
});
const birth = field('2000-01-01');
const age = field('42');
const graduation = field('');
const type = field('社会招聘');
const cohort = field('');
const dateForm = {
  querySelector(selector) {
    return {
      '[name=birthdate]': birth,
      '[name=age]': age,
      '[name=graduation]': graduation,
      '[name=recruitment_type]': type,
      '[name=cohort]': cohort,
      '.education-editor': null,
    }[selector] || null;
  },
};
candidates.bindCandidateDates(dateForm);
assert.strictEqual(age.value, '42', 'opening the editor must preserve the manually stored age');
birth.value = '1995-06-10';
listeners.input();
assert.strictEqual(age.value, '42', 'changing birth date must not overwrite age');

const grid = {
  children: [],
  append(...nodes) {
    for (const node of nodes) {
      node.remove();
      this.children.push(node);
      node.parentNode = this;
    }
  },
};
const node = name => ({
  name,
  parentNode: null,
  remove() {
    if (!this.parentNode) return;
    const index = this.parentNode.children.indexOf(this);
    if (index >= 0) this.parentNode.children.splice(index, 1);
    this.parentNode = null;
  },
});
const basic = node('basic');
const resume = node('resume');
resume.before = (...nodes) => {
  for (const item of nodes) item.remove();
  const index = grid.children.indexOf(resume);
  grid.children.splice(index, 0, ...nodes);
  nodes.forEach(item => { item.parentNode = grid; });
};
const tail = node('tail');
const education = node('education');
const work = node('work');
const projects = node('projects');
grid.append(basic, resume, tail, education, work, projects);
const resumeInput = {closest: selector => selector === '.attachment-field' ? resume : null};
const form = {querySelector: selector => selector === '[data-attachment=resume]' ? resumeInput : null};

candidates.placeExperienceEditorsBeforeResume(form, [education, work, projects]);

assert.deepStrictEqual(
  grid.children.map(item => item.name),
  ['basic', 'education', 'work', 'projects', 'resume', 'tail'],
  '教育、工作、项目经历应连续排列在简历附件前',
);
