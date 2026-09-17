// 面试管理专用页面与资料联动。
async function showStudentRegistration(identity) {
  if(!String(identity || '').trim()) {toast('请先填写身份证号');return;}
  try {
    const result=await api('student-registration?identity_card='+encodeURIComponent(identity));
    if(!result.matched) {toast('未找到该身份证号对应的应聘登记');return;}
    const detail=document.createElement('dialog');
    detail.innerHTML=`<div class="dialog-head"><div><div class="eyebrow">学生登记内容</div><h2>${escapeHTML(result.values.name)}</h2></div><button type="button" class="close" aria-label="关闭">×</button></div><div class="form-grid">${result.fields.map(field=>{
      const value=result.values[field.key];
      const content=field.type==='attachment' && value?`<a href="/api/attachments/${encodeURIComponent(value)}">${escapeHTML(result.values[field.key+'_name'] || '下载附件')}</a>`:escapeHTML((field.type==='datetime-local'?String(value ?? '').replace('T',' '):value) || '—');
      return `<div class="${field.type==='textarea' || field.type==='attachment'?'full':''}"><span class="muted">${escapeHTML(field.label)}</span><div style="white-space:pre-wrap;overflow-wrap:anywhere">${content}</div></div>`;
    }).join('')}</div><div class="dialog-foot"><span class="hint">按身份证号匹配；多份登记显示最近一份。</span><button type="button" class="secondary">关闭</button></div>`;
    tableLayout.floatDialogClose(detail);
    detail.querySelectorAll('button').forEach(button=>button.onclick=()=>detail.close());
    detail.addEventListener('close',()=>detail.remove(),{once:true});
    document.body.append(detail);detail.showModal();
  } catch(error) {toast(error.message);}
}
function bindInterviewConsent(form) {
  const consent=form.querySelector('[name=first_interview_consent]');
  const passed=form.querySelector('[name=first_interview_passed]'),result=form.querySelector('[name=result]');
  const keys=['interview_at','personality','campus_position','has_internship','family','project_locations','other_project_locations','first_interview_passed','first_interview_notes','second_interview_notes','result','personal_intention'];
  const fields=keys.map(key=>form.querySelector(`[name=${key}]`)).filter(Boolean);
  const required=new Map(fields.map(input=>[input,input.required]));
  const update=()=>{
    const hide=['拒绝','不合适'].includes(consent.value);
    fields.forEach(input=>{
      const fieldHidden=hide || (input.name==='second_interview_notes' && passed.value==='否');
      const label=input.closest('label');label.classList.toggle('conditional-hidden',fieldHidden);
      input.required=!fieldHidden && required.get(input);
      if(input.name!=='interview_at' && label.previousElementSibling?.classList.contains('form-section'))label.previousElementSibling.classList.toggle('conditional-hidden',hide);
    });
  };
  passed.addEventListener('change',()=>{
    if(passed.value==='否')result.value='pass';
    update();
  });
  if(passed.value==='否' && !result.value)result.value='pass';
  consent.addEventListener('change',update);update();
}
function bindInterviewIdentity(form, endpoint='interview-prefill') {
  const identity=form.querySelector('[name=identity_card]');
  if(endpoint==='interview-prefill')identity.addEventListener('input',()=>fillLinkedAttachments(form,{},['resume','transcript','certificates']));
  const hint=document.createElement('p');hint.className='hint full';hint.setAttribute('role','status');hint.textContent='填写身份证号后自动匹配应聘登记；相同号码有多份登记时取最近一份，未匹配时可手动填写。';form.querySelector('.form-grid').prepend(hint);
  let timer,version=0,lastMatched='',filled={};
  const lookup=async()=>{
    const number=identity.value.trim().toUpperCase();if(!number || !identity.checkValidity() || number===lastMatched)return;
    const request=++version;hint.textContent='正在匹配应聘登记…';
    try {const result=await api(endpoint+'?identity_card='+encodeURIComponent(number));if(request!==version || identity.value.trim().toUpperCase()!==number || !form.isConnected)return;
      if(endpoint==='interview-prefill')fillLinkedAttachments(form,result.attachment_fields || {},['resume','transcript','certificates']);
      if(!result.matched){hint.textContent='未找到相同身份证的应聘登记，可手动填写资料。';return;}
      filled={};for(const [key,value] of Object.entries(result.values)){if(key==='identity_card')continue;if(key==='education_experiences'){form.querySelector('.education-editor')?.setRows(value);continue;}const input=form.querySelector(`[name=${key}]`);if(input){input.value=value || '';if(!['birthdate','gender'].includes(key))filled[key]=input.value;}}
      PositionFields.refresh(form);
      form.querySelector('[name=name]').dispatchEvent(new Event('input'));
      lastMatched=number;form.querySelector('[name=birthdate]').dispatchEvent(new Event('input'));
      hint.textContent='已带入最近一份应聘登记资料，可继续补充修改。'+(result.attachments.length?'新建或变更身份证后保存时带入附件：'+result.attachments.join('、'):'');
    }catch(error){if(request===version && form.isConnected)hint.textContent=error.message;}
  };
  identity.addEventListener('input',()=>{clearTimeout(timer);version++;if(identity.value.trim().toUpperCase()===lastMatched)return;lastMatched='';for(const [key,value] of Object.entries(filled)){const input=form.querySelector(`[name=${key}]`);if(input?.value===value)input.value='';}filled={};form.querySelector('.education-editor')?.setRows([]);hint.textContent='填写完整且校验通过的身份证后匹配应聘登记。';if(identity.value.length===18 && identity.validity.valid)timer=setTimeout(lookup,450);});
  identity.addEventListener('change',()=>{clearTimeout(timer);lookup();});
  dialog.addEventListener('close',()=>{clearTimeout(timer);version++;},{once:true});
}

window.RecruitmentFeatures=window.RecruitmentFeatures || {};
window.RecruitmentFeatures.interviews={
  prepareEditor({spec,formFields,formRow}) {
    formFields=[{...spec.fields.find(field=>field.key==='name'),section:'基本信息',fullWidth:true},{...spec.fields.find(field=>field.key==='identity_card'),section:undefined,fullWidth:true},...spec.fields.filter(field=>!['name','identity_card'].includes(field.key))];
    return {formFields,formRow};
  },
  afterEditor({form}) {
    const input=form.querySelector('[name=basic_situation]');
    const button=document.createElement('button');button.type='button';button.className='text-button';
    const name=form.querySelector('[name=name]');
    const update=()=>button.textContent=name.value || '查看学生登记';update();
    name.addEventListener('input',update);
    button.onclick=()=>showStudentRegistration(form.querySelector('[name=identity_card]').value);
    input.hidden=true;input.parentElement.append(button);
    form.querySelector('[name=identity_card]').addEventListener('change',update);
    bindCandidateDates(form);
    bindSignature(form);
    bindIdentityCard(form);
    bindInterviewIdentity(form);
    bindInterviewConsent(form);
  }
};
