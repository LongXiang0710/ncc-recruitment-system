// 所有二维码共用的展示卡片，便于统一调整样式或整体删除。
(function(root){
  const escapeHTML=value=>String(value ?? '').replace(/[&<>"']/g,character=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  function renderQrCard(options) {
    const download=options.downloadName?`<a class="secondary qr-download" download="${escapeHTML(options.downloadName)}" href="${escapeHTML(options.image)}">下载二维码图片</a>`:'';
    const label=`<strong class="qr-card-label">${escapeHTML(options.label)}</strong>`;
    const image=`<div class="qr-image-shell"><img src="${escapeHTML(options.image)}" alt="${escapeHTML(options.imageAlt || options.label)}"></div>`;
    const className=options.labelAbove?'qr-card qr-label-above':'qr-card';
    return `<article class="${className}">${options.labelAbove?label+image:image+label}<b class="qr-card-company">南京南化建设有限公司</b>${download}</article>`;
  }
  const api={renderQrCard};
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  root.QrCards=api;
})(typeof window!=='undefined'?window:globalThis);
