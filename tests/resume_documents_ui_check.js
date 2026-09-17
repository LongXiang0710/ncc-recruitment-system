const assert = require('assert');
const ui = require('../web/features/resume_documents.js');

assert.strictEqual(ui.inferResumePosition('张坤洋_26岁_电气工程师_南京_智联简历_41274.pdf'),'电气工程师');
assert.strictEqual(ui.inferResumePosition('陈艺平_25岁_管道安装工程师福建漳州_智联招聘.pdf'),'管道安装工程师');
assert.strictEqual(ui.inferResumePosition('李四-安全员-社会招聘.pdf'),'安全员');
assert.strictEqual(ui.inferResumePosition('张三个人简历.pdf'),'');

const autoPosition={value:'',dataset:{}};
ui.applyFilenamePosition(autoPosition,'王五_28岁_施工员_南京.pdf');
assert.strictEqual(autoPosition.value,'施工员');
ui.applyFilenamePosition(autoPosition,'王五_28岁_项目经理_南京.pdf');
assert.strictEqual(autoPosition.value,'项目经理','a prior automatic value should refresh for a newly selected file');
autoPosition.value='手工填写岗位';
ui.applyFilenamePosition(autoPosition,'王五_28岁_安全员_南京.pdf');
assert.strictEqual(autoPosition.value,'手工填写岗位','a manually edited position must not be overwritten');

assert.strictEqual(typeof ui.prepareResumeToolbar,'function');
let exportRemoved=false;
const exportButton={remove:()=>{exportRemoved=true;}};
const importButton={textContent:'↑ 导入 Excel'};
const toolbar={querySelector:selector=>selector==='#export'?exportButton:selector==='#import-excel'?importButton:null};
const searchInput={placeholder:'搜索简历名称、备注…'};
ui.prepareResumeToolbar(toolbar,searchInput);
assert.strictEqual(exportRemoved,true,'resume collection should remove its export button');
assert.strictEqual(searchInput.placeholder,'搜索档案编号、简历名称…');
assert.strictEqual(importButton.textContent,'↑ 批量导入简历');

assert.strictEqual(typeof ui.filterResumeRecords,'function','resume filter behavior must be available');
assert.strictEqual(typeof ui.hasActiveResumeFilters,'function','active resume filters must be detectable');
assert.strictEqual(ui.hasActiveResumeFilters({}),false);
assert.strictEqual(ui.hasActiveResumeFilters({recruitment_type:'校园招聘'}),true);
const filterRecords=[
  {id:1,created_at:'2026-09-14T00:00:00',recruitment_type:'社会招聘',channel:'智联招聘'},
  {id:2,created_at:'2026-09-14T23:59:59',recruitment_type:'校园招聘',channel:'校园平台'},
  {id:3,created_at:'2026-09-15T00:00:00',recruitment_type:'社会招聘',channel:'智联招聘'},
  {id:4,created_at:'',recruitment_type:'社会招聘',channel:'boss直聘'}
];
assert.deepStrictEqual(
  ui.filterResumeRecords(filterRecords,{start_date:'2026-09-14',end_date:'2026-09-14'}).map(row=>row.id),
  [1,2],
  'the end date must include the entire selected day'
);
assert.deepStrictEqual(
  ui.filterResumeRecords(filterRecords,{recruitment_type:'社会招聘',channel:'智联招聘'}).map(row=>row.id),
  [1,3],
  'recruitment type and channel filters must both apply'
);
assert.deepStrictEqual(
  ui.filterResumeRecords(filterRecords,{}).map(row=>row.id),
  [1,2,3,4],
  'empty filters must preserve every record and its order'
);

const supportedExtensions=['txt','md','mdx','markdown','pdf','html','xlsx','xls','doc','docx','csv','eml','msg','pptx','ppt','xml','epub','jpg','jpeg','png','gif','webp','svg'];
for(const extension of supportedExtensions)assert.strictEqual(ui.isSupportedResumeFile({name:`简历.${extension}`}),true,extension);
assert.strictEqual(ui.isSupportedResumeFile({name:'简历.exe'}),false);

const firstPdf={name:'第一份.pdf',size:1024,lastModified:10};
const secondPdf={name:'第二份.pdf',size:2048,lastModified:20};
const replacementWithSameName={name:'第一份.pdf',size:4096,lastModified:30};
const mergedFiles=ui.mergeResumeFiles(
  [firstPdf],
  [secondPdf,{...firstPdf},replacementWithSameName]
);
assert.deepStrictEqual(
  mergedFiles,
  [firstPdf,secondPdf,replacementWithSameName],
  'later file selections should append while exact duplicate files are ignored'
);

const fields=[{key:'name',label:'姓名'},{key:'phone',label:'联系方式'}];
const source={recruitment_type:'社会招聘',channel:'其他',channel_detail:'行业推荐',resume:'file-1',resume_name:'resume.pdf'};
const recognized={
  name:'张三',phone:'13900000000',unknown:'丢弃',
  education_experiences:[{education:'本科',school_name:'测试大学',major:'工程',enrollment:'2020-09',graduation:'2024-06'}],
  work_experiences:[{organization:'测试公司',position:'工程师',start_date:'2024-07',end_date:'',description:''}],
  project_experiences:[{project_name:'测试项目',role:'负责人',start_date:'2024-07',end_date:'',description:''}]
};
const draft=ui.recognitionDraft(recognized,fields,source);
assert.strictEqual(draft.name,'张三');
assert.ok(!('unknown' in draft));
assert.deepStrictEqual(draft.education_experiences,recognized.education_experiences);
assert.deepStrictEqual(draft.work_experiences,recognized.work_experiences);
assert.deepStrictEqual(draft.project_experiences,recognized.project_experiences);
assert.strictEqual(draft.channel_detail,'行业推荐');
assert.strictEqual(draft.resume,'file-1');

