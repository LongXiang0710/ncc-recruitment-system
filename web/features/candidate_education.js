(function(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.RecruitmentCandidateEducation = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);

  function renderRow(row, index, totalRows, requiredKeys = new Set()) {
    const mark = key => requiredKeys.has(key) ? '<span class="required"> *</span>' : '';
    const required = key => requiredKeys.has(key) ? 'required' : '';
    const degrees = ['专科', '本科', '硕士', '博士'];
    return `<fieldset data-education-row>
      <legend>教育经历 ${index + 1}</legend>
      <div class="education-primary-fields">
        <label>学历${mark('education')}<select data-education="education" ${required('education')}><option value="">请选择学历</option>${degrees.map(value => `<option value="${value}" ${row.education === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label>
        <label>毕业院校${mark('school_name')}<input data-education="school_name" ${required('school_name')} maxlength="300" value="${escapeHTML(row.school_name || '')}"></label>
        <label>专业${mark('major')}<input data-education="major" ${required('major')} maxlength="300" value="${escapeHTML(row.major || '')}"></label>
      </div>
      <div class="education-period-fields">
        <label>入学时间<input type="month" data-education="enrollment" value="${escapeHTML(row.enrollment || '')}"></label>
        <label>毕业时间<input type="month" data-education="graduation" value="${escapeHTML(row.graduation || '')}"></label>
      </div>
      <button type="button" class="danger education-remove" data-remove-education ${totalRows === 1 ? 'disabled' : ''}>删除此条</button>
    </fieldset>`;
  }

  return {renderRow};
});
