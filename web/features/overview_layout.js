function spaceOverviewActions(actionGroup) {
  if (!actionGroup) return;
  actionGroup.classList.add('overview-page-actions');
}

const overviewLayout = {spaceOverviewActions};

if (typeof module !== 'undefined' && module.exports) module.exports = overviewLayout;
