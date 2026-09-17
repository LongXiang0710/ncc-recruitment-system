// 简历收集、识别和入库专用交互。
const RESUME_POSITION_SUFFIXES=['高级工程师','工程师','项目经理','技术员','施工员','安全员','资料员','预算员','造价员','管理员','设计师','会计','出纳','专员','主管','经理','总监','助理','实习生','操作工','焊工','电工','钳工'];
const RESUME_FILE_EXTENSIONS=['txt','md','mdx','markdown','pdf','html','xlsx','xls','doc','docx','csv','eml','msg','pptx','ppt','xml','epub','jpg','jpeg','png','gif','webp','svg'];
const RESUME_FILE_ACCEPT=RESUME_FILE_EXTENSIONS.map(extension=>'.'+extension).join(',');
const RESUME_FILE_FORMAT_HINT='文档：TXT、MD、MDX、MARKDOWN、PDF、HTML、XLSX、XLS、DOC、DOCX、CSV、EML、MSG、PPTX、PPT、XML、EPUB；图片：JPG、JPEG、PNG、GIF、WEBP、SVG。';
const RESUME_FILTER_CHANNELS=['校园线下','校园平台','智联招聘','boss直聘','化工英才网','其他'];
let resumeListFilters={start_date:'',end_date:'',recruitment_type:'',channel:''};
function isSupportedResumeFile(file) {
  const extension=String(file?.name || '').split('.').pop().toLowerCase();
  return RESUME_FILE_EXTENSIONS.includes(extension);
}
function inferResumePosition(filename) {
  const stem=String(filename || '').replace(/^.*[\\/]/,'').replace(/\.[^.]*$/,'');
  const segments=stem.split(/[_\-—–\s]+/).filter(Boolean);
  const clean=(segment,allowPlain=false)=>{
    const value=String(segment || '').replace(/^[ _\-—–()（）\[\]【】]+|[ _\-—–()（）\[\]【】]+$/g,'');
    if(!value || value.length>50 || /^(?:\d+|简历|个人简历|校园招聘|社会招聘|校招|社招|智联简历|智联招聘|boss直聘|化工英才网)$/i.test(value))return '';
    const suffix=RESUME_POSITION_SUFFIXES.find(item=>value.includes(item));
    if(suffix)return value.slice(0,value.indexOf(suffix)+suffix.length);
    return allowPlain?value:'';
  };
  const ageIndex=segments.findIndex(segment=>/^(?:1[6-9]|[2-5]\d|6[0-5])岁$/.test(segment));
  if(ageIndex>=0 && ageIndex+1<segments.length)return clean(segments[ageIndex+1],true);
  for(const segment of segments){const result=clean(segment);if(result)return result;}
  return '';
}
function applyFilenamePosition(positionInput,filename,detailInput=null) {
  if(!positionInput)return '';
  const prior=positionInput.dataset.filenamePosition || '';
  const current=positionInput.value==='其它' && detailInput?detailInput.value:positionInput.value;
  if(String(current || '').trim() && current!==prior)return current;
  const inferred=inferResumePosition(filename);
  if(detailInput && typeof PositionFields!=='undefined')PositionFields.setRecognized({elements:{position:positionInput,position_detail:detailInput}},inferred);
  else positionInput.value=inferred;
  positionInput.dataset.filenamePosition=inferred;
  return inferred;
}
function bindFilenamePosition(form) {
  const fileInput=form.querySelector('[data-attachment=resume]'),positionInput=form.elements.position,detailInput=form.elements.position_detail;
  if(!fileInput || !positionInput)return;
  fileInput.addEventListener('change',()=>applyFilenamePosition(positionInput,fileInput.files?.[0]?.name || '',detailInput));
}
async function resumeCollectionQr() {
  try {
    const result=await api('resume-collection-qr');
    dialog.classList.add('wide-dialog','qr-dialog','qr-showcase-dialog');
    dialog.innerHTML=`<div class="dialog-head"><h2>简历收集二维码</h2><button type="button" class="close" aria-label="关闭">×</button></div><div class="qr-grid resume-qr-grid">${result.items.map(item=>QrCards.renderQrCard({label:item.label+'简历投递',image:item.image,imageAlt:item.label+'简历投递二维码',downloadName:item.label+'简历投递二维码.svg',labelAbove:true})).join('')}</div><div class="dialog-foot"><button type="button" class="secondary">关闭</button></div>`;
    tableLayout.floatDialogClose(dialog);
    dialog.addEventListener('close',()=>dialog.classList.remove('wide-dialog','qr-dialog','qr-showcase-dialog'),{once:true});
    dialog.querySelectorAll('button').forEach(button=>button.onclick=()=>dialog.close());dialog.showModal();
  } catch(error){toast(error.message);}
}
async function publicResumeCollection() {
  const kind=new URLSearchParams(location.search).get('type');
  if(!['campus','social'].includes(kind)){app.textContent='入口无效，请使用校园招聘或社会招聘二维码打开。';return;}
  const label=kind==='campus'?'校园招聘':'社会招聘';
  try {
    const spec=await api('public/resume-schema');
    spec.fields=spec.fields.filter(field=>!['channel','channel_detail'].includes(field.key));
    app.innerHTML=`<main class="apply"><div class="identity"><div class="logo">N</div><div>南化建<strong>招聘管理系统</strong></div></div><div class="apply-title"><h1>简历收集</h1><p>填写并上传简历，招聘工作人员将统一处理。</p></div><section class="panel"><form><div class="panel-head"><h3>简历信息</h3></div><div class="form-grid">${await fieldsHTML(spec.fields)}</div><div class="consent"><label><input type="checkbox" required> 我确认所填信息真实，并同意将简历用于本次招聘。</label></div><p class="error form-error" role="alert"></p><div class="dialog-foot"><button type="submit" class="primary">提交简历</button></div></form></section></main>`;
    const form=app.querySelector('form');form.querySelector('[data-attachment=resume]').required=true;PositionFields.bind(form);bindFilenamePosition(form);
    form.onsubmit=async event=>{
      event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
      try {await api('public/resumes/'+kind,{method:'POST',body:JSON.stringify(await formPayload(form))});app.querySelector('.panel').innerHTML='<div class="success"><div>✓</div><h2>简历已提交</h2><p>感谢投递，请勿重复提交。</p></div>';}
      catch(error){form.querySelector('.form-error').textContent=error.message;button.disabled=false;}
    };
  } catch(error){app.textContent=error.message;}
}

