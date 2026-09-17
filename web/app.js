const app = document.querySelector('#app');
const dialog = document.querySelector('#editor');
const icons = {overview:'◫',schools:'▥',candidates:'♙',applications:'▤',interviews:'◎',employees:'▣',questions:'?',resume_documents:'▧'};
let schemas = {}, current = 'overview', records = [], search = '', page = 1, pageSize = paginationTools.loadPageSize(window.localStorage), requestVersion = 0;
let locations = {};
let selectedIds = new Set();
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const today = () => new Date().toLocaleDateString('sv-SE');
document.addEventListener('change',event=>{
  const input=event.target;
  if(input.matches('[data-native-date]')) {
    const display=input.closest('.date-control').querySelector('[data-date-format]');
    if(display.readOnly || display.disabled)return;
    display.value=input.value.replace('T',' ');
    display.dispatchEvent(new Event('input',{bubbles:true}));
    display.dispatchEvent(new Event('change',{bubbles:true}));
    return;
  }
  if(!input.matches('input[data-attachment]'))return;
  const status=input.closest('.attachment-field')?.querySelector('.attachment-selection');
  if(status)status.textContent=input.files[0]?'已选择：'+input.files[0].name:'';
});
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-open-date]');
  if(!button)return;
  event.preventDefault();
  const control=button.closest('.date-control'),display=control.querySelector('[data-date-format]'),picker=control.querySelector('[data-native-date]');
  if(display.readOnly || display.disabled)return;
  picker.value=display.value.replace(' ','T');
  picker.max=display.name==='birthdate'?today():display.max || '';
  try {if(picker.showPicker)picker.showPicker();else {picker.focus();picker.click();}}
  catch {picker.focus();picker.click();}
});
let toastTimer;
document.addEventListener('click',event=>{
  const link=event.target.closest('a[href^="/api/attachments/"]');
  if(!link || link.hasAttribute('download'))return;
  event.preventDefault();previewAttachment(link.getAttribute('href'),link.textContent.replace(/^下载：/,''));
});
async function previewAttachment(url,name) {
  const preview=document.createElement('dialog'),controller=new AbortController();let objectUrl;
  preview.className='attachment-preview-dialog';
  preview.innerHTML=`<div class="dialog-head"><h2>${escapeHTML(name)}</h2><button type="button" class="close" aria-label="关闭">×</button></div><div class="attachment-preview-body">正在加载预览…</div><div class="dialog-foot"><a class="secondary" href="${escapeHTML(url)}" download>下载附件</a><button type="button" class="secondary">关闭</button></div>`;
  tableLayout.floatDialogClose(preview);
  preview.querySelectorAll('button').forEach(button=>button.onclick=()=>preview.close());
  preview.addEventListener('close',()=>{controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl);preview.remove();},{once:true});
  document.body.append(preview);preview.showModal();
  try {
    const response=await fetch(url+'?preview=1',{signal:controller.signal});
    if(!response.ok){const error=await response.json();throw new Error(error.error || '预览失败');}
    const body=preview.querySelector('.attachment-preview-body');
    if(response.headers.get('Content-Type')?.includes('application/json')) {
      const result=await response.json();if(!preview.isConnected)return;
      body.textContent='';const note=document.createElement('p');note.className='hint';note.textContent=result.note;body.append(note);
      if(result.kind==='text'){const text=document.createElement('pre');text.textContent=result.text;body.append(text);}return;
    }
    const blob=await response.blob();if(!preview.isConnected)return;
    objectUrl=URL.createObjectURL(blob);body.textContent='';
    const viewer=document.createElement(blob.type==='application/pdf'?'iframe':'img');
    viewer.src=objectUrl;viewer.title=name;if(viewer.tagName==='IMG')viewer.alt=name;body.append(viewer);
  } catch(error){if(preview.isConnected)preview.querySelector('.attachment-preview-body').textContent=error.message;}
}
function toast(message) { const el = document.querySelector('#toast'); el.textContent = message; el.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 4000); }
async function api(path, options = {}) {
  const response = await fetch('/api/' + path, {...options, headers: {'Content-Type':'application/json', ...options.headers}});
  const data = await response.json();
  if (!response.ok) { if(response.status === 401 && path !== 'login' && !['/apply','/onboard','/resume-submit'].includes(location.pathname)) login(); throw new Error(data.error || '请求失败'); }
  return data;
}
function badge(value) {
  const kind = ['通过','已入职','已录用','已报到','已合作','已答复','已结束'].includes(value) ? 'green' : ['未通过','已放弃','取消入职','暂停合作'].includes(value) ? 'red' : '';
  return `<span class="badge ${kind}">${escapeHTML(value || '未设置')}</span>`;
}
function login() {
  requestVersion++;
  app.innerHTML = `<main class="auth"><section class="auth-brand"><div class="logo">N</div><span>南化建 / RECRUITMENT</span><h1>连接优秀人才<br>开启职业新程。</h1><p>南化建招聘管理系统</p><div class="brand-line"></div><small>院校资源 · 招聘管理 · 入职登记</small></section><section class="auth-card"><div class="eyebrow">招聘管理端</div><h2>登录工作台</h2><p class="muted">使用管理员或成员账号继续</p><form id="login-form"><label>账号<input name="username" value="admin" autocomplete="username" required></label><label>密码<input name="password" type="password" autocomplete="current-password" required></label><p id="login-error" class="error" role="alert"></p><button class="primary wide">登录</button></form><p class="hint">首次登录密码见服务器 data/initial-password.txt</p></section></main>`;
  document.querySelector('#login-form').onsubmit = async event => {
    event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
    try { await api('login', {method:'POST', body:JSON.stringify(Object.fromEntries(new FormData(event.target)))}); await boot(); }
    catch(error) { document.querySelector('#login-error').textContent = error.message; button.disabled = false; }
  };
}
async function boot() {
  try { schemas = await api('schema'); } catch(error) { login(); return; }
  const user=await api('me');
  app.innerHTML = `<div class="layout"><aside><a class="identity" href="/"><div class="logo">N</div><div>南化建<strong>招聘管理系统</strong></div></a><div class="nav-caption">招聘工作空间</div><nav><button data-nav="overview"><i>${icons.overview}</i>招聘总览</button>${Object.entries(schemas).sort(([a],[b])=>({resume_documents:0,candidates:1}[a]??2)-({resume_documents:0,candidates:1}[b]??2)).map(([key, spec]) => `<button data-nav="${key}"><i>${icons[key]}</i>${spec.title}</button>`).join('')}</nav><div class="aside-bottom"><span class="online-dot"></span>局域网协作<div class="hint">数据统一保存于服务端</div></div></aside><div class="workspace"><header><span>人才招聘 <span class="slash">/</span> 招聘管理</span><div class="header-actions"><button id="password" class="text-button">修改密码</button><button id="logout" class="avatar" title="退出登录" aria-label="退出登录">管</button></div></header><main id="content"></main><footer>南化建招聘管理系统 <span>让每一份人才档案有序可循</span></footer></div></div>`;
  document.querySelectorAll('[data-nav]').forEach(button => button.onclick = () => { current = button.dataset.nav; search = ''; page = 1; render(); });
  document.querySelector('#logout').onclick = () => accountMenu(user);
  document.querySelector('#password').onclick = changePassword;
  document.querySelector('#logout').textContent=user.role!=='member'?'管':'员';
  document.querySelector('#logout').title=(user.nickname || user.username)+' · 账号菜单';
  document.querySelector('#logout').setAttribute('aria-label','打开账号菜单');
  document.querySelector('#logout').setAttribute('aria-haspopup','dialog');
  const destination=new URLSearchParams(location.search);
  if(schemas[destination.get('module')]) current=destination.get('module');
  await render();
  const recordId=Number(destination.get('record'));
  if(recordId && current===destination.get('module')) {
    const row=records.find(item=>item.id===recordId);
    if(row) await edit(current,row); else toast('该记录不存在或已删除');
  }
}
async function render() {
  const version = ++requestVersion;
  document.querySelectorAll('[data-nav]').forEach(button => button.classList.toggle('active', button.dataset.nav === current));
  const content = document.querySelector('#content');
  content.innerHTML = '<div class="loading">正在加载数据…</div>';
  try {
    if(current === 'overview') {
      const stats = await api('stats'); if(version !== requestVersion) return;
      const card = (key, label, count) => `<button class="stat" data-open="${key}"><div><span>${label}</span><i>${icons[key]}</i></div><strong>${count}<small> ${key==='schools'?'所':'条'}</small></strong><p>查看${schemas[key].short} <b>↗</b></p></button>`;
      const recruitmentSection = kind => {
        const group=stats.recruitment[kind];
        const kindLabel=kind==='校园招聘'?'校园招聘':'社会招聘';
        const labels={resume_documents:'简历收集',candidates:'人才库',schools:'院校基础库',applications:'应聘登记',interviews:'面试情况'};
        return `<section class="recruitment-overview"><div class="panel-head"><h2>${kindLabel}</h2><span class="hint">${kind==='校园招聘'?'校园招聘资料与应聘、面试记录':'社会招聘简历与人才资料'}</span></div><div class="stats">${Object.entries(group.counts).map(([key,count])=>card(key,labels[key],count)).join('')}</div><section class="panel"><div class="panel-head"><h3>最新${kindLabel}人才登记</h3></div>${group.recent.length?`<div class="table-wrap"><table><thead><tr><th class="page-number">编号</th><th>姓名 / 院校</th><th>意向岗位</th></tr></thead><tbody>${group.recent.map((row,index)=>`<tr><td class="page-number">${index+1}</td><td><strong>${escapeHTML(row.name)}</strong><small>${escapeHTML(row.school_name)} · ${escapeHTML(row.major)}</small></td><td>${escapeHTML(row.position)}</td></tr>`).join('')}</tbody></table></div>`:`<div class="empty"><h3>暂无${kindLabel}人才登记</h3></div>`}</section></section>`;
      };
      content.innerHTML = `<div class="page-title"><div><h1>招聘总览</h1><p>按招聘类型查看简历、人才与招聘记录。</p></div><div id="overview-actions"><span class="date-chip">${today()}</span>${schemas.candidates?'<button class="primary" id="quick-new">新增</button>':''}</div></div>${recruitmentSection('校园招聘')}${recruitmentSection('社会招聘')}${schemas.employees?`<section class="recruitment-overview"><div class="panel-head"><h2>新员工登记</h2><span class="hint">统一统计新员工登记，不计入校园招聘或社会招聘</span></div><div class="stats">${card('employees','新员工信息登记',stats.counts.employees)}</div></section>`:''}`;
      overviewLayout.spaceOverviewActions(document.querySelector('#overview-actions'));
      if(document.querySelector('#quick-new')) document.querySelector('#quick-new').onclick = () => edit('candidates');
      content.querySelectorAll('[data-open]').forEach(button => button.onclick = () => {current = button.dataset.open; search = ''; page = 1; render();});
    } else {
      const entity = current;
      const rows = await api(entity); if(version !== requestVersion) return; records = rows; selectedIds.clear();
      const spec = schemas[entity];
      const featureUI=window.RecruitmentFeatures?.[entity] || {};
      const searchPlaceholder=spec.fields.some(field=>field.key==='archive_no')?'搜索档案编号、姓名、院校、岗位等…':'搜索姓名、院校、岗位等…';
      content.innerHTML = `<div class="page-title"><div><h1>${spec.title}</h1><p>${spec.description}</p></div><button class="primary" id="new-record">＋ 新增${spec.short}</button></div><section class="panel records"><div class="toolbar"><div class="toolbar-actions"><input id="search" type="search" placeholder="${searchPlaceholder}" aria-label="搜索记录" value="${escapeHTML(search)}"><button class="secondary" id="export">↓ 导出 CSV</button></div></div><div id="record-table"></div></section><p class="hint">应聘、面试与入职记录通过人员档案关联；招聘阶段在人才库中统一维护。</p>`;
      document.querySelector('#new-record').onclick = () => edit(entity);
      if(entity==='resume_documents') {
        const qrButton=document.createElement('button');qrButton.className='secondary';qrButton.textContent='生成二维码';qrButton.onclick=resumeCollectionQr;document.querySelector('.page-title').append(qrButton);
        document.querySelector('.records').nextElementSibling.textContent='上传文档或图片简历后可点击文件名预览或下载。待识别或失败记录可直接点击“识别”，成功后自动打开核对入库；“Dify 工作流”保留为手动备用。每份文件最大 50MB。';
        const workflow=document.createElement('button');workflow.className='secondary';workflow.textContent='Dify 工作流';workflow.onclick=openDifyWorkflow;document.querySelector('.page-title').append(workflow);
      }
      if(entity==='questions') {
        document.querySelector('.records').nextElementSibling.textContent='维护常见问题及通用回答话术，支持 Excel 导入导出。';
        document.querySelector('#search').placeholder='搜索问题、通用回答话术…';
      }
      if(entity==='employees') document.querySelector('.records').nextElementSibling.textContent='填写身份证后自动校验并计算出生日期和性别；身高单位为厘米，体重单位为公斤。';
      if(entity==='candidates') document.querySelector('.records').nextElementSibling.textContent='创建日期由服务器记录且不可修改；毕业时间取最高学历教育经历，仅校园招聘人才按毕业年份显示应届届别。简历附件支持上传、下载和替换。';
      if(entity==='applications') document.querySelector('.records').nextElementSibling.textContent='填写联系电话后自动匹配人才库并带入资料；未匹配时可独立登记。打开“查看 / 编辑”填写完整信息、上传附件或手写签名。';
      if(entity==='interviews') document.querySelector('.records').nextElementSibling.textContent='填写身份证后按相同号码带入应聘登记资料；多份登记取最近一份。面试时间精确到分钟，流程状态与面试结果分别维护。';
      document.querySelector('#search').oninput = event => {search = event.target.value; page = 1; renderTable();};
      SelectionExport.updateButton(document.querySelector('#export'),selectedIds);
      document.querySelector('#export').onclick = () => {const request=SelectionExport.request(entity,selectedIds,records);downloadExcel(request.path,spec.title+'.xlsx',request.options);};
      const actions=document.querySelector('.toolbar-actions');
      if(entity==='employees') document.querySelector('.page-title').insertAdjacentHTML('beforeend','<a class="secondary" href="/onboard" target="_blank" rel="noopener">新员工登记入口 ↗</a>');
      if(entity==='applications') document.querySelector('.page-title').insertAdjacentHTML('beforeend','<a class="secondary" href="/apply" target="_blank" rel="noopener">学生登记入口 ↗</a>');
      actions.insertAdjacentHTML('beforeend','<button class="secondary" id="refresh-records">↻ 刷新</button><button class="secondary" id="import-excel">↑ 导入 Excel</button><button class="secondary" id="print-qr" disabled>打印二维码（0）</button><button class="secondary delete-selected" id="delete-selected" disabled>删除所选（0）</button>');
      if(entity==='resume_documents'){actions.insertAdjacentHTML('beforeend','<button class="secondary" id="recognize-selected" disabled>识别（0）</button>');document.querySelector('#recognize-selected').onclick=()=>recognizeResumes([...selectedIds]);}
      const newButton=document.querySelector('#new-record');
      newButton.textContent='新增';
      actions.insertBefore(newButton,document.querySelector('#export'));
      actions.insertBefore(document.querySelector('#refresh-records'),document.querySelector('#export'));
      const toolbar=document.querySelector('.toolbar');
      tableLayout.arrangeListToolbar(toolbar,document.querySelector('#search'));
      if(featureUI.prepareToolbar)featureUI.prepareToolbar({toolbar,search:document.querySelector('#search'),applyFilters:()=>{selectedIds.clear();page=1;renderTable();}});
      if(entity==='resume_documents') {
        const pageActions=document.createElement('div');pageActions.className='page-title-actions';
        document.querySelectorAll('.page-title > button,.page-title > a').forEach(button=>pageActions.append(button));
        document.querySelector('.page-title').append(pageActions);
      }
      document.querySelector('#refresh-records').onclick=()=>render();
      document.querySelector('#import-excel').onclick=()=>featureUI.importRecords?featureUI.importRecords():importExcel(entity);
      document.querySelector('#print-qr').onclick=()=>printQr(entity,[...selectedIds]);
      document.querySelector('#delete-selected').onclick=()=>deleteSelected(entity,[...selectedIds]);
      renderTable();
    }
  } catch(error) { if(version === requestVersion) {content.innerHTML = '<div class="empty"><h3>加载失败</h3><p id="load-error"></p><button id="retry" class="secondary">重试</button></div>'; document.querySelector('#load-error').textContent = error.message; document.querySelector('#retry').onclick = render;} }
}
function renderTable() {
  const entity = current, spec = schemas[entity];
  const featureUI=window.RecruitmentFeatures?.[entity] || {};
  const visibleFields = ['candidates','applications','interviews','employees','resume_documents'].includes(entity)?tableLayout.listVisibleFields(spec.fields):{schools:['name','region','business_leader','province_city','level','ownership','is_985','is_211','is_double_first','ranking'],employees:['candidate_id','employee_no','department','start_date','status'],questions:['question','answer']}[entity].map(key=>spec.fields.find(field=>field.key===key));
  const secretKeys = new Set(spec.fields.filter(field=>field.type==='password').map(field=>field.key));
  let filtered = RecordSearch.filterRecords(records,search,secretKeys);
  if(featureUI.filterRecords)filtered=featureUI.filterRecords(filtered);
  const paging = paginationTools.paginate(filtered,page,pageSize); page=paging.page; pageSize=paging.pageSize;
  const pages = paging.pages, shown = paging.rows.map(item=>item.value);
  const hasListFilter=!!search || !!featureUI.hasActiveFilters?.();
  const tableContent = shown.length ? `<div class="table-wrap"><table><thead><tr><th class="id-col">编号</th>${visibleFields.map(field=>`<th>${field.label}</th>`).join('')}<th class="action-column">操作</th></tr></thead><tbody>${shown.map(row=>`<tr><td class="muted">${String(row.id).padStart(4,'0')}</td>${visibleFields.map(field=>`<td>${['status','cooperation'].includes(field.key)?badge(row[field.key]):escapeHTML(row[field.ref?field.key+'_label':field.key] || '—')}</td>`).join('')}<td class="row-actions"><button data-edit="${row.id}">查看 / 编辑</button><button data-delete="${row.id}" class="danger">删除</button></td></tr>`).join('')}</tbody></table></div>` : `<div class="empty"><div>${icons[entity]}</div><h3>${hasListFilter?'没有匹配的记录':'还没有'+spec.short+'记录'}</h3><p>${hasListFilter?'请调整搜索或筛选条件。':'点击右上角新增，开始建立招聘档案。'}</p></div>`;
  document.querySelector('#record-table').innerHTML = tableContent + paginationTools.paginationFooter(filtered.length,paging);
  document.querySelectorAll('[data-edit]').forEach(button=>button.onclick=()=>edit(entity,records.find(row=>row.id===Number(button.dataset.edit))));
  document.querySelectorAll('[data-delete]').forEach(button=>button.onclick=()=>remove(entity,Number(button.dataset.delete)));
  const table=document.querySelector('#record-table table');
  if(table) {
    table.querySelector('thead .id-col').remove();
    table.querySelector('thead tr').insertAdjacentHTML('afterbegin','<th class="page-number">编号</th><th><input type="checkbox" class="row-check" id="select-page" aria-label="选择本页全部记录"></th>');
    tableLayout.placeActionsAfterSelection(table.querySelector('thead tr'));
    table.querySelectorAll('tbody tr').forEach((tr,index)=>{
      const id=shown[index].id;
      if(entity==='resume_documents') {
        const actions=tr.querySelector('.row-actions');
        const resultButton=document.createElement('button');resultButton.textContent='识别结果入库';resultButton.onclick=()=>resumeRecognitionResult(shown[index]);actions.prepend(resultButton);
        const recognizeButton=document.createElement('button');recognizeButton.textContent='识别';recognizeButton.disabled=!canRecognizeResume(shown[index]);recognizeButton.title=recognizeButton.disabled?'只有待识别或失败简历可以识别':'自动上传该简历并运行 Dify';
        recognizeButton.onclick=async()=>{recognizeButton.disabled=true;recognizeButton.textContent='识别中…';try{Object.assign(shown[index],await recognizeOneResume(shown[index]));}catch(error){toast(error.message);recognizeButton.textContent='识别';recognizeButton.disabled=!canRecognizeResume(shown[index]);}};
        actions.prepend(recognizeButton);
      }
      visibleFields.forEach((field,column)=>{
        if(entity==='interviews' && field.key==='basic_situation') {
          const cell=tr.cells[column+1], button=document.createElement('button');
          button.className='text-button';button.textContent=shown[index].name || '查看登记';
          button.onclick=()=>showStudentRegistration(shown[index].identity_card);
          cell.replaceChildren(button);
        }
        if(field.type==='datetime-local') tr.cells[column+1].textContent=(shown[index][field.key] || '—').replace('T',' ');
        if(field.type==='attachment') {
          const cell=tr.cells[column+1];cell.textContent='—';
          if(shown[index][field.key+'_name']){const link=document.createElement('a');link.href='/api/attachments/'+encodeURIComponent(shown[index][field.key]);link.textContent=shown[index][field.key+'_name'];cell.textContent='';cell.append(link);}
        }
      });
      tr.cells[0].remove();
      tr.insertAdjacentHTML('afterbegin',`<td class="page-number">${paging.rows[index].number}</td><td><input class="row-check" type="checkbox" data-select="${id}" aria-label="选择记录${id}" ${selectedIds.has(id)?'checked':''}></td>`);
      tableLayout.placeActionsAfterSelection(tr);
      tr.querySelector('.row-actions').insertAdjacentHTML('beforeend',`<button data-qr="${id}">二维码</button>`);
    });
    const syncSelection=()=>{SelectionExport.updateButton(document.querySelector('#export'),selectedIds);const recognize=document.querySelector('#recognize-selected');if(recognize){recognize.textContent=`识别（${selectedIds.size}）`;recognize.disabled=!selectedIds.size;}const count=shown.filter(row=>selectedIds.has(row.id)).length;const selectAll=document.querySelector('#select-page');selectAll.checked=count===shown.length;selectAll.indeterminate=count>0 && count<shown.length;const button=document.querySelector('#print-qr');button.textContent=`打印二维码（${selectedIds.size}）`;button.disabled=!selectedIds.size;const removeButton=document.querySelector('#delete-selected');removeButton.textContent=`删除所选（${selectedIds.size}）`;removeButton.disabled=!selectedIds.size;};
    document.querySelectorAll('[data-select]').forEach(input=>input.onchange=()=>{const id=Number(input.dataset.select);input.checked?selectedIds.add(id):selectedIds.delete(id);syncSelection();});
    document.querySelector('#select-page').onchange=event=>{shown.forEach(row=>event.target.checked?selectedIds.add(row.id):selectedIds.delete(row.id));document.querySelectorAll('[data-select]').forEach(input=>input.checked=selectedIds.has(Number(input.dataset.select)));syncSelection();};
    document.querySelectorAll('[data-qr]').forEach(button=>button.onclick=()=>printQr(entity,[Number(button.dataset.qr)]));
    syncSelection();
  }
  SelectionExport.updateButton(document.querySelector('#export'),selectedIds);
  if(document.querySelector('#prev')) paginationTools.bindPaginationControls(document,paging,{
    onPageChange:value=>{page=value;renderTable();},
    onPageSizeChange:value=>{pageSize=paginationTools.savePageSize(window.localStorage,value);page=1;renderTable();},
  });
}
async function fieldsHTML(fields, row={}) {
  fields=fields.filter(field=>!field.hidden);
  const refs = {};
  await Promise.all([...new Set(fields.filter(f=>f.ref).map(f=>f.ref))].map(async ref=>{refs[ref]=await api(ref);}));
  return fields.map(field=>{
    const value = row[field.key] ?? '', required = field.required ? 'required' : '';
    const common = `name="${field.key}" id="f-${field.key}" ${required} ${field.type==='datetime-local'?`step="${field.precision==='minutes'?60:1}"`:''} ${field.readonly?'readonly aria-readonly="true"':''}`;
    let input;
    if(field.options || field.ref) {
      const choices = field.ref ? refs[field.ref].map(item=>[item.id,item.name+(item.phone?' · '+item.phone:'')]) : field.options.map(item=>[item,item]);
      input = `<select ${common}><option value="">请选择${field.label}</option>${choices.map(([key,label])=>`<option value="${escapeHTML(key)}" ${String(key)===String(value)?'selected':''}>${escapeHTML(label)}</option>`).join('')}</select>`;
    } else if(field.type==='attachment') input = `<span class="attachment-upload"><svg viewBox="0 0 32 32" aria-hidden="true" focusable="false"><path d="M5 21v6h22v-6M16 21V6m-5 5 5-5 5 5"/></svg><input id="${field.key}-file" data-attachment="${field.key}" type="file" aria-label="上传${field.label}" title="选择${field.label}" accept="${field.accept || '.pdf,.doc,.docx'}"></span><span class="attachment-selection hint" role="status"></span><span class="hint attachment-help">支持 ${field.accept || '.pdf,.doc,.docx'}，每份最大50MB，保存时上传。</span>${value?`<div class="attachment-existing"><a href="/api/attachments/${encodeURIComponent(value)}">下载：${escapeHTML(row[field.key+'_name'] || '已有附件')}</a><label><input type="checkbox" name="_remove_${field.key}"> 移除已有附件</label></div>`:''}${field.signature?'<div class="signature-pad"><span class="hint">也可在下方手写签名，保存后生成PNG附件</span><canvas id="signature-canvas" width="800" height="240" aria-label="本人手写签名区域"></canvas><button type="button" class="secondary" id="clear-signature">清空手写签名</button></div>':''}`;
    else if(['date','month','datetime-local'].includes(field.type)) {
      const format=field.type==='month'?'YYYY-MM':field.type==='date'?'YYYY-MM-DD':field.precision==='minutes'?'YYYY-MM-DD HH:mm':'YYYY-MM-DD HH:mm:ss';
      const pattern=field.type==='month'?'[0-9]{4}-[0-9]{2}':field.type==='date'?'[0-9]{4}-[0-9]{2}-[0-9]{2}':'[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}(:[0-9]{2})?';
      input=`<span class="date-control"><input ${common} type="text" value="${escapeHTML(String(value).replace('T',' '))}" placeholder="${format}" pattern="${pattern}" title="请按 ${format} 格式填写，或点击日历选择" maxlength="${format.length}" data-date-format="${field.type}"><button type="button" data-open-date aria-label="选择${field.label}" title="选择${field.label}"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/></svg></button><input type="${field.type}" class="native-date-picker" data-native-date tabindex="-1" aria-label="${field.label}选择器" ${field.type==='datetime-local'?`step="${field.precision==='minutes'?60:1}"`:''}></span>`;
    }
    else if(field.type==='textarea') input = `<textarea ${common} rows="3" maxlength="5000">${escapeHTML(value)}</textarea>`;
    else if(field.type==='password') input = `<div class="password-control"><input ${common} type="password" value="${escapeHTML(value)}" maxlength="300" autocomplete="off"><button type="button" class="text-button" data-toggle-password="f-${field.key}" aria-label="显示${field.label}" aria-pressed="false">显示</button></div>`;
    else input = `<input ${common} type="${field.type==='integer'?'number':field.type || 'text'}" value="${escapeHTML(value)}" ${field.type==='number'?`min="${field.min ?? 0}" max="${field.max ?? 100}" step="${field.step ?? 0.1}"`:field.type==='integer'?'min="1" step="1"':`maxlength="${field.maxLength || 300}"`} ${field.readonly?`placeholder="${field.key==='archive_no'?'保存后生成或按关联档案带入':field.key==='created_date'?'提交后自动记录，精确到秒':field.key==='province_city'?'根据所在省、所在市自动填写':'根据日期自动计算'}"`:''}>`;
    const section=field.section?`<h3 class="form-section">${field.section}</h3>`:'';
    if(field.type==='attachment')return `${section}<div class="full attachment-field"><label for="${field.key}-file">${field.label}</label>${input}</div>`;
    return `${section}<label class="${field.type==='textarea' || field.fullWidth?'full':''}" for="f-${field.key}">${field.label}${field.required?'<span class="required"> *</span>':''}${input}</label>`;
  }).join('');
}
function candidateEducationEditor(rows, requiredKeys=new Set()) {
  const section=document.createElement('section');section.className='education-editor full';
  let educationRows=rows?.length?rows:[{education:'',school_name:'',major:'',enrollment:'',graduation:''}];
  const rank={专科:1,本科:2,硕士:3,博士:4};
  section.highestGraduation=()=>educationRows.map((row,index)=>({row,index})).sort((left,right)=>(rank[right.row.education] || 0)-(rank[left.row.education] || 0) || left.index-right.index)[0]?.row.graduation || '';
  const notify=()=>section.dispatchEvent(new CustomEvent('educationchange'));
  const draw=()=>{
    section.innerHTML=`<div class="education-editor-head"><div><h3>教育经历</h3><span class="hint">每段学历分别填写起止年月；列表及其他表单联动时自动使用最高教育经历。</span></div><button type="button" class="secondary" data-add-education>＋ 添加教育经历</button></div><div class="education-list">${educationRows.map((row,index)=>window.RecruitmentCandidateEducation.renderRow(row,index,educationRows.length,requiredKeys)).join('')}</div>`;
    section.querySelector('[data-add-education]').onclick=()=>{if(educationRows.length>=10){toast('最多添加10条教育经历');return;}educationRows.push({education:'',school_name:'',major:'',enrollment:'',graduation:''});draw();notify();};
    section.querySelectorAll('[data-remove-education]').forEach((button,index)=>button.onclick=()=>{educationRows.splice(index,1);draw();notify();});
    section.querySelectorAll('[data-education-row]').forEach((item,index)=>item.querySelectorAll('[data-education]').forEach(input=>input.oninput=()=>{educationRows[index][input.dataset.education]=input.value;notify();}));
  };
  section.setRows=rows=>{educationRows=rows?.length?rows.map(row=>({...row})):[{education:'',school_name:'',major:'',enrollment:'',graduation:''}];draw();notify();};
  draw();return section;
}
async function edit(entity, row, draft=null, resumeSource=null) {
  try {
    const spec=schemas[entity];
    let formFields=spec.fields, formRow=row || draft || {date:today(),status:spec.fields.find(f=>f.key==='status')?.options?.[0]};
    const featureUI=window.RecruitmentFeatures?.[entity] || {};
    let educationRows=null;
    if(['candidates','applications','interviews','employees'].includes(entity)) {
      educationRows=formRow.education_experiences?.length?formRow.education_experiences:[{education:formRow.education || '',school_name:formRow.school_name || '',major:formRow.major || ''}];
    }
    if(featureUI.prepareEditor) ({formFields,formRow}=await featureUI.prepareEditor({spec,formFields,formRow,row}));
    const educationRequired=new Set(formFields.filter(field=>field.required && ['education','school_name','major'].includes(field.key)).map(field=>field.key));
    if(educationRows)formFields=formFields.filter(field=>!['education','school_name','major'].includes(field.key));
    const fields=await fieldsHTML(formFields,formRow);
    dialog.innerHTML=`<form id="record-form"><div class="dialog-head"><div><div class="eyebrow">${row?'更新档案':'新增档案'}</div><h2>${spec.title}</h2></div><button type="button" class="close" aria-label="关闭">×</button></div><div class="form-grid">${fields}</div><p class="error form-error" role="alert"></p><div class="dialog-foot"><span class="hint">带 * 为必填项</span><button type="button" class="secondary cancel">取消</button><button class="primary" type="submit">保存${spec.short}</button></div></form>`;
    tableLayout.floatEditorClose(dialog);
    if(['candidates','applications','interviews','employees'].includes(entity)) {
      const editor=candidateEducationEditor(educationRows,educationRequired);
      const gender=dialog.querySelector('[for=f-gender]');
      gender?gender.after(editor):dialog.querySelector('.form-grid').prepend(editor);
    }
    dialog.querySelector('.close').onclick=()=>dialog.close(); dialog.querySelector('.cancel').onclick=()=>dialog.close(); dialog.showModal();
    dialog.querySelectorAll('[data-toggle-password]').forEach(button=>button.onclick=()=>{const input=document.getElementById(button.dataset.togglePassword);const visible=input.type==='password';input.type=visible?'text':'password';button.textContent=visible?'隐藏':'显示';button.setAttribute('aria-label',`${visible?'隐藏':'显示'}就业网密码`);button.setAttribute('aria-pressed',String(visible));});
    if(resumeSource) {const file=dialog.querySelector('[data-attachment=resume]');file.closest('.attachment-upload').hidden=true;dialog.querySelector('[name=_remove_resume]')?.closest('label').remove();}
    PositionFields.bind(dialog.querySelector('form'));
    if(featureUI.afterEditor) await featureUI.afterEditor({form:dialog.querySelector('form'),row,formRow,spec});
    dialog.querySelector('form').onsubmit=async event=>{
      event.preventDefault(); const button=event.target.querySelector('[type=submit]'); button.disabled=true;
      try {let payload=await formPayload(event.target);if(featureUI.preparePayload)payload=await featureUI.preparePayload({form:event.target,payload,row,formRow,spec});await api(resumeSource?'resume_documents/'+resumeSource+'/candidate':entity+(row?'/'+row.id:''),{method:row?'PUT':'POST',body:JSON.stringify(payload)});dialog.close();toast('保存成功');render();}
      catch(error){dialog.querySelector('.form-error').textContent=error.message;button.disabled=false;}
    };
  }catch(error){toast(error.message);}
}
function remove(entity,id) {
  return deleteSelected(entity,[id]);
}

