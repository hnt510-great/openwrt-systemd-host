// Run with node. Verify dashboard URLs, listen validation, status and rendering.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('package/custom/luci-app-daed/htdocs/luci-static/resources/view/daed/settings.js', 'utf8');

const config = { daed: { config: { enabled: '1', listen_addr: '0.0.0.0:2023' } }, passwall: [] };
const execs = [];
let writable = true;
let services = {};
function E(tag, attrs, children) {
	if (Array.isArray(tag)) return { tag: 'fragment', children: attrs };
	if (Array.isArray(attrs)) { children = attrs; attrs = {}; }
	const node = { tag, attrs: attrs || {}, children: children || [], dataset: {}, className: '', textContent: '',
		replaceChildren(...items) { this.children = items; } };
	if (node.attrs.disabled) node.disabled = node.attrs.disabled;
	return node;
}
class Option {
	constructor(type, name, title, description) { Object.assign(this, { type, name, title, description }); }
}
class Section {
	constructor() { this.options = {}; }
	option(type, name, title, description) { return (this.options[name] = new Option(type, name, title, description)); }
}
class FormMap {
	constructor(config, title, description) { Object.assign(this, { config, title, description }); }
	section() { return (this.service = new Section()); }
	render() { return Promise.resolve({ tag: 'map', map: this }); }
}
const context = vm.createContext({
	E, window: { location: { hostname: '192.0.2.1' }, open: () => {} },
	_: s => s,
	view: { extend: obj => obj },
	form: { Map: FormMap, NamedSection: 'NamedSection', Flag: 'Flag', Value: 'Value' },
	fs: { exec: (cmd, args) => { execs.push([ cmd, ...args ].join(' '));
		return Promise.resolve(cmd == '/usr/bin/tail' ? { code: 0, stdout: 'log line\n' } : { code: 0 }); } },
	poll: { add: () => {} },
	rpc: { declare: () => () => Promise.resolve(services) },
	uci: {
		load: () => Promise.resolve(),
		get: (c, s, o) => (config[c] && config[c][s] || {})[o],
		sections: (c) => config[c] || []
	},
	ui: { createHandlerFn: (self, name) => self[name].bind(self), addNotification: () => {} },
	L: { bind: (fn, self, ...args) => fn.bind(self, ...args), hasViewPermission: () => writable }
});
// LuCI adds String.prototype.format; provide it inside the sandbox.
vm.runInContext("String.prototype.format = function(v) { return this.replace('%s', v); };", context);
const view = vm.runInContext('(function() { ' + source.replace('return view.extend({',
	'globalThis.daed = { parseListen, dashboardURL, statusInfo, isRunning }; return view.extend({') + ' })()', context);
const h = context.daed;

// Listen addresses and dashboard URLs.
assert.deepEqual({ ...h.parseListen('0.0.0.0:2023') }, { host: '0.0.0.0', port: '2023' });
assert.deepEqual({ ...h.parseListen('[fd00::1]:8080') }, { host: 'fd00::1', port: '8080' });
assert.deepEqual({ ...h.parseListen(':2023') }, { host: '', port: '2023' });
for (const bad of [ '', '2023', 'host', 'fd00::1:2023', '1.2.3.4:0', '1.2.3.4:65536', '1.2.3.4:20x' ])
	assert.equal(h.parseListen(bad), null, bad);
assert.equal(h.dashboardURL('0.0.0.0:2023', '192.0.2.1'), 'http://192.0.2.1:2023/');
assert.equal(h.dashboardURL(':2023', 'router.lan'), 'http://router.lan:2023/');
assert.equal(h.dashboardURL('[::]:2023', 'fd00::1'), 'http://[fd00::1]:2023/');
assert.equal(h.dashboardURL('[::]:2023', '[fd00::1]'), 'http://[fd00::1]:2023/');
assert.equal(h.dashboardURL('192.0.2.1:9000', 'other'), 'http://192.0.2.1:9000/');
assert.equal(h.dashboardURL('127.0.0.1:2023', '192.0.2.1'), null);
assert.equal(h.dashboardURL('[::1]:2023', '192.0.2.1'), null);
assert.equal(h.dashboardURL('nonsense', '192.0.2.1'), null);