function publicResumeBatch() {
  app.innerHTML=`<main class="apply"><div class="identity"><div class="logo">N</div><div>南化建<strong>招聘管理系统</strong></div></div><div class="apply-title"><h1>批量导入简历</h1><p>无需登录。请选择招聘类型和招聘渠道，然后增加一份或多份简历文件。</p></div><section class="panel"><form><div class="panel-head"><h3>批量导入信息</h3></div><div class="form-grid"><label>招聘类型<span class="required"> *</span><select name="recruitment_type" required><option value="">请选择招聘类型</option><option>校园招聘</option><option>社会招聘</option></select></label><label>招聘渠道<span class="required"> *</span><select name="channel" required><option value="">请先选择招聘类型</option></select></label><label class="full conditional-hidden">其他渠道详情<span class="required"> *</span><input name="channel_detail" maxlength="100" placeholder="请填写具体招聘渠道"></label><div class="full resume-file-picker-area"><label>简历文件<span class="required"> *</span></label><input id="public-resume-file-picker" class="resume-file-picker" name="resume_files" type="file" accept="${RESUME_FILE_ACCEPT}" multiple><button type="button" class="secondary add-resume-files">＋ 增加文件</button><span class="hint resume-file-summary">尚未增加文件</span><span class="hint">${RESUME_FILE_FORMAT_HINT}</span><ul class="resume-selected-files"></ul></div></div><div class="import-body resume-import-result" aria-live="polite"></div><p class="error form-error" role="alert"></p><div class="dialog-foot"><button type="submit" class="primary" disabled>开始导入</button></div></form></section><p class="hint center">每份文件最大50MB；单份失败不会影响其他文件。</p></main>`;
  const form=app.querySelector('form'),fileInput=form.elements.resume_files,fileList=form.querySelector('.resume-selected-files'),submitButton=form.querySelector('[type=submit]');
  let selectedFiles=[],busy=false;
  bindRecruitmentChannel(form);
  const renderSelectedFiles=()=>{
    form.querySelector('.resume-file-summary').textContent=selectedFiles.length?`已增加 ${selectedFiles.length} 份文件`:'尚未增加文件';
    fileList.innerHTML=selectedFiles.map((file,index)=>{const position=inferResumePosition(file.name);return `<li><span>${escapeHTML(file.name)}${position?`（岗位：${escapeHTML(position)}）`:''}</span><button type="button" data-remove-file="${index}" aria-label="移除${escapeHTML(file.name)}">移除</button></li>`;}).join('');
    submitButton.disabled=busy || !selectedFiles.length;
  };
  form.querySelector('.add-resume-files').onclick=()=>fileInput.click();
  fileInput.onchange=()=>{selectedFiles=mergeResumeFiles(selectedFiles,[...fileInput.files]);fileInput.value='';renderSelectedFiles();};
  fileList.onclick=event=>{const button=event.target.closest('[data-remove-file]');if(!button || busy)return;selectedFiles.splice(Number(button.dataset.removeFile),1);renderSelectedFiles();};
  form.onsubmit=async event=>{
    event.preventDefault();
    const files=[...selectedFiles],errorLine=form.querySelector('.form-error'),resultBox=form.querySelector('.resume-import-result');
    errorLine.textContent='';resultBox.innerHTML='';busy=true;form.querySelectorAll('button,input,select').forEach(control=>control.disabled=true);
    try {
      const metadata={recruitment_type:form.elements.recruitment_type.value,channel:form.elements.channel.value,channel_detail:form.elements.channel_detail.value};
      const kind=metadata.recruitment_type==='校园招聘'?'campus':'social',items=[];
      const result=await importResumeBatch(files,metadata,{
        encodeFile:readResumeFile,
        request:api,
        requestPath:'public/resumes/'+kind,
        onProgress:(item,index,total)=>{
          items.push(item);
          resultBox.innerHTML=`<p class="hint">正在导入 ${index}/${total}…</p><ul class="resume-import-list">${items.map(row=>`<li class="${row.status==='成功'?'import-success':'import-failure'}">${escapeHTML(row.name)}：${row.status}${row.error?'（'+escapeHTML(row.error)+'）':''}</li>`).join('')}</ul>`;
        }
      });
      resultBox.innerHTML=`<p class="import-ok">导入完成：成功 ${result.succeeded} 份，失败 ${result.failed} 份。</p><ul class="resume-import-list">${result.items.map(row=>`<li class="${row.status==='成功'?'import-success':'import-failure'}">${escapeHTML(row.name)}：${row.status}${row.error?'（'+escapeHTML(row.error)+'）':''}</li>`).join('')}</ul>`;
      selectedFiles=files.filter((file,index)=>result.items[index].status==='失败');
    } catch(error) {
      errorLine.textContent=error.message;
    } finally {
      busy=false;form.querySelectorAll('button,input,select').forEach(control=>control.disabled=false);renderSelectedFiles();
    }
  };
}
async function recognizeResumes(ids) {
  if(!ids.length)return;
  try {
    const config=await api('recognition-config');
    if(!config.configured){toast(config.message);return;}
    const chosen=ids.map(id=>records.find(row=>row.id===id)).filter(Boolean);
    const popup=document.createElement('dialog');
    popup.innerHTML=`<div class="dialog-head"><h2>批量识别</h2><button class="close" disabled aria-label="关闭">×</button></div><div class="import-body"><p role="status">正在识别，请保持页面打开…</p><ul>${chosen.map(row=>`<li data-result="${row.id}">${escapeHTML(row.name)}：等待处理</li>`).join('')}</ul></div>`;
    tableLayout.floatDialogClose(popup);
    document.body.append(popup);popup.showModal();
    popup.addEventListener('cancel',event=>event.preventDefault());
    popup.querySelector('.close').onclick=()=>{popup.close();popup.remove();if(current==='resume_documents')render();};
    let succeeded=0,failed=0,skipped=0;
    for(const row of chosen){
      const line=popup.querySelector(`[data-result="${row.id}"]`);
      if(!canRecognizeResume(row)){line.textContent=`${row.name}：跳过（${row.status}）`;skipped++;continue;}
      line.textContent=`${row.name}：识别中…`;
      try{await api(`resume_documents/${row.id}/recognize`,{method:'POST'});line.textContent=`${row.name}：已识别，可通过“识别结果入库”核对保存`;succeeded++;}
      catch(error){line.textContent=`${row.name}：${error.message}`;failed++;}
    }
    popup.querySelector('[role=status]').textContent=`处理完成：成功 ${succeeded} 条，失败 ${failed} 条，跳过 ${skipped} 条。`;
    popup.querySelector('.close').disabled=false;
  }catch(error){toast(error.message);}
}
function canRecognizeResume(source) {
  return !!source && ['待识别','失败'].includes(source.status);
}
async function recognizeOneResume(source,services={}) {
  if(!canRecognizeResume(source))throw new Error('只有待识别或失败简历可以发起识别');
  const request=services.request || api;
  const review=services.review || resumeRecognitionResult;
  const refresh=services.refresh || (()=>render());
  const config=await request('recognition-config');
  if(!config.configured)throw new Error(config.message || '尚未配置 Dify API Key');
  try {
    await request(`resume_documents/${source.id}/recognize`,{method:'POST'});
  } catch(error) {
    try{await refresh();}catch{}
    throw error;
  }
  const recognized={...source,status:'已识别'};
  await review(recognized);
  await refresh();
  return recognized;
}
async function openDifyWorkflow() {
  try {
    const config=await api('dify-embed');
    if(!config.url){toast('尚未配置 Dify 工作流，请提供发布后的嵌入链接。');return;}
    const popup=document.createElement('dialog');popup.className='attachment-preview-dialog';
    popup.innerHTML='<div class="dialog-head"><h2>Dify 工作流</h2><button class="close" aria-label="关闭">×</button></div><div class="attachment-preview-body"></div>';
    tableLayout.floatDialogClose(popup);
    const frame=document.createElement('iframe');frame.src=config.url;frame.title='Dify 简历识别工作流';frame.referrerPolicy='no-referrer';frame.setAttribute('sandbox','allow-scripts allow-forms allow-same-origin allow-downloads');popup.querySelector('.attachment-preview-body').append(frame);
    popup.querySelector('button').onclick=()=>popup.close();popup.addEventListener('close',()=>popup.remove(),{once:true});document.body.append(popup);popup.showModal();
  } catch(error){toast(error.message);}
}
function recognitionDraft(data,candidateFields,source){
  if(!data || Array.isArray(data) || typeof data!=='object')throw new Error('识别结果须为 JSON 对象');
  const draft={};
  for(const field of candidateFields){
    if(field.hidden || field.readonly || field.type==='attachment')continue;
    const value=data[field.key] ?? data[field.label];
    if(value!=null){if(typeof value==='object')throw new Error(field.label+'须为文字');draft[field.key]=String(value);}
  }
  for(const key of ['education_experiences','work_experiences','project_experiences']){
    if(key==='project_experiences' && source.recruitment_type!=='社会招聘')continue;
    if(data[key]==null)continue;
    if(!Array.isArray(data[key]) || data[key].some(row=>!row || Array.isArray(row) || typeof row!=='object'))throw new Error('识别结果中的经历格式不正确');
    draft[key]=data[key].map(row=>({...row}));
  }
  return {...draft,channel:source.channel || draft.channel || '',channel_detail:source.channel_detail || draft.channel_detail || '',recruitment_type:source.recruitment_type || draft.recruitment_type || '',resume:source.resume,resume_name:source.resume_name};
}
async function resumeRecognitionResult(source) {
  let saved=null;try{saved=(await api(`resume_documents/${source.id}/recognition-result`)).result;}catch(error){toast(error.message);return;}
  dialog.innerHTML=`<form><div class="dialog-head"><h2>识别结果入库</h2><button type="button" class="close" aria-label="关闭">×</button></div><div class="form-grid"><p class="hint full">${escapeHTML(source.name)}：粘贴 Dify 输出的 JSON，下一步核对人才字段。也可留空后手动填写。</p><label class="full">识别结果 JSON<textarea name="result" rows="9" placeholder='{"name":"姓名","phone":"手机号","school_name":"毕业院校","education":"本科","major":"专业"}'></textarea></label></div><p class="error form-error"></p><div class="dialog-foot"><button class="primary" type="submit">核对人才信息</button></div></form>`;
  tableLayout.floatDialogClose(dialog);
  if(saved)dialog.querySelector('[name=result]').value=JSON.stringify(saved,null,2);
  dialog.querySelector('.close').onclick=()=>dialog.close();if(!dialog.open)dialog.showModal();
  dialog.querySelector('form').onsubmit=event=>{
    event.preventDefault();
    try {
      const raw=event.target.elements.result.value.trim();const data=raw?JSON.parse(raw):{};
      const draft=recognitionDraft(data,schemas.candidates.fields,source);
      dialog.close();edit('candidates',null,draft,source.id);
    } catch(error){dialog.querySelector('.form-error').textContent=error.message;}
  };
}

