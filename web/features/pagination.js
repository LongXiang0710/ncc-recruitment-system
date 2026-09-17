const PAGE_SIZE_STORAGE_KEY = 'recruitment-page-size';

function pageSizeOptions() {
  return [10, 20, 50, 100];
}

function normalizePageSize(value) {
  const size = Number(value);
  return pageSizeOptions().includes(size) ? size : 10;
}

function paginate(values, requestedPage, requestedPageSize) {
  const pageSize = normalizePageSize(requestedPageSize);
  const pages = Math.max(1, Math.ceil(values.length / pageSize));
  const page = normalizePageNumber(requestedPage, pages);
  const start = (page - 1) * pageSize;
  const rows = values.slice(start, start + pageSize).map((value, index) => ({value, number: start + index + 1}));
  return {page, pages, pageSize, rows};
}

function normalizePageNumber(value, pages) {
  const lastPage = Math.max(1, Math.trunc(Number(pages) || 1));
  const parsedPage = Number(value);
  const integerPage = Number.isFinite(parsedPage) ? Math.trunc(parsedPage) : 1;
  return Math.min(Math.max(1, integerPage || 1), lastPage);
}

function loadPageSize(storage) {
  try {
    return normalizePageSize(storage?.getItem(PAGE_SIZE_STORAGE_KEY));
  } catch (_error) {
    return 10;
  }
}

function savePageSize(storage, value) {
  const pageSize = normalizePageSize(value);
  try {
    storage?.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize));
  } catch (_error) {
    // Browsers may disable storage; pagination still works for this session.
  }
  return pageSize;
}

function paginationFooter(total, paging) {
  const totalRows = Math.max(0, Math.trunc(Number(total) || 0));
  const pageSize = normalizePageSize(paging?.pageSize);
  const pages = Math.max(1, Math.trunc(Number(paging?.pages) || 1));
  const page = Math.min(Math.max(1, Math.trunc(Number(paging?.page) || 1)), pages);
  const previousDisabled = page <= 1 ? 'disabled' : '';
  const nextDisabled = page >= pages ? 'disabled' : '';
  const options = pageSizeOptions().map(size=>`<option value="${size}" ${size===pageSize?'selected':''}>${size}</option>`).join('');
  return `<div class="pagination"><span>共 ${totalRows} 条记录，<label class="page-size-control">每页 <select id="page-size" class="page-size-select" aria-label="每页显示条数">${options}</select> 条</label></span><div class="pagination-navigation"><button class="secondary" id="first-page" ${previousDisabled}>首页</button><button class="secondary" id="prev" ${previousDisabled}>上一页</button><label class="page-jump-control">第 <input id="page-jump" class="page-jump-input" type="number" min="1" max="${pages}" value="${page}" aria-label="输入页码"> 页</label><button class="secondary" id="jump-page">跳转</button><span class="page-status">${page} / ${pages}</span><button class="secondary" id="next" ${nextDisabled}>下一页</button><button class="secondary" id="last-page" ${nextDisabled}>末页</button></div></div>`;
}

function bindPaginationControls(root, paging, handlers={}) {
  const page = normalizePageNumber(paging?.page, paging?.pages);
  const pages = Math.max(1, Math.trunc(Number(paging?.pages) || 1));
  const go = value => handlers.onPageChange?.(normalizePageNumber(value, pages));
  const find = selector => root.querySelector(selector);
  const pageInput = find('#page-jump');
  find('#page-size').onchange = event => handlers.onPageSizeChange?.(event.target.value);
  find('#first-page').onclick = () => go(1);
  find('#prev').onclick = () => go(page - 1);
  find('#next').onclick = () => go(page + 1);
  find('#last-page').onclick = () => go(pages);
  find('#jump-page').onclick = () => go(pageInput.value);
  pageInput.onkeydown = event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      go(pageInput.value);
    }
  };
}

const paginationTools = {pageSizeOptions, paginate, loadPageSize, savePageSize, paginationFooter, bindPaginationControls};

if (typeof module !== 'undefined' && module.exports) module.exports = paginationTools;
