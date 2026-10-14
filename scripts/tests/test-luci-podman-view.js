// Exercise account switching, read-only controls and literal text rendering.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let writable = true, pendingList, requests = [];
function E(tag, attrs, children) {
	return { tag, attrs: attrs || {}, children: children == null ? [] : [].concat(children),
		appendChild(node) { this.children.push(node); },
		replaceChildren(...nodes) { this.children = nodes; } };
}
function descendants(node) {
	return [node, ...(node && node.children || []).flatMap(descendants)];
}
const context = vm.createContext({
	E, _: s => s, view: { extend: obj => obj }, baseclass: { extend: obj => obj },
	window: { localStorage: { getItem: () => 'alice', setItem: () => {} }, setTimeout },
	poll: { add: () => {} },
	ui: { createHandlerFn: (_, fn) => fn, showModal: () => {}, hideModal: () => {} },
	L: { bind: (fn, self, ...args) => fn.bind(self, ...args), hasViewPermission: () => writable, url: s => s },
	rpc: { declare: spec => (...args) => {
		requests.push([spec.method, ...args]);
		if (spec.method == 'list') return new Promise(resolve => { pendingList = resolve; });
		return Promise.resolve({ success: true });
	} }
});
vm.runInContext('String.prototype.format = function(...args) { let i = 0; return this.replace(/%s/g, () => args[i++]); };', context);
const source = fs.readFileSync('package/custom/luci-app-podman/htdocs/luci-static/resources/podman/manager.js', 'utf8');
const manager = vm.runInContext('(function() {' + source + '})()', context);
const view = manager.makeView('containers', 'Containers');
view.resource = 'containers';
view.title = 'Containers';
const hostile = '<img src=x onerror=alert(1)>';
const row = { Id: 'abc', Names: [hostile], Image: 'alpine', State: 'running', Ports: [] };

(async () => {
	writable = false;
	let table = view.table([row]);
	assert.deepEqual(descendants(table).filter(n => n && n.tag == 'button').map(n => n.children[0]), ['Inspect', 'Logs']);
	assert(descendants(table).includes(hostile));
	await assert.rejects(view.execute('container', 'start', 'abc', {}), /Permission denied/);
	writable = true;
	assert(descendants(view.table([row])).some(n => n && n.tag == 'button' && n.children[0] == 'Remove'));
	view.user = 'bob';
	await assert.rejects(view.execute('container', 'rm', 'abc', {}, 'alice'), /Account changed/);
	assert.equal(requests.length, 0);
	let root = view.render({ success: true, accounts: [ { user: 'alice', uid: 1000, allowed: true }, { user: 'bob', uid: 1001, allowed: true } ] });
	let opts = descendants(root).filter(n => n && n.tag == 'option');
	assert.equal(opts[0].attrs.selected, true);
	assert.equal(opts[1].attrs.selected, null);
	let selector = descendants(root).find(n => n && n.tag == 'select');
	selector.attrs.change({ target: { value: 'bob' } });
	assert.equal(view.user, 'bob');
	assert.equal(view.body.children[0].children[0], 'Loading…');
	pendingList({ success: true, data: [row] });
	await new Promise(resolve => setImmediate(resolve));
	assert.equal(requests[requests.length - 1][1], 'bob');
	assert.equal(view.body.children[0].children[0], 'Loading…'); // alice's late reply was discarded
	pendingList({ success: true, data: [] });
	await new Promise(resolve => setImmediate(resolve));
	assert.equal(view.body.children[0].tag, 'table');
	console.log('PASS: read-only controls, literal names, stale replies and account selection');
})().catch(e => { console.error(e); process.exitCode = 1; });
