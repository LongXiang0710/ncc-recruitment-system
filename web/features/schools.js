// 院校基础库专用省市联动。
window.RecruitmentFeatures=window.RecruitmentFeatures || {};
window.RecruitmentFeatures.schools={
  async prepareEditor({spec,formFields,formRow}) {
    locations=await api('locations');
    const oldProvince=String(formRow.province || '').trim();
    const province=Object.keys(locations).find(name=>name===oldProvince || name.replace(/(省|市|壮族自治区|回族自治区|维吾尔自治区|自治区|特别行政区)$/,'')===oldProvince) || '';
    const oldCity=String(formRow.city || '').trim();
    const city=(locations[province] || []).find(name=>name===oldCity || name===oldCity+'市') || '';
    formRow={...formRow,province,city};
    formFields=spec.fields.map(field=>field.key==='province'?{...field,options:Object.keys(locations)}:field.key==='city'?{...field,options:locations[province] || []}:field);
    return {formFields,formRow};
  },
  afterEditor({form,row,formRow}) {
    const provinceInput=form.querySelector('[name=province]'),cityInput=form.querySelector('[name=city]');
    const updateLocation=()=>{form.querySelector('[name=province_city]').value=['province','city'].map(key=>form.querySelector(`[name=${key}]`).value.trim()).filter(Boolean).join(' ');};
    const populateCities=()=>{const cities=locations[provinceInput.value] || [];cityInput.innerHTML='<option value="">'+(provinceInput.value?'请选择所在市':'请先选择所在省')+'</option>'+cities.map(city=>`<option value="${escapeHTML(city)}">${escapeHTML(city)}</option>`).join('');cityInput.disabled=!provinceInput.value;updateLocation();};
    provinceInput.addEventListener('change',populateCities);
    cityInput.addEventListener('change',updateLocation);
    cityInput.disabled=!provinceInput.value;
    if(row && ((row.province && !formRow.province) || (row.city && !formRow.city))) {
      const hint=document.createElement('p');hint.className='hint full';hint.textContent=`原省市信息：${row.province || ''} ${row.city || ''}。请按下拉选项重新选择后保存。`;form.querySelector('.form-grid').prepend(hint);
    }
    updateLocation();
  }
};
