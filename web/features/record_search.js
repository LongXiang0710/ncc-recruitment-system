// 所有数据列表共用的搜索匹配规则。
function filterRecords(records,query,excludedKeys=new Set()) {
  const keyword=String(query || '').trim().toLowerCase();
  if(!keyword)return records;
  return records.filter(row=>Object.entries(row)
    .filter(([key])=>!excludedKeys.has(key))
    .some(([,value])=>String(value ?? '').toLowerCase().includes(keyword)));
}

const RecordSearch={filterRecords};
if(typeof window!=='undefined')window.RecordSearch=RecordSearch;
if(typeof module!=='undefined' && module.exports)module.exports=RecordSearch;
