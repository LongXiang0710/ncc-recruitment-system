// 列表勾选导出专用逻辑，和 Excel 生成代码保持解耦。
(function(root){
  function selectedIds(selection, records=[]) {
    const chosen=new Set(selection || []);
    return records.length?records.filter(row=>chosen.has(row.id)).map(row=>row.id):[...chosen];
  }
  function updateButton(button, selection) {
    if(!button)return;
    const count=selection?.size || 0;
    button.textContent=`导出所选（${count}）`;
    button.disabled=count===0;
  }
  function request(entity, selection, records=[]) {
    const ids=selectedIds(selection,records);
    return {path:`${entity}/export.xlsx`,options:{method:'POST',body:JSON.stringify({ids})}};
  }
  const api={selectedIds,updateButton,request};
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  root.SelectionExport=api;
})(typeof window!=='undefined'?window:globalThis);