const campus=ui.recognitionDraft(recognized,fields,{...source,recruitment_type:'校园招聘'});
assert.ok(!('project_experiences' in campus));
assert.strictEqual(ui.canRecognizeResume({status:'待识别'}),true);
assert.strictEqual(ui.canRecognizeResume({status:'失败'}),true);
assert.strictEqual(ui.canRecognizeResume({status:'已识别'}),false);
assert.strictEqual(ui.canRecognizeResume({status:'已入库'}),false);

(async()=>{
  const calls=[];
  let reviewed=null;
  let successfulRefreshes=0;
  const pending={id:17,name:'张三简历.pdf',status:'待识别'};
  const result=await ui.recognizeOneResume(pending,{
    request:async(path,options)=>{
      calls.push([path,options]);
      if(path==='recognition-config')return {configured:true,message:''};
      return {status:'已识别'};
    },
    review:async source=>{reviewed=source;},
    refresh:async()=>{successfulRefreshes++;}
  });
  assert.deepStrictEqual(calls,[
    ['recognition-config',undefined],
    ['resume_documents/17/recognize',{method:'POST'}]
  ]);
  assert.strictEqual(result.status,'已识别');
  assert.strictEqual(reviewed.id,17);
  assert.strictEqual(reviewed.status,'已识别');
  assert.strictEqual(successfulRefreshes,1);

  reviewed=null;
  const retried=await ui.recognizeOneResume({id:18,name:'失败简历.pdf',status:'失败'},{
    request:async path=>path==='recognition-config'?{configured:true,message:''}:{status:'已识别'},
    review:async source=>{reviewed=source;},
    refresh:async()=>{successfulRefreshes++;}
  });
  assert.strictEqual(retried.status,'已识别');
  assert.strictEqual(reviewed.id,18);
  assert.strictEqual(successfulRefreshes,2);

  let refreshed=0;
  await assert.rejects(()=>ui.recognizeOneResume(pending,{
    request:async path=>{
      if(path==='recognition-config')return {configured:true,message:''};
      throw new Error('识别失败');
    },
    review:async()=>{throw new Error('失败时不应打开核对');},
    refresh:async()=>{refreshed++;}
  }),/识别失败/);
  assert.strictEqual(refreshed,1);

  const uploaded=[];
  const progress=[];
  const batch=await ui.importResumeBatch([
    {name:'校园简历.pdf',size:1024},
    {name:'重复简历.pdf',size:2048},
    {name:'社会简历.pdf',size:4096}
  ],{recruitment_type:'社会招聘',channel:'智联招聘',channel_detail:''},{
    encodeFile:async file=>'encoded-'+file.name,
    request:async(path,options)=>{
      const payload=JSON.parse(options.body);
      uploaded.push([path,payload]);
      if(payload.name==='重复简历.pdf')throw new Error('该 PDF 已存在');
      return {id:uploaded.length};
    },
    onProgress:item=>progress.push(item)
  });
  assert.deepStrictEqual(uploaded.map(item=>item[0]),['resume_documents','resume_documents','resume_documents']);
  assert.deepStrictEqual(uploaded[0][1],{
    name:'校园简历.pdf',position:'',recruitment_type:'社会招聘',channel:'智联招聘',channel_detail:'',
    _resume_upload:{name:'校园简历.pdf',content:'encoded-校园简历.pdf'}
  });
  assert.strictEqual(batch.succeeded,2);
  assert.strictEqual(batch.failed,1);
  assert.deepStrictEqual(batch.items.map(item=>item.status),['成功','失败','成功']);
  assert.match(batch.items[1].error,/已存在/);
  assert.strictEqual(progress.length,3);

  const publicCalls=[];
  const publicBatch=await ui.importResumeBatch(
    [{name:'公开简历.pdf',size:300,lastModified:50}],
    {recruitment_type:'校园招聘',channel:'校园平台',channel_detail:''},
    {
      encodeFile:async()=>'public-pdf',
      requestPath:'public/resumes/campus',
      request:async(path,options)=>{publicCalls.push([path,JSON.parse(options.body)]);return {ok:true};}
    }
  );
  assert.strictEqual(publicBatch.succeeded,1);
  assert.deepStrictEqual(publicCalls,[['public/resumes/campus',{
    name:'公开简历.pdf',position:'',recruitment_type:'校园招聘',channel:'校园平台',channel_detail:'',
    _resume_upload:{name:'公开简历.pdf',content:'public-pdf'}
  }]]);

  const invalidBatch=await ui.importResumeBatch([
    {name:'错误格式.exe',size:100},
    {name:'超大简历.pdf',size:50*1024*1024+1},
    {name:'读取失败.pdf',size:100}
  ],{recruitment_type:'校园招聘',channel:'校园平台',channel_detail:''},{
    encodeFile:async()=>{throw new Error('读取文件失败');},
    request:async()=>{throw new Error('不应提交无效文件');}
  });
  assert.strictEqual(invalidBatch.succeeded,0);
  assert.strictEqual(invalidBatch.failed,3);
  assert.match(invalidBatch.items[0].error,/文件格式不支持/);
  assert.match(invalidBatch.items[1].error,/超过50MB/);
  assert.match(invalidBatch.items[2].error,/读取文件失败/);

  await assert.rejects(()=>ui.importResumeBatch([],{
    recruitment_type:'',channel:'',channel_detail:''
  }),/请选择招聘类型/);
  await assert.rejects(()=>ui.importResumeBatch([{name:'简历.pdf',size:1}],{
    recruitment_type:'社会招聘',channel:'其他',channel_detail:''
  }),/请填写其他渠道详情/);
})().catch(error=>{console.error(error);process.exitCode=1;});
