const assert = require('assert');
const ui = require('../web/features/candidate_experiences.js');

assert.deepStrictEqual(ui.experienceConfig(), {
  key: 'work_experiences',
  title: '工作经历',
  organizationLabel: '工作单位',
  descriptionLabel: '工作描述'
});
assert.deepStrictEqual(ui.normalizedRows([{organization: ' 单位 ', position: ' 岗位 '}]), [{
  organization: ' 单位 ', position: ' 岗位 ', start_date: '', end_date: '', description: ''
}]);

const originalWork = [{organization: '原单位', position: '工程师', start_date: '2022-01', end_date: '', description: ''}];
const state = ui.createExperienceState({work_experiences: originalWork});
assert.deepStrictEqual(state.payload(), {work_experiences: originalWork});
