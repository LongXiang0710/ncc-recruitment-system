(function(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.PositionFields = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  const options = [
    '机械工程师', '电气工程师', '安全工程师', '土建工程师',
    '管道工程师', '设备工程师', '数据分析师', '软件工程师',
    '财务专员', '其它',
  ];

  function refresh(form) {
    const position = form?.elements?.position;
    const detail = form?.elements?.position_detail;
    if (!position || !detail) return;
    const show = position.value === '其它';
    detail.closest('label')?.classList.toggle('conditional-hidden', !show);
    detail.required = show;
    if (!show) detail.value = '';
  }

  function bind(form) {
    const position = form?.elements?.position;
    if (!position || !form?.elements?.position_detail) return;
    position.addEventListener('change', () => refresh(form));
    refresh(form);
  }

  function setRecognized(form, value) {
    const position = form?.elements?.position;
    const detail = form?.elements?.position_detail;
    if (!position || !detail) return;
    const text = String(value || '').trim();
    if (options.includes(text)) {
      position.value = text;
      detail.value = '';
    } else if (text) {
      position.value = '其它';
      detail.value = text;
    } else {
      position.value = '';
      detail.value = '';
    }
    refresh(form);
  }

  return {options, bind, refresh, setRecognized};
});
