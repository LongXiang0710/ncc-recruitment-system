// 应聘登记专用页面与交互。
async function application() {
  try {
    const spec=await api('public/schema');
    spec.fields=[{...spec.fields.find(field=>field.key==='name'),section:'基本信息',fullWidth:true},{...spec.fields.find(field=>field.key==='phone'),section:undefined,fullWidth:true},{...spec.fields.find(field=>field.key==='identity_card'),fullWidth:true},...spec.fields.filter(field=>!['phone','name','identity_card'].includes(field.key)).map(field=>field.key==='email'?{...field,fullWidth:true}:field)];
    const educationRequired=new Set(spec.fields.filter(field=>field.required && ['education','school_name','major'].includes(field.key)).map(field=>field.key));
    spec.fields=spec.fields.filter(field=>!['education','school_name','major'].includes(field.key));
    app.innerHTML=`<main class="apply"><a class="identity" href="/"><div class="logo">N</div><div>南化建<strong>校园招聘</strong></div></a><div class="apply-title"><div class="eyebrow">CAMPUS RECRUITMENT</div><h1>校园招聘应聘登记</h1><p>你好，未来的同行者。请填写真实信息，让我们更好地了解你。</p></div><section class="panel"><form id="apply-form"><div class="panel-head"><h3>个人信息与求职意向</h3><span class="hint">* 为必填</span></div><div class="form-grid">${await fieldsHTML(spec.fields)}</div><div class="consent"><label><input type="checkbox" required> 我确认所填信息真实，并同意将上述信息用于本次校园招聘联系、面试及录用评估。</label><p class="hint">如需更正或删除已提交资料，请联系招聘工作人员。相同手机号再次提交将更新已有登记及匹配的人才资料。</p></div><p class="error form-error" role="alert"></p><div class="dialog-foot"><button class="primary" type="submit">提交应聘登记 →</button></div></form></section><p class="hint center">南化建 · 校园招聘</p></main>`;
    document.querySelector('#apply-form [for=f-gender]')?.after(candidateEducationEditor([{education:'',school_name:'',major:''}],educationRequired));
    PositionFields.bind(document.querySelector('#apply-form'));
    bindCandidateDates(document.querySelector('#apply-form'));
    bindIdentityCard(document.querySelector('#apply-form'));
    bindSignature(document.querySelector('#apply-form'));
    bindApplicationPhone(document.querySelector('#apply-form'),'public');
    document.querySelector('#apply-form').onsubmit=async event=>{event.preventDefault();const button=event.target.querySelector('[type=submit]');button.disabled=true;try{const result=await api('public/apply',{method:'POST',body:JSON.stringify(await formPayload(event.target))});document.querySelector('.apply .panel').innerHTML=`<div class="success"><div>✓</div><h2>应聘登记已提交</h2><p>登记编号：${result.id}</p><p>招聘工作人员将根据岗位需求与你联系，请保持电话畅通。</p><a href="/apply" class="secondary">返回登记页面</a></div>`;}catch(error){document.querySelector('.form-error').textContent=error.message;button.disabled=false;}};
  }catch(error){app.textContent=error.message;}
}
function bindApplicationPhone(form,entity='applications') {
  const phone=form.querySelector('[name=phone]');
  if(entity!=='public')phone.addEventListener('input',()=>fillLinkedAttachments(form,{},['resume']));
  const hint=document.createElement('p');hint.className='hint full';hint.setAttribute('role','status');hint.textContent='填写联系电话后自动按相同号码调取人才库资料，未匹配时可手动填写。';form.querySelector('.form-grid').prepend(hint);
  let timer,version=0,lastMatched='',filled={};
  const lookup=async()=>{
    const number=phone.value.trim();if(!number || number===lastMatched)return;
    const request=++version;hint.textContent='正在匹配人才库…';
    try {
      const result=await api((entity==='public'?'public/application-prefill':entity==='interviews'?'interview-prefill':'application-prefill')+'?phone='+encodeURIComponent(number));
      if(request!==version || phone.value.trim()!==number || !form.isConnected)return;
      if(entity!=='public')fillLinkedAttachments(form,result.resume?{resume:{id:result.resume,name:result.resume_name}}:{},['resume']);
      if(!result.matched){hint.textContent='未找到相同联系电话的人才，请手动填写。';return;}
      filled={};
      for(const [key,value] of Object.entries(result.values)){
        if(key==='education_experiences'){form.querySelector('.education-editor')?.setRows(value);continue;}
        const input=form.querySelector(`[name=${key}]`);if(input && key!=='phone'){input.value=value;filled[key]=String(value);}
      }
      PositionFields.refresh(form);
      lastMatched=number;form.querySelector('[name=identity_card]').dispatchEvent(new Event('input'));form.querySelector('[name=birthdate]').dispatchEvent(new Event('input'));
      hint.textContent='已按联系电话带入人才资料，可继续补充修改。'+(result.resume_name?'保存新登记或变更电话时带入简历：'+result.resume_name:'');
    }catch(error){if(request===version && form.isConnected)hint.textContent=error.message;}
  };
  phone.addEventListener('input',()=>{clearTimeout(timer);version++;lastMatched='';for(const [key,value] of Object.entries(filled)){const input=form.querySelector(`[name=${key}]`);if(input?.value===value)input.value='';}filled={};form.querySelector('.education-editor')?.setRows([]);form.querySelector('[name=birthdate]').dispatchEvent(new Event('input'));hint.textContent='填写联系电话后自动匹配人才库。';if(phone.value.trim().length>=7)timer=setTimeout(lookup,450);});
  phone.addEventListener('input',()=>form.querySelector('[name=identity_card]').dispatchEvent(new Event('input')));
  phone.addEventListener('change',()=>{clearTimeout(timer);lookup();});
  dialog.addEventListener('close',()=>{clearTimeout(timer);version++;},{once:true});
}
function bindApplicationLanguage(form) {
  const language=form.querySelector('[name=language]');
  const fields=['english_level','language_scores'].map(key=>form.querySelector(`[name=${key}]`));
  const required=fields.map(input=>input.required);
  const update=()=>fields.forEach((input,index)=>{
    const hide=['其他','无'].includes(language.value);
    input.closest('label').classList.toggle('conditional-hidden',hide);
    input.required=!hide && required[index];
  });
  language.addEventListener('change',update);update();
}

window.RecruitmentFeatures=window.RecruitmentFeatures || {};
window.RecruitmentFeatures.applications={
  prepareEditor({spec,formFields,formRow}) {
    formFields=[{...spec.fields.find(field=>field.key==='name'),section:'基本信息',fullWidth:true},{...spec.fields.find(field=>field.key==='phone'),section:undefined,fullWidth:true},{...spec.fields.find(field=>field.key==='identity_card'),fullWidth:true},...spec.fields.filter(field=>!['phone','name','identity_card'].includes(field.key))];
    const scores=spec.fields.find(field=>field.key==='language_scores');
    formFields=formFields.filter(field=>field.key!=='language_scores').flatMap(field=>field.key==='english_level'?[{...field,fullWidth:true},{...scores,fullWidth:true}]:[field]);
    return {formFields,formRow};
  },
  afterEditor({form}) {
    bindCandidateDates(form);
    bindSignature(form);
    bindIdentityCard(form);
    bindApplicationPhone(form);
    bindApplicationLanguage(form);
  }
};