function prepareResumeToolbar(toolbar,searchInput,services={}) {
  toolbar.querySelector('#export')?.remove();
  const importButton=toolbar.querySelector('#import-excel');
  if(importButton)importButton.textContent='↑ 批量导入简历';
  searchInput.placeholder='搜索档案编号、简历名称…';
  const top=searchInput.parentElement;
  if(!top || !toolbar.ownerDocument)return;
  top.classList.add('resume-toolbar-top');
  const filterArea=toolbar.ownerDocument.createElement('div');
  filterArea.className='resume-filter-area';
  filterArea.innerHTML=`<button type="button" class="secondary resume-filter-toggle" aria-expanded="false">筛选</button><div class="resume-filter-panel" hidden><div class="resume-filter-grid"><label>上传开始日期<input type="date" name="start_date"></label><label>上传结束日期<input type="date" name="end_date"></label><label>招聘类型<select name="recruitment_type"><option value="">全部</option><option>校园招聘</option><option>社会招聘</option></select></label><label>招聘渠道<select name="channel"><option value="">全部</option>${RESUME_FILTER_CHANNELS.map(item=>`<option>${item}</option>`).join('')}</select></label></div><p class="error resume-filter-error" role="alert"></p><div class="resume-filter-actions"><button type="button" class="secondary resume-filter-reset">重置</button><button type="button" class="primary resume-filter-apply">应用筛选</button></div></div>`;
  top.append(filterArea);
  const panel=filterArea.querySelector('.resume-filter-panel');
  const toggle=filterArea.querySelector('.resume-filter-toggle');
  const updateButton=()=>{
    const active=hasActiveResumeFilters(resumeListFilters);
    toggle.textContent=active?'筛选（已选）':'筛选';
    toggle.classList.toggle('active',active);
  };
  Object.entries(resumeListFilters).forEach(([key,value])=>{panel.querySelector(`[name="${key}"]`).value=value;});
  updateButton();
  toggle.onclick=()=>{panel.hidden=!panel.hidden;toggle.setAttribute('aria-expanded',String(!panel.hidden));};
  panel.querySelector('.resume-filter-apply').onclick=()=>{
    const next=Object.fromEntries(['start_date','end_date','recruitment_type','channel'].map(key=>[key,panel.querySelector(`[name="${key}"]`).value]));
    const error=panel.querySelector('.resume-filter-error');
    if(next.start_date && next.end_date && next.start_date>next.end_date){error.textContent='上传开始日期不能晚于结束日期';return;}
    error.textContent='';resumeListFilters=next;panel.hidden=true;toggle.setAttribute('aria-expanded','false');updateButton();services.onChange?.();
  };
  panel.querySelector('.resume-filter-reset').onclick=()=>{
    resumeListFilters={start_date:'',end_date:'',recruitment_type:'',channel:''};
    panel.querySelectorAll('input,select').forEach(control=>{control.value='';});
    panel.querySelector('.resume-filter-error').textContent='';panel.hidden=true;toggle.setAttribute('aria-expanded','false');updateButton();services.onChange?.();
  };
}

