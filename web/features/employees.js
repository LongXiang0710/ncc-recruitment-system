// 新员工登记专用公开页面。
async function employeeApplication() {
  try {
    const spec=await api('public/employee-schema');
    const educationRows=[{education:'',school_name:'',major:''}];
    const educationRequired=new Set(spec.fields.filter(field=>field.required && ['education','school_name','major'].includes(field.key)).map(field=>field.key));
    spec.fields=spec.fields.filter(field=>!['education','school_name','major'].includes(field.key));
    app.innerHTML=`<main class="apply"><a class="identity" href="/"><div class="logo">N</div><div>南化建<strong>新员工登记</strong></div></a><div class="apply-title"><h1>新员工信息登记</h1><p>请填写本人真实资料，提交后由招聘工作人员统一管理。</p></div><section class="panel"><form id="employee-apply-form"><div class="panel-head"><h3>新员工个人信息</h3><span class="hint">* 为必填</span></div><div class="form-grid">${await fieldsHTML(spec.fields)}</div><div class="consent"><label><input type="checkbox" required> 我确认所填信息真实，并同意将上述信息用于入职登记及相关联系。</label><p class="hint">同一身份证请勿重复提交。如需更正资料，请联系招聘工作人员。身高单位为厘米，体重单位为公斤。</p></div><p class="error form-error" role="alert"></p><div class="dialog-foot"><button class="primary" type="submit">提交登记</button></div></form></section></main>`;
    const form=document.querySelector('#employee-apply-form');
    form.querySelector('[for=f-gender]')?.after(candidateEducationEditor(educationRows,educationRequired));
    PositionFields.bind(form);
    bindIdentityCard(form);
    form.onsubmit=async event=>{
      event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
      try {
        await api('public/employees',{method:'POST',body:JSON.stringify(await formPayload(form))});
        document.querySelector('.apply .panel').innerHTML='<div class="success"><div>✓</div><h2>新员工登记已提交</h2><p>招聘工作人员已可在新员工信息登记表中查看你的资料。</p></div>';
      } catch(error) {form.querySelector('.form-error').textContent=error.message;button.disabled=false;}
    };
  } catch(error) {app.textContent=error.message;}
}

window.RecruitmentFeatures=window.RecruitmentFeatures || {};
window.RecruitmentFeatures.employees={
  afterEditor({form}) {
    bindIdentityCard(form);
    bindInterviewIdentity(form,'employee-prefill');
  }
};
