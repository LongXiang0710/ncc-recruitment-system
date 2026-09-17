const assert = require('assert');

global.window = {RecruitmentFeatures: {}};
const candidates = require('../web/features/candidates.js');

assert.strictEqual(typeof candidates.prepareCandidateEditor, 'function');
const fields = [
  {key: 'name'},
  {key: 'graduation', readonly: true},
  {key: 'cohort', readonly: true, virtual: true},
  {key: 'phone'},
];
const row = {name: '测试人才', graduation: '2026-07', cohort: '2026届'};
const prepared = candidates.prepareCandidateEditor({formFields: fields, formRow: row});

assert.deepStrictEqual(prepared.formFields.map(field => field.key), ['name', 'phone']);
assert.strictEqual(prepared.formRow, row, '隐藏展示字段时不应改写原记录');

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
