// 社会招聘项目经历独立编辑组件。
const candidateProjectExperienceConfig={key:'project_experiences',title:'项目经历',nameLabel:'项目名称',roleLabel:'担任角色',descriptionLabel:'项目描述'};
const candidateProjectExperienceFields=['project_name','role','start_date','end_date','description'];

function projectExperienceConfig(){return candidateProjectExperienceConfig;}
function normalizedProjectRows(rows){return (Array.isArray(rows)?rows:[]).map(row=>Object.fromEntries(candidateProjectExperienceFields.map(field=>[field,String(row?.[field] ?? '')])));}
function createProjectExperienceState(type,initialRows={}){
  let currentType=type || '';
  const rows=normalizedProjectRows(initialRows.project_experiences);
  return {visible:()=>currentType==='社会招聘',setType:type=>{currentType=type || '';},rows:()=>rows,payload:()=>({project_experiences:currentType==='社会招聘'?normalizedProjectRows(rows):[]})};
}
function createProjectExperienceEditor(type,initialRows={}){
  const section=document.createElement('section');section.className='candidate-project-experience-editor full';
  const state=createProjectExperienceState(type,initialRows),config=projectExperienceConfig();
  const blank=()=>({project_name:'',role:'',start_date:'',end_date:'',description:''});
  const rows=state.rows();if(!rows.length)rows.push(blank());
  const draw=()=>{
    section.hidden=!state.visible();
    section.innerHTML=`<div class="candidate-project-experience-head"><div><h3>${config.title}</h3><span class="hint">仅社会招聘人才填写，可添加多条；项目名称和开始时间必填，担任角色可选填，结束时间留空表示至今。</span></div><button type="button" class="secondary" data-add-project>＋ 添加${config.title}</button></div><div class="candidate-project-experience-list">${rows.map((row,index)=>`<fieldset data-project-row><legend>${config.title} ${index+1}</legend><label>${config.nameLabel}（必填）<input data-project="project_name" maxlength="300" value="${escapeHTML(row.project_name)}"></label><label>${config.roleLabel}（选填）<input data-project="role" maxlength="300" value="${escapeHTML(row.role)}"></label><label>开始时间（必填）<input type="month" data-project="start_date" value="${escapeHTML(row.start_date)}"></label><label>结束时间<input type="month" data-project="end_date" value="${escapeHTML(row.end_date)}"></label><label class="full">${config.descriptionLabel}<textarea data-project="description" rows="3" maxlength="5000">${escapeHTML(row.description)}</textarea></label><button type="button" class="danger candidate-project-experience-remove" data-remove-project ${rows.length===1?'disabled':''}>删除此条</button></fieldset>`).join('')}</div>`;
    section.querySelector('[data-add-project]').onclick=()=>{if(rows.length>=10){toast('项目经历最多添加10条');return;}rows.push(blank());draw();};
    section.querySelectorAll('[data-remove-project]').forEach((button,index)=>button.onclick=()=>{rows.splice(index,1);draw();});
    section.querySelectorAll('[data-project-row]').forEach((item,index)=>item.querySelectorAll('[data-project]').forEach(input=>input.oninput=()=>{rows[index][input.dataset.project]=input.value;}));
  };
  section.setType=type=>{state.setType(type);draw();};section.payload=()=>state.payload();draw();return section;
}
const candidateProjectExperiences={projectExperienceConfig,normalizedProjectRows,createProjectExperienceState,createProjectExperienceEditor};
if(typeof window!=='undefined')window.CandidateProjectExperiences=candidateProjectExperiences;
if(typeof module!=='undefined' && module.exports)module.exports=candidateProjectExperiences;
