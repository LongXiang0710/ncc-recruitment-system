const assert = require('assert');

let spaceOverviewActions = () => {};
try {
  const loaded = require('../web/features/overview_layout.js');
  if (typeof loaded.spaceOverviewActions === 'function') spaceOverviewActions = loaded.spaceOverviewActions;
} catch (_error) {
  // The first TDD run intentionally exercises the not-yet-implemented behavior.
}

const values = new Set();
const actionGroup = {
  classList: {
    add: name => values.add(name),
    contains: name => values.has(name),
  },
};

spaceOverviewActions(actionGroup);

assert.ok(
  actionGroup.classList.contains('overview-page-actions'),
  'the overview date and add button need their own spaced action group',
);

console.log('overview layout UI checks passed');
