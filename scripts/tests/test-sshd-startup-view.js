// Run with node from the repository root.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let rows;
function E(tag, attrs, children) {
	if (Array.isArray(attrs)) { children = attrs; attrs = {}; }
	const result = { tag, attrs: attrs || {}, children: children || [] };
	result.childNodes = result.children;
	Object.defineProperty(result, 'lastElementChild', { get: () => result.children.at(-1) });
	return result;
}
const context = vm.createContext({
	E, _: s => s, view: { extend: obj => obj },
	rpc: { declare: () => () => Promise.resolve({}) },
	fs: {}, ui: { createHandlerFn: () => () => {}, tabs: { initTabGroup: () => {} } },
	L: { hasViewPermission: () => true },
	cbi_update_table: (table, values) => { rows = values; }
});
vm.runInContext(`String.prototype.format = function(...args) {
	let i = 0;
	return this.replace(/%02d|%s/g, token => token === '%02d' ? String(args[i++]).padStart(2, '0') : args[i++]);
}`, context);
const source = fs.readFileSync('feeds/luci/modules/luci-mod-system/htdocs/luci-static/resources/view/system/startup.js', 'utf8');
const startup = vm.runInContext('(function() {' + source + '})()', context);
const scripts = { sshd: { start: 50, enabled: true }, network: { start: 20, enabled: true } };
for (const backend of [ { code: 0, stdout: 'systemd\n' }, { code: 0, stdout: 'procd\n' }, { code: 1 }, {} ]) {
	const output = startup.render(['exit 0\n', scripts, backend]);
	const native = backend.stdout === 'systemd\n';
	assert.equal(rows.length, native ? 1 : 2);
	assert.equal(rows.some(row => row[1] === 'sshd'), !native);
	assert.equal(JSON.stringify(output).includes('OpenSSH is managed by sshd.service'), native);
	assert.equal(rows[0][1], 'network');
}
console.log('SSH Startup view: native controls hidden, recovery controls retained, absent backend supported');
