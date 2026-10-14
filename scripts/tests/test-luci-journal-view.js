// Run with node. Check text rendering, stale responses and read failures.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('package/custom/luci-app-systemd-journal/htdocs/luci-static/resources/view/status/systemd-journal.js', 'utf8');
const requests = [];
let polling;
function E(tag, attrs, children) {
	if (Array.isArray(attrs)) { children = attrs; attrs = {}; }
	attrs = attrs || {};
	children = children || [];
	return { tag, attrs, children, checked: !!attrs.checked, value: tag == 'select'
		? children.find(option => option.attrs.selected).attrs.value : '', scrollHeight: 50 };
}
const context = vm.createContext({
	E, _: s => s, view: { extend: obj => obj },
	rpc: { declare: () => (...args) => new Promise((resolve, reject) => requests.push({ args, resolve, reject })) },
	poll: { add: fn => { polling = fn; } },
	L: { bind: (fn, self) => fn.bind(self) }
});
const page = vm.runInContext('(function() { ' + source + ' })()', context);
async function flush() { for (let i = 0; i < 10; i++) await Promise.resolve(); }
async function main() {
	page.render();
	assert.equal(requests.length, 1);
	assert.deepEqual(Array.from(requests[0].args), [ 'current', '', 'all', 300 ]);
	page.unit.value = 'example.service';
	page.refresh(); // Queue new filters without overlapping queries.
	requests[0].resolve({ success: true, log: 'stale response' });
	await flush();
	assert.equal(requests.length, 2);
	assert.equal(page.output.value, '');
	const log = '<img src=x onerror=alert(1)>\nExample <script>hello</script>\n';
	requests[1].resolve({ success: true, log });
	await flush();
	assert.equal(page.output.value, log.trimEnd());
	assert.equal(page.output.attrs.readonly, true);
	assert.equal(page.downloadButton.disabled, false);
	page.search.value = 'EXAMPLE';
	page.display();
	assert.equal(page.output.value, 'Example <script>hello</script>');
	assert.equal(requests.length, 2); // Search is literal and local.
	page.search.value = '[';
	page.display();
	assert.equal(page.output.value, '');
	assert.equal(page.downloadButton.disabled, true);
	page.auto.checked = false;
	polling();
	assert.equal(requests.length, 2);
	page.refresh();
	requests[2].reject(new Error('RPC unavailable'));
	await flush();
	assert.equal(page.output.value, '');
	assert.equal(page.log, '');
	assert.equal(page.downloadButton.disabled, true);
	assert.match(page.status.textContent, /RPC unavailable/);
	assert.equal(page.refreshButton.disabled, false);
	assert.equal(page.handleSave, null);
	console.log('LuCI journal view: safe text, filters, polling, stale replies and failures passed');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
