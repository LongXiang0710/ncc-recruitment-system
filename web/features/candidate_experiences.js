// 人才库通用工作经历独立编辑组件。
const candidateExperienceConfig={key:'work_experiences',title:'工作经历',organizationLabel:'工作单位',descriptionLabel:'工作描述'};
const candidateExperienceFields=['organization','position','start_date','end_date','description'];

function experienceConfig() {
  return candidateExperienceConfig;
}

function normalizedRows(rows) {
  return (Array.isArray(rows)?rows:[]).map(row=>Object.fromEntries(candidateExperienceFields.map(field=>[field,String(row?.[field] ?? '')])));
}

function recruitmentTypeFromChannel(currentType, channel) {
  if(currentType)return currentType;
  if(['boss直聘','化工英才网','其他'].includes(channel))return '社会招聘';
  if(['校园线下','校园平台','智联招聘'].includes(channel))return '校园招聘';
  return '';
}

function createExperienceState(initialRows={}) {
  const rows=normalizedRows(initialRows.work_experiences);
  return {
    rows:()=>rows,
    payload:()=>({work_experiences:normalizedRows(rows)})
  };
}

function createExperienceEditor(initialRows={}) {
  const section=document.createElement('section');section.className='candidate-experience-editor full';
  const state=createExperienceState(initialRows);
  const blank=()=>({organization:'',position:'',start_date:'',end_date:'',description:''});
  const activeRows=()=>{const rows=state.rows();if(!rows.length)rows.push(blank());return rows;};
  const draw=()=>{
    const config=experienceConfig();
    const rows=activeRows();
    section.innerHTML=`<div class="candidate-experience-head"><div><h3>${config.title}</h3><span class="hint">校园招聘与社会招聘通用，可填写多条；工作单位必填，岗位可选填，结束时间留空表示至今。</span></div><button type="button" class="secondary" data-add-experience>＋ 添加${config.title}</button></div><div class="candidate-experience-list">${rows.map((row,index)=>`<fieldset data-experience-row><legend>${config.title} ${index+1}</legend><label>${config.organizationLabel}（必填）<input data-experience="organization" maxlength="300" value="${escapeHTML(row.organization)}"></label><label>岗位（选填）<input data-experience="position" maxlength="300" value="${escapeHTML(row.position)}"></label><label>开始时间<input type="month" data-experience="start_date" value="${escapeHTML(row.start_date)}"></label><label>结束时间<input type="month" data-experience="end_date" value="${escapeHTML(row.end_date)}"></label><label class="full">${config.descriptionLabel}<textarea data-experience="description" rows="3" maxlength="5000">${escapeHTML(row.description)}</textarea></label><button type="button" class="danger candidate-experience-remove" data-remove-experience ${rows.length===1?'disabled':''}>删除此条</button></fieldset>`).join('')}</div>`;
    section.querySelector('[data-add-experience]').onclick=()=>{if(rows.length>=10){toast(`${config.title}最多添加10条`);return;}rows.push(blank());draw();};
    section.querySelectorAll('[data-remove-experience]').forEach((button,index)=>button.onclick=()=>{rows.splice(index,1);draw();});
    section.querySelectorAll('[data-experience-row]').forEach((item,index)=>item.querySelectorAll('[data-experience]').forEach(input=>input.oninput=()=>{rows[index][input.dataset.experience]=input.value;}));
  };
  section.payload=()=>state.payload();
  draw();return section;
}

const candidateExperiences={experienceConfig,normalizedRows,recruitmentTypeFromChannel,createExperienceState,createExperienceEditor};
if(typeof window!=='undefined')window.CandidateExperiences=candidateExperiences;
if(typeof module!=='undefined' && module.exports)module.exports=candidateExperiences;