// Running detection uses procd instance state.
assert.equal(h.isRunning({ daed: { instances: { daed: { running: true } } } }), true);
assert.equal(h.isRunning({ daed: { instances: { daed: { running: false } } } }), false);
assert.equal(h.isRunning({ daed: {} }), false);
assert.equal(h.isRunning(undefined), false);

// Status explains the Passwall interlock.
assert.equal(h.statusInfo(true, true, true).cls, 'notice');
assert.match(String(h.statusInfo(false, true, true).text), /Passwall/);
assert.equal(h.statusInfo(false, true, true).cls, 'warning');
assert.match(String(h.statusInfo(false, true, false).text), /log/);
assert.match(String(h.statusInfo(false, false, true).text), /disabled/);

(async () => {
	// Running service: dashboard enabled with the browser's host, log loaded.
	services = { daed: { instances: { daed: { running: true } } } };
	let page = await view.render([ services ]);
	assert.equal(page.tag, 'fragment');
	const map = page.children[0].map;
	assert.equal(map.config, 'daed');
	assert.equal(map.service.options.enabled.rmempty, false);
	assert.equal(map.service.options.listen_addr.validate('config', '0.0.0.0:2023'), true);
	assert.notEqual(map.service.options.listen_addr.validate('config', '2023'), true);
	const links = () => view.dashboard.children.filter(c => c && c.tag == 'a');
	const text = () => JSON.stringify(view.dashboard.children);
	assert.deepEqual(links().map(a => a.attrs.href), [ 'http://192.0.2.1:2023/', 'http://192.0.2.1:2023/' ]);
	for (const a of links()) {
		assert.equal(a.attrs.target, '_blank');
		assert.equal(a.attrs.rel, 'noopener noreferrer');
	}
	assert.deepEqual([ ...links()[1].children ], [ 'http://192.0.2.1:2023/' ]);
	assert.doesNotMatch(text(), /not running/);
	assert.equal(view.log.value, 'log line\n');
	assert.deepEqual(execs, [ '/usr/bin/tail -n 200 /var/log/daed/daed.log' ]);
	assert.equal(view.status.className, 'alert-message notice');

	// Passwall enabled and daed stopped: warning, no dashboard link.
	config.passwall = [ { enabled: '1' } ];
	view.updateStatus({ daed: { instances: {} } });
	assert.equal(view.status.className, 'alert-message warning');
	assert.match(view.status.textContent, /Passwall/);
	// Stopped: the link stays visible, with a hint.
	assert.equal(links().length, 2);
	assert.match(text(), /daed is not running/);

	// A specific listen address is used as-is; loopback-only shows no link.
	config.daed.config.listen_addr = '192.0.2.1:9000';
	view.updateStatus(services);
	assert.equal(links()[0].attrs.href, 'http://192.0.2.1:9000/');
	config.daed.config.listen_addr = '127.0.0.1:2023';
	view.updateStatus(services);
	assert.equal(links().length, 0);
	assert.match(text(), /loopback only/);
	config.daed.config.listen_addr = '0.0.0.0:2023';

	// Restart runs exactly the command the ACL grants.
	await view.handleRestart({ currentTarget: {} });
	assert.equal(execs.at(-1), '/etc/init.d/daed restart');
	const acl = JSON.parse(fs.readFileSync('package/custom/luci-app-daed/root/usr/share/rpcd/acl.d/luci-app-daed.json'));
	assert.ok(acl['luci-app-daed'].write.file['/etc/init.d/daed restart']);
	assert.ok(acl['luci-app-daed'].read.file[execs[0]]);
	// fs.exec goes through ubus file.exec, which needs its own grant.
	assert.deepEqual(acl['luci-app-daed'].read.ubus.file, [ 'exec' ]);
	assert.deepEqual(acl['luci-app-daed'].write.ubus.file, [ 'exec' ]);

	// Read-only users cannot restart.
	writable = false;
	page = await view.render([ services ]);
	const restart = page.children[1].children[3].children[0];
	assert.equal(restart.attrs.disabled, true);
	console.log('LuCI daed view: listen parsing, dashboard URLs and link, status, interlock, ACL commands and permissions passed');
})().catch(error => { console.error(error); process.exit(1); });
