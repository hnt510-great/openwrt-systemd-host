#!/usr/bin/env node
// Exercise the real view with text-only DOM and RPC fixtures, including errors.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const base = path.join(root, 'package/custom/luci-app-needrestart/htdocs/luci-static/resources/view/status');

class Element {
	constructor(tag, attrs, children) {
		this.tag = tag;
		this.attrs = attrs || {};
		this.children = children || [];
		this.textContent = '';
	}
	appendChild(child) { this.children.push(child); return child; }
	replaceChildren(...children) { this.children = children; }
	text() { return this.textContent + this.children.map(c => c instanceof Element ? c.text() : String(c)).join(' '); }
}

function E(tag, attrs, children) {
	if (Array.isArray(attrs)) { children = attrs; attrs = {}; }
	return new Element(tag, attrs, children);
}

async function main() {
	let status = { report: null }, scans = 0;
	const notices = [], rpc = { declare: spec => async () => {
		if (spec.method == 'scan') { scans++; return { success: true }; }
		if (status instanceof Error) throw status;
		return status;
	} };
	const extend = { extend: value => value };
	const L = { bind: (fn, self) => fn.bind(self), url: s => '/cgi-bin/luci/' + s };
	const make = new Function('view', 'baseclass', 'rpc', 'poll', 'ui', 'L', 'E', '_',
		fs.readFileSync(path.join(base, 'needrestart.js'), 'utf8'));
	const view = make(extend, extend, rpc, { add() {} }, { addNotification: (...args) => notices.push(args) }, L, E, s => s);
	view.render();
	await view.pending;
	assert.match(view.status.textContent, /No report yet/);
	await view.scanButton.attrs.click();
	assert.equal(scans, 1);
	status = { pending: true, report: null };
	await view.refresh();
	assert.equal(view.scanButton.disabled, true);
	assert.match(view.status.textContent, /queued/);
	status = { running: true, report: null };
	await view.refresh();
	assert.match(view.status.textContent, /running/);
	status = { report: { complete: false, timestamp: 100, processes_scanned: 5,
		kernel: { status: 'optional-same-abi-trial', recommended_action: 'No required reboot' },
		warnings: ['inaccessible container'], services: [{ name: '<img src=x onerror=alert(1)>',
			kind: 'systemd', disruptive: true, recommended_action: 'Maintenance review',
			processes: [{ pid: 1, files: [{ path: '<script>test</script>', reason: 'replaced' }] }] }],
		containers: [{ id: 'a'.repeat(64), name: 'test', uid: 1000, account: 'test', image_reference: 'example:v1', image_status: 'changed' }] } };
	await view.refresh();
	assert.equal(view.scanButton.disabled, false);
	assert.match(view.status.textContent, /incomplete/);
	assert.match(view.content.text(), /<script>test<\/script>/);
	assert.match(view.content.text(), /recreation needed/);
	assert.match(view.content.text(), /No required reboot/);
	const tags = [];
	function walk(e) { if (!(e instanceof Element)) return; tags.push(e.tag); e.children.forEach(walk); }
	walk(view.content);
	assert(!tags.includes('script') && !tags.includes('img'), 'untrusted evidence must be rendered as text');
	status = new Error('RPC unavailable');
	await view.refresh();
	assert.match(view.status.textContent, /RPC unavailable/);
	assert.equal(view.scanButton.disabled, false);
	const summary = new Function('baseclass', 'rpc', 'L', 'E', '_',
		fs.readFileSync(path.join(base, 'include/15_needrestart.js'), 'utf8'))(extend, rpc, L, E, s => s);
	assert.match(summary.render({ report: null }).text(), /No restart report/);
	assert.match(summary.render({ error: true }).text(), /unavailable/);
	assert.match(summary.render({ pending: true }).text(), /pending/);
	assert.match(summary.render({ report: { complete: false, services: [], containers: [], kernel: {}, timestamp: 1 } }).text(), /Incomplete coverage/);
	console.log('PASS: LuCI loading, queue, running, evidence, kernel/container advice, text escaping, RPC errors, overview');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
