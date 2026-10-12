// Run with node. Verify rate resets and that read-only/stale views cannot act.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('package/custom/luci-app-qemu/htdocs/luci-static/resources/view/qemu/overview.js', 'utf8');
let writable = true;
function E(tag, attrs, children) {
	if (Array.isArray(attrs)) { children = attrs; attrs = {}; }
	return { tag, attrs: attrs || {}, children: children || [], querySelectorAll: () => [] };
}
const context = vm.createContext({
	E, _: s => s, view: { extend: obj => obj },
	rpc: { declare: () => () => Promise.resolve({ success: true }) },
	poll: { add: () => {} }, dom: { content: (target, children) => { target.children = children; } },
	ui: { addNotification: () => {} }, L: { bind: (fn, self, ...args) => fn.bind(self, ...args), hasViewPermission: () => writable }
});
const view = vm.runInContext('(function() { ' + source.replace('return view.extend({', 'globalThis.qemuRate = rate; return view.extend({') + ' })()', context);
const rate = context.qemuRate;
const running = { state: 1, cpu_time: 8e9, net_rx: 500 };
const old = { state: 1, cpu_time: 3e9, net_rx: 0 };
assert.equal(rate(running, old, 'cpu_time', 5), 1e9); // 100% of one core
assert.equal(rate(running, old, 'net_rx', 5), 100);
assert.equal(rate(running, null, 'cpu_time', 5), null);
assert.equal(rate(running, old, 'disk_read', 5), null);
assert.equal(rate(running, old, 'cpu_time', 0), null);
assert.equal(rate(running, old, 'cpu_time', 31), null);
assert.equal(rate({ ...running, cpu_time: 1 }, old, 'net_rx', 5), null);
assert.equal(rate({ ...running, state: 5 }, old, 'cpu_time', 5), null);
assert.equal(rate(running, { ...old, state: 5 }, 'cpu_time', 5), null);
const guest = { ...running, uuid: '11111111-2222-3333-4444-555555555555', name: '<img src=x onerror=alert(1)>', memory_kib: 262144, vcpus: 2 };
view.render({ success: true, uri: 'qemu:///system', timestamp: 5, domains: [ guest ] });
// HTML boolean attributes must be absent, not disabled="false".
assert.equal(view.button(guest, 'shutdown', 'Shutdown', true).attrs.disabled, null);
view.busy[guest.uuid] = true;
assert.equal(view.button(guest, 'shutdown', 'Shutdown', true).attrs.disabled, true);
view.update({ success: false, error: 'offline' });
assert.equal(Object.keys(view.previous).length, 0);
assert.equal(view.rows.children.tag, 'tr');
assert.match(view.status.textContent, /offline/);
writable = false;
view.render({ success: true, uri: 'qemu:///system', timestamp: 10, domains: [ guest ] });
assert.equal(view.button(guest, 'shutdown', 'Shutdown', true).attrs.disabled, true);
assert.equal(view.rows.children[0].children[0].children[0].children[0], guest.name);
console.log('LuCI QEMU view: rates, resets, missing data, read-only permissions and text rendering passed');