function filterResumeRecords(records,filters={}) {
  const start=String(filters.start_date || '');
  const end=String(filters.end_date || '');
  const recruitmentType=String(filters.recruitment_type || '');
  const channel=String(filters.channel || '');
  return records.filter(row=>{
    const uploaded=String(row.created_at || row.created_date || '').slice(0,10);
    if(start && (!uploaded || uploaded<start))return false;
    if(end && (!uploaded || uploaded>end))return false;
    if(recruitmentType && row.recruitment_type!==recruitmentType)return false;
    if(channel && row.channel!==channel)return false;
    return true;
  });
}

function hasActiveResumeFilters(filters={}) {
  return Object.values(filters).some(value=>String(value || '').trim());
}

async function importResumeBatch(files,metadata,services={}) {
  if(!metadata?.recruitment_type)throw new Error('请选择招聘类型');
  if(!metadata.channel)throw new Error('请选择招聘渠道');
  if(metadata.channel==='其他' && !String(metadata.channel_detail || '').trim())throw new Error('请填写其他渠道详情');
  if(!files?.length)throw new Error('请选择需要导入的简历文件');
  const encodeFile=services.encodeFile;
  const request=services.request;
  if(typeof encodeFile!=='function' || typeof request!=='function')throw new Error('批量导入服务不可用');
  const items=[];
  for(const file of files) {
    let item;
    try {
      if(!isSupportedResumeFile(file))throw new Error('文件格式不支持');
      if(file.size>50*1024*1024)throw new Error('文件超过50MB');
      const content=await encodeFile(file);
      await request(services.requestPath || 'resume_documents',{method:'POST',body:JSON.stringify({
        name:file.name,
        position:String(file.position || inferResumePosition(file.name) || '').trim(),
        recruitment_type:metadata.recruitment_type,
        channel:metadata.channel,
        channel_detail:metadata.channel==='其他'?String(metadata.channel_detail || '').trim():'',
        _resume_upload:{name:file.name,content}
      })});
      item={name:file.name,status:'成功'};
    } catch(error) {
      item={name:file.name,status:'失败',error:error.message || '导入失败'};
    }
    items.push(item);
    services.onProgress?.(item,items.length,files.length);
  }
  return {total:items.length,succeeded:items.filter(item=>item.status==='成功').length,failed:items.filter(item=>item.status==='失败').length,items};
}

