async function deleteSelected(entity,ids) {
  if(!ids.length || ids.length>1000){toast('请选择1至1000条记录');return;}
  let preview;
  try {preview=await api(entity+'/delete-preview',{method:'POST',body:JSON.stringify({ids})});}
  catch(error){toast(error.message);return;}
  dialog.innerHTML=`<div class="dialog-head"><h2>确认删除共 ${preview.count} 条记录？</h2></div><div class="import-body"><p>包含所选记录及其关联数据，删除后无法在页面恢复。</p><div class="delete-preview">${preview.items.map((row,index)=>`<p><label class="delete-choice"><input type="checkbox" data-delete-choice="${index}" checked ${row.entity===entity && ids.includes(row.id)?'disabled':''}>${escapeHTML(schemas[row.entity].short)} · ${escapeHTML(row.name)}${row.entity===entity && ids.includes(row.id)?'（所选记录）':''}</label></p>`).join('')}</div><p class="hint">关联记录默认勾选，可取消勾选保留。保留记录会解除与已删除记录的关联，已有内容和附件保留。</p><p class="error form-error" role="alert"></p></div><div class="dialog-foot"><button class="secondary cancel">取消</button><button class="primary delete-confirm">确认删除 ${preview.count} 条</button></div>`;
  tableLayout.floatDialogClose(dialog);
  const choices=()=>[...dialog.querySelectorAll('[data-delete-choice]:checked')].map(input=>preview.items[Number(input.dataset.deleteChoice)]);
  const updateCount=()=>{const count=choices().length;dialog.querySelector('h2').textContent=`确认删除共 ${count} 条记录？`;dialog.querySelector('.delete-confirm').textContent=`确认删除 ${count} 条`;};
  dialog.querySelectorAll('[data-delete-choice]').forEach(input=>input.onchange=updateCount);
  let busy=false;
  dialog.querySelector('.close').onclick=()=>{if(!busy)dialog.close();};
  const cancel=event=>{if(busy)event.preventDefault();};
  dialog.addEventListener('cancel',cancel);
  dialog.addEventListener('close',()=>dialog.removeEventListener('cancel',cancel),{once:true});
  dialog.querySelector('.cancel').onclick=()=>dialog.close();
  dialog.querySelector('.delete-confirm').onclick=async()=>{
    if(busy)return;busy=true;dialog.querySelectorAll('button').forEach(button=>button.disabled=true);
    try {const result=await api(entity+'/batch-delete',{method:'POST',body:JSON.stringify({ids,expected:preview.items,selected:choices().map(row=>({entity:row.entity,id:row.id}))})});dialog.close();toast(`已删除 ${result.count} 条记录`);await render();}
    catch(error){dialog.querySelector('.form-error').textContent=error.message;busy=false;dialog.querySelectorAll('button').forEach(button=>button.disabled=false);}
  };
  dialog.showModal();
}
async function downloadExcel(path,filename,options={}) {
  try {
    const response=await fetch('/api/'+path,{...options,headers:{'Content-Type':'application/json',...(options.headers || {})}});
    if(!response.ok) {const error=await response.json();throw new Error(error.error || '下载失败');}
    const url=URL.createObjectURL(await response.blob());
    const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(error){toast(error.message);}
}
function importExcel(entity) {
  const spec=schemas[entity];
  let filePayload=null, preview=null, busy=false;
  dialog.classList.add('wide-dialog');
  dialog.innerHTML=`<div class="dialog-head"><div><div class="eyebrow">EXCEL IMPORT</div><h2>导入${spec.short}</h2></div><button class="close" aria-label="关闭">×</button></div><div class="import-body"><p class="hint">支持 .xlsx、.xls，最大8MB，每次最多1000条。识别表头后可调整列对应关系。仅新增记录，不覆盖现有档案；全部校验通过才可导入。</p><div class="import-controls"><label>选择Excel文件<input type="file" id="excel-file" accept=".xlsx,.xls"></label><label>工作表<select id="excel-sheet" disabled><option>请先选择文件</option></select></label><button class="secondary" id="template">下载导入模板</button></div><p class="hint">关联人员可填写档案编号、唯一姓名或手机号，关联院校可填写档案编号或唯一学校名称。建议先导入院校及人才库。</p><div id="import-result"></div><p class="error" id="import-error" role="alert"></p></div><div class="dialog-foot"><button class="secondary" id="recognize" disabled>识别 / 重新校验</button><button class="primary" id="confirm-import" disabled>确认导入</button></div>`;
  tableLayout.floatDialogClose(dialog);
  const close=()=>{if(!busy)dialog.close();};
  dialog.querySelector('.close').onclick=close;
  dialog.addEventListener('close',()=>dialog.classList.remove('wide-dialog'),{once:true});
  dialog.showModal();
  document.querySelector('#template').onclick=()=>downloadExcel(entity+'/template.xlsx',spec.title+'-导入模板.xlsx');
  const setBusy=value=>{busy=value;document.querySelector('#excel-file').disabled=value;document.querySelector('#excel-sheet').disabled=value || !preview;document.querySelector('#recognize').disabled=value || !filePayload;document.querySelector('#confirm-import').disabled=value || !preview?.token;dialog.querySelector('.close').disabled=value;};
  const recognize=async(useMapping=false)=>{
    if(!filePayload || busy)return;
    const mapping=useMapping?[...dialog.querySelectorAll('[data-column]')].map(select=>select.value):undefined;
    setBusy(true);document.querySelector('#import-error').textContent='';document.querySelector('#import-result').textContent='正在识别并校验，请稍候…';
    try {
      const sheet=preview?document.querySelector('#excel-sheet').value:undefined;
      preview=await api(entity+'/import-preview',{method:'POST',body:JSON.stringify({...filePayload,sheet,mapping})});
      document.querySelector('#excel-sheet').innerHTML=preview.sheets.map(name=>`<option ${name===preview.sheet?'selected':''}>${escapeHTML(name)}</option>`).join('');
      const fields=spec.fields.filter(field=>!field.readonly && !field.hidden && field.type!=='attachment');
      document.querySelector('#import-result').innerHTML=`<h3>识别到 ${preview.total} 条记录${preview.errors.length?'，'+preview.errors.length+' 处问题':''}</h3><p class="hint">表头位于第 ${preview.header_row} 行。调整对应字段后请重新校验；预览最多显示20条。</p><div class="column-mappings">${preview.headers.map((header,index)=>`<label>${escapeHTML(header || '空列'+(index+1))}<select data-column="${index}"><option value="">忽略此列</option>${fields.map(field=>`<option value="${field.key}" ${preview.mapping[index]===field.key?'selected':''}>${field.label}</option>`).join('')}</select></label>`).join('')}</div>${preview.errors.length?`<div class="import-errors" role="alert">${preview.errors.map(error=>`<p>第 ${error.line} 行：${escapeHTML(error.error)}</p>`).join('')}</div>`:'<p class="import-ok">校验通过，确认后写入数据库。</p>'}<div class="table-wrap"><table><thead><tr><th>Excel行号</th>${fields.filter(field=>preview.mapping.includes(field.key)).map(field=>`<th>${field.label}</th>`).join('')}</tr></thead><tbody>${preview.rows.map(row=>`<tr><td>${row.line}</td>${fields.filter(field=>preview.mapping.includes(field.key)).map(field=>`<td>${escapeHTML(row.values[field.key] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
      dialog.querySelectorAll('[data-column]').forEach(select=>select.onchange=()=>{preview.token=null;document.querySelector('#confirm-import').disabled=true;});
    }catch(error){preview=null;document.querySelector('#import-result').textContent='';document.querySelector('#import-error').textContent=error.message;}
    finally{setBusy(false);}
  };
  document.querySelector('#excel-file').onchange=async event=>{
    const file=event.target.files[0];preview=null;filePayload=null;document.querySelector('#confirm-import').disabled=true;
    if(!file)return;
    if(file.size>8*1024*1024){document.querySelector('#import-error').textContent='文件超过8MB，请拆分后重试';return;}
    setBusy(true);
    try {const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('读取文件失败'));reader.readAsDataURL(file);});filePayload={filename:file.name,file:encoded};}
    catch(error){document.querySelector('#import-error').textContent=error.message;}
    finally{setBusy(false);}
    if(filePayload)await recognize();
  };
  document.querySelector('#excel-sheet').onchange=()=>recognize();
  document.querySelector('#recognize').onclick=()=>recognize(Boolean(preview));
  document.querySelector('#confirm-import').onclick=async()=>{
    if(!preview?.token || busy)return;setBusy(true);
    try {const result=await api(entity+'/import-commit',{method:'POST',body:JSON.stringify({token:preview.token})});dialog.close();toast(`已导入 ${result.count} 条记录`);await render();}
    catch(error){preview.token=null;document.querySelector('#import-error').textContent=error.message;setBusy(false);}
  };
  const cancelWhileBusy=event=>{if(busy)event.preventDefault();};
  dialog.addEventListener('cancel',cancelWhileBusy);
  dialog.addEventListener('close',()=>dialog.removeEventListener('cancel',cancelWhileBusy),{once:true});
}
async function printQr(entity,ids) {
  if(!ids.length || ids.length>100){toast('请选择1至100条记录');return;}
  try {
    const result=await api(entity+'/qr-print',{method:'POST',body:JSON.stringify({ids})});
    dialog.classList.add('wide-dialog','qr-dialog');
    dialog.innerHTML=`<div class="dialog-head"><h2>打印二维码</h2><button class="close" aria-label="关闭">×</button></div><div class="qr-grid">${result.items.map(item=>QrCards.renderQrCard({label:item.title,image:item.image,imageAlt:'记录'+item.id+'二维码'})).join('')}</div><div class="dialog-foot"><button class="secondary cancel">关闭</button><button class="primary" id="send-print">打印 / 保存为 PDF</button></div>`;
    tableLayout.floatDialogClose(dialog);
    const cleanup=()=>{dialog.classList.remove('wide-dialog','qr-dialog');document.body.classList.remove('printing-qr');};
    dialog.addEventListener('close',cleanup,{once:true});dialog.querySelector('.close').onclick=()=>dialog.close();dialog.querySelector('.cancel').onclick=()=>dialog.close();dialog.showModal();
    document.querySelector('#send-print').onclick=async()=>{
      try {await Promise.all([...dialog.querySelectorAll('img')].map(img=>img.decode()));document.body.classList.add('printing-qr');window.print();}catch(error){toast('二维码图片未加载完成，请重试');}finally{document.body.classList.remove('printing-qr');}
    };
  }catch(error){toast(error.message);}
}
