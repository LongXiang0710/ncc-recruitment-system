// 人才库专用交互。删除人才库功能时，可随模块一并移除。
function bindRecruitmentChannel(form, fixedType=null) {
  const type=form.querySelector('[name=recruitment_type]'),channel=form.querySelector('[name=channel]'),detail=form.querySelector('[name=channel_detail]');
  if(!channel || !detail)return;
  const choices={'校园招聘':['校园线下','校园平台','智联招聘'],'社会招聘':['boss直聘','智联招聘','化工英才网','其他']};
  if(type && !type.value)type.value=CandidateExperiences.recruitmentTypeFromChannel(type.value,channel.value);
  const toggle=()=>{const show=channel.value==='其他';detail.closest('label').classList.toggle('conditional-hidden',!show);detail.required=show;};
  const update=()=>{const value=channel.value;channel.replaceChildren(new Option('请选择招聘渠道',''),...(choices[fixedType || type?.value] || []).map(item=>new Option(item,item)));channel.value=(choices[fixedType || type?.value] || []).includes(value)?value:'';toggle();};
  type?.addEventListener('change',update);channel.addEventListener('change',toggle);update();
}
function bindCandidateDates(form) {
  const birth=form.querySelector('[name=birthdate]'),graduation=form.querySelector('[name=graduation]'),type=form.querySelector('[name=recruitment_type]'),educationEditor=form.querySelector('.education-editor');
  if(birth)birth.max=today();
  const calculate=()=>{
    const highestGraduation=educationEditor?.highestGraduation?.() || graduation?.value || '';
    if(graduation)graduation.value=highestGraduation;
    const cohort=form.querySelector('[name=cohort]');if(cohort)cohort.value=highestGraduation && (!type || type.value==='校园招聘')?highestGraduation.slice(0,4)+'届':'';
  };
  birth?.addEventListener('input',calculate);graduation?.addEventListener('input',calculate);type?.addEventListener('change',calculate);educationEditor?.addEventListener('educationchange',calculate);calculate();
}

function prepareCandidateEditor({formFields,formRow}) {
  return {
    formFields: formFields.filter(field=>!['graduation','cohort'].includes(field.key)),
    formRow,
  };
}

function placeExperienceEditorsBeforeResume(form, editors) {
  const sections=editors.filter(Boolean);
  const resumeField=form.querySelector('[data-attachment=resume]')?.closest('.attachment-field');
  if(resumeField)resumeField.before(...sections);
  else form.querySelector('.form-grid')?.append(...sections);
}

window.RecruitmentFeatures=window.RecruitmentFeatures || {};
window.RecruitmentFeatures.candidates={
  prepareEditor: prepareCandidateEditor,
  afterEditor({form,formRow}) {
    bindCandidateDates(form);
    bindRecruitmentChannel(form);
    const editor=CandidateExperiences.createExperienceEditor({work_experiences:formRow.work_experiences});
    const education=form.querySelector('.education-editor');
    const type=form.querySelector('[name=recruitment_type]');
    const projectEditor=CandidateProjectExperiences.createProjectExperienceEditor(type?.value,{project_experiences:formRow.project_experiences});
    placeExperienceEditorsBeforeResume(form,[education,editor,projectEditor]);
    type?.addEventListener('change',()=>projectEditor.setType(type.value));
  },
  preparePayload({form,payload}) {
    return {...payload,...form.querySelector('.candidate-experience-editor')?.payload(),...form.querySelector('.candidate-project-experience-editor')?.payload()};
  }
};

if(typeof module!=='undefined' && module.exports)module.exports={bindCandidateDates,prepareCandidateEditor,placeExperienceEditorsBeforeResume};