function editAccountPhone(user) {
  dialog.innerHTML=`<form><div class="dialog-head"><h2>我的电话号码</h2></div><div class="form-grid"><label class="full">电话号码<input name="phone" type="tel" maxlength="30" autocomplete="tel" value="${escapeHTML(user.phone || '')}"><span class="hint">可填写手机号或带区号的固定电话，留空则清除号码。</span></label></div><p class="error form-error" role="alert"></p><div class="dialog-foot"><button type="button" class="secondary cancel">取消</button><button type="submit" class="primary">保存</button></div></form>`;
  tableLayout.floatDialogClose(dialog);
  dialog.querySelector('.cancel').onclick=()=>dialog.close();
  dialog.querySelector('form').onsubmit=async event=>{
    event.preventDefault();const form=event.target,button=form.querySelector('[type=submit]');button.disabled=true;
    try {const result=await api('me/phone',{method:'PUT',body:JSON.stringify({phone:form.elements.phone.value})});user.phone=result.phone;dialog.close();toast('电话号码已保存');}
    catch(error){form.querySelector('.form-error').textContent=error.message;button.disabled=false;}
  };
}
function editNickname(user) {
  dialog.innerHTML=`<form><div class="dialog-head"><h2>修改昵称</h2></div><div class="form-grid"><label class="full">昵称<input name="nickname" maxlength="30" value="${escapeHTML(user.nickname || '')}" autocomplete="off"><span class="hint">最多30个字符，留空则显示登录账号。</span></label></div><p class="error form-error" role="alert"></p><div class="dialog-foot"><button type="button" class="secondary cancel">取消</button><button type="submit" class="primary">保存</button></div></form>`;
  tableLayout.floatDialogClose(dialog);
  dialog.querySelector('.cancel').onclick=()=>dialog.close();
  dialog.querySelector('form').onsubmit=async event=>{
    event.preventDefault();const form=event.target,button=form.querySelector('[type=submit]');button.disabled=true;
    try {
      const updated=await api('me',{method:'PUT',body:JSON.stringify({nickname:form.elements.nickname.value})});
      Object.assign(user,updated);document.querySelector('#logout').title=(user.nickname || user.username)+' · 账号菜单';
      dialog.close();toast('昵称已更新');
    } catch(error){form.querySelector('.form-error').textContent=error.message;button.disabled=false;}
  };
}
function accountMenu(user) {
  dialog.innerHTML=`<div class="dialog-head"><div><h2>${escapeHTML(user.nickname || user.username)}</h2><span class="hint">账号：${escapeHTML(user.username)} · ${user.role==='admin'?'主管理员':user.role==='manager'?'管理员':'成员'}</span></div><button type="button" class="close" aria-label="关闭">×</button></div><div class="form-grid"><button type="button" class="secondary full" id="account-nickname">修改昵称</button><button type="button" class="secondary full" id="account-members">查看成员</button><button type="button" class="secondary full" id="account-switch">切换账号</button><button type="button" class="secondary full" id="account-exit">退出登录</button></div>`;
  tableLayout.floatDialogClose(dialog);
  dialog.querySelector('.close').onclick=()=>dialog.close();dialog.showModal();
  dialog.querySelector('#account-nickname').onclick=()=>editNickname(user);
  const phoneButton=document.createElement('button');phoneButton.type='button';phoneButton.className='secondary full';phoneButton.textContent='我的电话号码';phoneButton.onclick=()=>editAccountPhone(user);dialog.querySelector('#account-nickname').after(phoneButton);
  dialog.querySelector('#account-members').onclick=()=>manageMembers(false);
  if(user.role!=='member') {
    const button=document.createElement('button');button.type='button';button.className='secondary full';button.textContent='创建成员';
    button.onclick=()=>manageMembers(true);dialog.querySelector('#account-members').before(button);
  }
  const leave=async switching=>{
    try {
      await api('logout',{method:'POST'});dialog.close();records=[];selectedIds.clear();login();
      if(switching){document.querySelector('.auth-card h2').textContent='切换账号';const username=document.querySelector('[name=username]');username.value='';username.focus();}
    } catch(error){toast(error.message);}
  };
  dialog.querySelector('#account-switch').onclick=()=>leave(true);
  dialog.querySelector('#account-exit').onclick=()=>leave(false);
}
async function manageMembers(canManage=false) {
  try {
    const [members, viewer]=await Promise.all([api('members'),api('me')]);
    dialog.innerHTML=`<div class="dialog-head"><h2>成员账号管理</h2><button type="button" class="close" aria-label="关闭">×</button></div><form id="member-form"><div class="form-grid"><label>成员账号<input name="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_\\-]{3,32}" autocomplete="off"><span class="hint">3至32位字母、数字、下划线或短横线</span></label><label>初始密码<input name="password" type="password" required minlength="10" maxlength="128" autocomplete="new-password"><span class="hint">10至128位，成员可自行修改</span></label><p class="hint full">成员可新增、查看、编辑、删除全部业务数据，并使用导入、导出和二维码功能。</p></div><p class="error form-error" role="alert"></p><div class="dialog-foot"><button class="primary" type="submit">创建成员</button></div></form><div class="form-grid"><h3 class="full">已创建成员（${members.length}）</h3>${members.length?members.map(member=>`<div class="full"><strong>${escapeHTML(member.nickname || member.username)}</strong><span class="hint"> · ${member.role==='manager'?'管理员':'成员'} · 账号：${escapeHTML(member.username)} · 创建于 ${escapeHTML(member.created_at.replace('T',' '))}</span></div>`).join(''):'<p class="hint full">暂无成员账号</p>'}</div>`;
    tableLayout.floatDialogClose(dialog);
    dialog.querySelector('#member-form .form-grid').insertAdjacentHTML('beforeend','<label>昵称<input name="nickname" maxlength="30" autocomplete="off" placeholder="选填，未填写则显示账号名"><span class="hint">最多30个字符</span></label><label>电话号码<input name="phone" type="tel" maxlength="30" autocomplete="off" placeholder="选填，成员也可登录后自行填写"></label>');
    if(!canManage){dialog.querySelector('#member-form').remove();dialog.querySelector('h2').textContent='查看成员';}
    else {dialog.querySelector('#member-form').nextElementSibling.remove();dialog.querySelector('h2').textContent='创建成员';}
    if(!canManage && viewer.role!=='member') {
      dialog.querySelectorAll('.form-grid > div.full').forEach((row,index)=>{
        const member=members[index];if(!member)return;
        if(viewer.role==='admin') {
          const roleButton=document.createElement('button');roleButton.type='button';roleButton.className='text-button';
          roleButton.textContent=member.role==='manager'?'取消管理员':'任命管理员';
          roleButton.onclick=async()=>{
            const promoting=member.role!=='manager';
            if(!confirm(`确认${promoting?'任命':'取消'}“${member.nickname || member.username}”的管理员权限？${promoting?'该账号将拥有除任命管理员以外的全部管理权限。':''}`))return;
            roleButton.disabled=true;
            try {await api('members/'+member.id+'/role',{method:'PUT',body:JSON.stringify({role:promoting?'manager':'member'})});toast('权限已更新');await manageMembers(false);}
            catch(error){toast(error.message);roleButton.disabled=false;}
          };
          row.append(roleButton);
          const passwordButton=document.createElement('button');passwordButton.type='button';passwordButton.className='text-button';passwordButton.textContent='重置密码';
          passwordButton.onclick=()=>{
            dialog.innerHTML=`<form><div class="dialog-head"><h2>重置成员密码</h2><button type="button" class="close" aria-label="关闭">×</button></div><div class="form-grid"><p class="hint full">成员：${escapeHTML(member.nickname || member.username)}（${escapeHTML(member.username)}）</p><label class="full">新密码（至少10位）<input name="password" type="password" minlength="10" maxlength="128" autocomplete="new-password" required></label><label class="full">再次输入新密码<input name="password_confirm" type="password" minlength="10" maxlength="128" autocomplete="new-password" required></label></div><p class="error form-error"></p><div class="dialog-foot"><button type="button" class="secondary cancel">取消</button><button class="primary" type="submit">保存新密码</button></div></form>`;
            tableLayout.floatDialogClose(dialog);
            const back=()=>manageMembers(false);
            dialog.querySelector('.close').onclick=back;dialog.querySelector('.cancel').onclick=back;
            dialog.querySelector('form').onsubmit=async event=>{
              event.preventDefault();const form=event.target,error=form.querySelector('.form-error'),button=form.querySelector('[type=submit]');
              if(form.elements.password.value!==form.elements.password_confirm.value){error.textContent='两次输入的新密码不一致';return;}
              button.disabled=true;
              try {await api('members/'+member.id+'/password',{method:'PUT',body:JSON.stringify({password:form.elements.password.value})});toast('成员密码已重置，原登录会话已失效');await manageMembers(false);}
              catch(resetError){error.textContent=resetError.message;button.disabled=false;}
            };
          };
          row.append(passwordButton);
        }
        const button=document.createElement('button');button.type='button';button.className='text-button danger';button.textContent='注销账号';
        button.onclick=async()=>{
          if(!confirm(`确认注销成员“${member.nickname || member.username}”（${member.username}）？该账号将无法登录，当前登录会话立即失效，业务数据保留。`))return;
          button.disabled=true;
          try {await api('members/'+member.id,{method:'DELETE'});toast('成员账号已注销');await manageMembers(false);}
          catch(error){toast(error.message);button.disabled=false;}
        };
        row.append(button);
      });
    }
    dialog.querySelector('.close').onclick=()=>dialog.close();if(!dialog.open)dialog.showModal();
    if(!canManage)return;
    dialog.querySelector('#member-form').onsubmit=async event=>{
      event.preventDefault();const form=event.target,button=form.querySelector('[type=submit]');button.disabled=true;
      try {await api('members',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});toast('成员账号已创建');dialog.close();}
      catch(error){form.querySelector('.form-error').textContent=error.message;button.disabled=false;}
    };
  } catch(error){toast(error.message);}
}
function changePassword() {
  dialog.innerHTML='<form><div class="dialog-head"><h2>修改管理员密码</h2></div><div class="form-grid"><label class="full">原密码<input name="old_password" type="password" autocomplete="current-password" required></label><label class="full">新密码（至少10位）<input name="password" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></label></div><p class="error form-error"></p><div class="dialog-foot"><button type="button" class="secondary cancel">取消</button><button class="primary" type="submit">保存并重新登录</button></div></form>';
  tableLayout.floatDialogClose(dialog);
  dialog.showModal();dialog.querySelector('.cancel').onclick=()=>dialog.close();dialog.querySelector('form').onsubmit=async event=>{event.preventDefault();try{await api('password',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});dialog.close();login();toast('密码已修改，请重新登录');}catch(error){dialog.querySelector('.form-error').textContent=error.message;}};
}
async function formPayload(form) {
  const payload=Object.fromEntries(new FormData(form));
  if(form.querySelector('.education-editor')) payload.education_experiences=[...form.querySelectorAll('[data-education-row]')].map(row=>Object.fromEntries([...row.querySelectorAll('[data-education]')].map(input=>[input.dataset.education,input.value])));
  if(form.dataset.syncAttachments==='true')payload._sync_attachments=true;
  for(const input of form.querySelectorAll('[data-attachment]')) {
    const key=input.dataset.attachment;
    payload['_remove_'+key]=payload['_remove_'+key]==='on';
    const file=input.files[0];
    if(!file)continue;
    const extension='.'+file.name.split('.').pop().toLowerCase();
    if(!input.accept.split(',').includes(extension) || file.size>50*1024*1024)throw new Error('附件类型不支持或超过50MB');
    const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('简历读取失败'));reader.readAsDataURL(file);});
    payload['_'+key+'_upload']={name:file.name,content};
  }
  const canvas=form.querySelector('#signature-canvas');
  if(canvas?.dataset.signed==='true')payload._signature_upload={name:'本人签名.png',content:canvas.toDataURL('image/png').split(',')[1]};
  return payload;
}
function bindSignature(form) {
  const canvas=form.querySelector('#signature-canvas');if(!canvas)return;
  const context=canvas.getContext('2d');let active=null;
  const clear=()=>{context.fillStyle='#ffffff';context.fillRect(0,0,canvas.width,canvas.height);canvas.dataset.signed='false';};
  const point=event=>{const rect=canvas.getBoundingClientRect();return [(event.clientX-rect.left)*canvas.width/rect.width,(event.clientY-rect.top)*canvas.height/rect.height];};
  clear();context.strokeStyle='#172943';context.lineWidth=3;context.lineCap='round';
  canvas.onpointerdown=event=>{event.preventDefault();active=event.pointerId;canvas.setPointerCapture(active);context.beginPath();context.moveTo(...point(event));};
  canvas.onpointermove=event=>{if(active!==event.pointerId)return;context.lineTo(...point(event));context.stroke();canvas.dataset.signed='true';form.querySelector('#signature-file').value='';};
  canvas.onpointerup=canvas.onpointercancel=()=>{active=null;};
  form.querySelector('#clear-signature').onclick=clear;
  form.querySelector('#signature-file').onchange=clear;
}
function fillLinkedAttachments(form, attachments, keys) {
  form.dataset.syncAttachments='true';
  keys.forEach(key=>{
    const input=form.querySelector(`[data-attachment="${key}"]`);if(!input)return;
    const field=input.closest('.attachment-field');
    field.querySelector('.attachment-existing')?.remove();
    const attachment=attachments[key];if(!attachment)return;
    const existing=document.createElement('div');existing.className='attachment-existing';
    existing.innerHTML=`<a href="/api/attachments/${encodeURIComponent(attachment.id)}">${escapeHTML(attachment.name)}</a><span class="hint">已联动带入，保存后生效</span><label><input type="checkbox" name="_remove_${key}"> 移除附件</label>`;
    input.closest('.attachment-upload').after(existing);
  });
}
function bindIdentityCard(form) {
  const identity=form.querySelector('[name=identity_card]'),birth=form.querySelector('[name=birthdate]'),gender=form.querySelector('[name=gender]');
  identity.maxLength=18;
  const hint=document.createElement('span');hint.className='hint';hint.setAttribute('role','status');identity.after(hint);
  let generated=null;
  const update=()=>{
    const number=identity.value.trim().toUpperCase();identity.value=number;
    let error='',birthday='',sex='';
    if(number) {
      if(!/^[1-9]\d{16}[\dX]$/.test(number))error='请输入18位身份证号码，末位可为X';
      else {const year=Number(number.slice(6,10)),month=Number(number.slice(10,12)),day=Number(number.slice(12,14));const date=new Date(year,month-1,day);birthday=`${number.slice(6,10)}-${number.slice(10,12)}-${number.slice(12,14)}`;if(date.getFullYear()!==year || date.getMonth()!==month-1 || date.getDate()!==day || birthday>today())error='身份证中的出生日期无效';else sex=Number(number[16])%2?'男':'女';}
    }
    if(number && !error) {
      if(number.slice(14,17)==='000')error='身份证顺序码不能为000';
      else {const weights=[7,9,10,5,8,4,2,1,6,3,7,9,10,5,8,4,2];const sum=weights.reduce((total,weight,index)=>total+Number(number[index])*weight,0);if(number[17]!=='10X98765432'[sum%11])error='身份证校验码不正确，请核对完整号码';}
    }
    identity.setCustomValidity(error);
    identity.setAttribute('aria-invalid',String(Boolean(error)));
    hint.className=error?'error':'hint';
    birth.readOnly=Boolean(number && !error);gender.disabled=Boolean(number && !error);
    if(number && !error){birth.value=birthday;gender.value=sex;generated={birthday,sex};hint.textContent='号码格式及校验码通过，已自动填写出生日期和性别。';}
    else {if(generated){if(birth.value===generated.birthday)birth.value='';if(gender.value===generated.sex)gender.value='';generated=null;}hint.textContent=error || '填写18位身份证后自动计算出生日期和性别。';}
    birth.dispatchEvent(new Event('input'));
  };
  identity.addEventListener('input',update);update();
}
if(location.pathname==='/apply') application(); else if(location.pathname==='/onboard') employeeApplication(); else if(location.pathname==='/resume-submit') publicResumeCollection(); else boot();