function readResumeFile(file) {
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(String(reader.result).split(',')[1]);
    reader.onerror=()=>reject(new Error('读取文件失败'));
    reader.readAsDataURL(file);
  });
}

function mergeResumeFiles(selected,incoming) {
  const files=[],keys=new Set();
  for(const file of [...selected,...incoming]) {
    const key=[file.name,file.size,file.lastModified || 0].join('\u0000');
    if(keys.has(key))continue;
    keys.add(key);files.push(file);
  }
  return files;
}

function openResumeImport() {
  let busy=false,selectedFiles=[];
  dialog.innerHTML=`<form><div class="dialog-head"><div><div class="eyebrow">RESUME IMPORT</div><h2>批量导入简历</h2></div><button type="button" class="close" aria-label="关闭">×</button></div><div class="form-grid"><p class="hint full">本次选择的招聘类型和招聘渠道将应用于全部文件。每份文件最大50MB，成功文件会保存为“待识别”，失败文件不影响其他文件。</p><label>招聘类型<span class="required"> *</span><select name="recruitment_type" required><option value="">请选择招聘类型</option><option>校园招聘</option><option>社会招聘</option></select></label><label>招聘渠道<span class="required"> *</span><select name="channel" required><option value="">请先选择招聘类型</option></select></label><label class="full conditional-hidden">其他渠道详情<span class="required"> *</span><input name="channel_detail" maxlength="100" placeholder="请填写具体招聘渠道"></label><div class="full resume-file-picker-area"><label>简历文件<span class="required"> *</span></label><input id="resume-file-picker" class="resume-file-picker" name="resume_files" type="file" accept="${RESUME_FILE_ACCEPT}" multiple><button type="button" class="secondary add-resume-files">＋ 增加文件</button><span class="hint resume-file-summary">尚未增加文件</span><span class="hint">${RESUME_FILE_FORMAT_HINT}</span><ul class="resume-selected-files"></ul></div></div><div class="import-body resume-import-result" aria-live="polite"></div><p class="error form-error" role="alert"></p><div class="dialog-foot"><button type="button" class="secondary cancel">取消</button><button type="submit" class="primary" disabled>开始导入</button></div></form>`;
  tableLayout.floatDialogClose(dialog);
  const form=dialog.querySelector('form');
  const close=()=>{if(!busy)dialog.close();};
  dialog.querySelector('.close').onclick=close;
  dialog.querySelector('.cancel').onclick=close;
  bindRecruitmentChannel(form);
  const fileInput=form.elements.resume_files;
  const fileList=form.querySelector('.resume-selected-files'),submitButton=form.querySelector('[type=submit]');
  const renderSelectedFiles=()=>{
    form.querySelector('.resume-file-summary').textContent=selectedFiles.length?`已增加 ${selectedFiles.length} 份文件`:'尚未增加文件';
    fileList.innerHTML=selectedFiles.map((file,index)=>{const position=inferResumePosition(file.name);return `<li><span>${escapeHTML(file.name)}${position?`（岗位：${escapeHTML(position)}）`:''}</span><button type="button" data-remove-file="${index}" aria-label="移除${escapeHTML(file.name)}">移除</button></li>`;}).join('');
    submitButton.disabled=!selectedFiles.length;
  };
  form.querySelector('.add-resume-files').onclick=()=>fileInput.click();
  fileInput.onchange=()=>{selectedFiles=mergeResumeFiles(selectedFiles,[...fileInput.files]);fileInput.value='';renderSelectedFiles();};
  fileList.onclick=event=>{const button=event.target.closest('[data-remove-file]');if(!button)return;selectedFiles.splice(Number(button.dataset.removeFile),1);renderSelectedFiles();};
  const cancelWhileBusy=event=>{if(busy)event.preventDefault();};
  dialog.addEventListener('cancel',cancelWhileBusy);
  dialog.addEventListener('close',()=>dialog.removeEventListener('cancel',cancelWhileBusy),{once:true});
  form.onsubmit=async event=>{
    event.preventDefault();
    const files=[...selectedFiles],errorLine=form.querySelector('.form-error'),resultBox=form.querySelector('.resume-import-result');
    errorLine.textContent='';resultBox.innerHTML='';busy=true;form.querySelectorAll('button,input,select').forEach(control=>control.disabled=true);
    try {
      const metadata={recruitment_type:form.elements.recruitment_type.value,channel:form.elements.channel.value,channel_detail:form.elements.channel_detail.value};
      const items=[];
      const result=await importResumeBatch(files,metadata,{
        encodeFile:readResumeFile,
        request:api,
        onProgress:(item,index,total)=>{
          items.push(item);
          resultBox.innerHTML=`<p class="hint">正在导入 ${index}/${total}…</p><ul class="resume-import-list">${items.map(row=>`<li class="${row.status==='成功'?'import-success':'import-failure'}">${escapeHTML(row.name)}：${row.status}${row.error?'（'+escapeHTML(row.error)+'）':''}</li>`).join('')}</ul>`;
        }
      });
      resultBox.innerHTML=`<p class="import-ok">导入完成：成功 ${result.succeeded} 份，失败 ${result.failed} 份。</p><ul class="resume-import-list">${result.items.map(row=>`<li class="${row.status==='成功'?'import-success':'import-failure'}">${escapeHTML(row.name)}：${row.status}${row.error?'（'+escapeHTML(row.error)+'）':''}</li>`).join('')}</ul>`;
      if(current==='resume_documents')await render();
      form.querySelector('[type=submit]').remove();form.querySelector('.cancel').textContent='关闭';
    } catch(error) {
      errorLine.textContent=error.message;
    } finally {
      busy=false;form.querySelectorAll('button,input,select').forEach(control=>control.disabled=false);
    }
  };
  dialog.showModal();
}

if(typeof window!=='undefined'){
window.RecruitmentFeatures=window.RecruitmentFeatures || {};
window.RecruitmentFeatures.resume_documents={
  prepareToolbar({toolbar,search,applyFilters}) {
    prepareResumeToolbar(toolbar,search,{onChange:applyFilters});
  },
  filterRecords(rows) {
    return filterResumeRecords(rows,resumeListFilters);
  },
  hasActiveFilters() {
    return hasActiveResumeFilters(resumeListFilters);
  },
  prepareEditor({formFields,formRow}) {
    return {formFields:formFields.filter(field=>field.key!=='name'),formRow};
  },
  afterEditor({form}) {
    bindRecruitmentChannel(form);
    bindFilenamePosition(form);
  },
  importRecords() {
    openResumeImport();
  }
};
}
if(typeof module!=='undefined' && module.exports)module.exports={recognitionDraft,canRecognizeResume,recognizeOneResume,prepareResumeToolbar,filterResumeRecords,hasActiveResumeFilters,importResumeBatch,mergeResumeFiles,inferResumePosition,applyFilenamePosition,isSupportedResumeFile};
