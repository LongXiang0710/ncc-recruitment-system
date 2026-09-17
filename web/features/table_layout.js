function placeActionsAfterSelection(row) {
  const actionCell = row?.querySelector('.action-column, .row-actions');
  if (!actionCell) return;
  Object.assign(actionCell.style, {maxWidth: 'none', overflow: 'visible', textOverflow: 'clip'});
  const thirdCell = row.children[2] || null;
  if (actionCell !== thirdCell) row.insertBefore(actionCell, thirdCell);
}

function arrangeListToolbar(toolbar, search) {
  toolbar.querySelector('.record-summary')?.remove();
  const top = toolbar.ownerDocument.createElement('div');
  top.className = 'toolbar-top';
  top.append(search);
  toolbar.prepend(top);
}

function listVisibleFields(fields) {
  return fields.filter(field => !field.hidden && !field.listHidden);
}

function floatDialogClose(dialog) {
  if (!dialog) return;
  let close = dialog.querySelector('.floating-dialog-close') || dialog.querySelector('.close');
  const header = dialog.querySelector('.dialog-head');
  if (!close && header) {
    close = dialog.ownerDocument.createElement('button');
    close.type = 'button';
    close.classList.add('close');
    close.setAttribute('aria-label', '关闭');
    close.textContent = '×';
    header.append(close);
  }
  if (!close) return;

  let surface = Array.from(dialog.children).find(child => child.classList.contains('dialog-surface'));
  if (!surface) {
    surface = dialog.ownerDocument.createElement('div');
    surface.classList.add('dialog-surface');
    Array.from(dialog.children).forEach(child => surface.append(child));
    dialog.append(surface);
  }
  close.classList.add('floating-dialog-close');
  dialog.insertBefore(close, surface);
  dialog.classList.add('floating-close-dialog');
  if (close.onclick == null) close.onclick = () => dialog.close();
  if (!dialog._floatingCloseCleanupBound) {
    dialog._floatingCloseCleanupBound = true;
    dialog.addEventListener('close', () => {
      dialog.classList.remove('floating-close-dialog');
      dialog._floatingCloseCleanupBound = false;
    }, {once: true});
  }
}

function floatEditorClose(dialog) {
  floatDialogClose(dialog);
}

const tableLayout = {placeActionsAfterSelection, arrangeListToolbar, listVisibleFields, floatDialogClose, floatEditorClose};

if (typeof module !== 'undefined' && module.exports) module.exports = tableLayout;
