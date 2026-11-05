#!/usr/bin/env node
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const base = path.join(root, 'package/custom/luci-app-desktop-setup/htdocs/luci-static/resources');
function element(tag, attrs, children) {
	const node = { tag, attrs: attrs || {}, children: children || [] };
	Object.assign(node, attrs || {});
	return node;
}
function find(node, id) {
	if (node && node.id == id) return node;
	for (const child of (node && node.children || [])) {
		if (child && typeof child == 'object') { const found = find(child, id); if (found) return found; }
	}
}
function environment(filename) {
	let status = { success: true, platform: { native: true, lan_address: '192.0.2.1',
		available: { desktop: true, rdp: true, moonlight: true, containers: true, flatpak: true, virtual_machines: true } },
		accounts: [], features: {}, running: false, automatic: true, job: {} };
	const calls = [], polls = [], redirects = [], notifications = [];
	let permission = true, access = true, fail = false;
	const context = vm.createContext({
		_: s => s, E: element,
		view: { extend: obj => obj }, baseclass: { extend: obj => obj },
		dom: { content: (node, children) => { node.children = children; } },
		ui: { addNotification: (...args) => notifications.push(args) },
		poll: { add: callback => polls.push(callback), remove: callback => polls.splice(polls.indexOf(callback), 1) },
		L: { hasViewPermission: () => permission, url: s => '/cgi-bin/luci/' + s },
		window: { location: { assign: s => redirects.push(s), replace: s => redirects.push(s) } },
		rpc: { declare: schema => (...args) => {
			if (schema.object == 'session') return Promise.resolve(access);
			if (schema.method == 'status') return Promise.resolve(status);
			calls.push({ method: schema.method, args });
			if (schema.method == 'defer') return Promise.resolve(fail ? { success: false, error: 'busy' } : { success: true });
			return Promise.resolve(fail ? { success: false, error: 'helper_failed' } : { success: true, accepted: true });
		} }
	});
	const source = fs.readFileSync(path.join(base, filename), 'utf8');
	const view = vm.runInContext('(function() {\n' + source + '\n})()', context);
	return { view, calls, polls, redirects, notifications, source,
		get status() { return status; }, set status(value) { status = value; },
		set permission(value) { permission = value; }, set access(value) { access = value; }, set fail(value) { fail = value; } };
}

(async () => {
	for (const page of [0, 1, 2]) {
		const skip = environment('view/system/desktop-setup.js');
		skip.view.render(skip.status);
		skip.view.page = page; skip.view.draw();
		const button = skip.view.root.children.at(-1).children.find(n => n.children.includes('Skip setup'));
		assert.ok(button);
		assert.equal(button.disabled, false);
		await button.click();
		assert.deepEqual(skip.calls.map(call => call.method), ['defer']);
		assert.deepEqual(skip.redirects, ['/cgi-bin/luci/admin/status/overview']);
		// A failed save must leave the wizard visible so skipping can be retried.
		skip.fail = true;
		await button.click();
		assert.equal(skip.redirects.length, 1);
		assert.equal(skip.notifications.length, 1);
		skip.permission = false; skip.view.draw();
		assert.equal(skip.view.root.children.at(-1).children.find(n => n.children.includes('Skip setup')).disabled, true);
	}

	const env = environment('view/system/desktop-setup.js');
	const app = env.view;
	app.render(env.status);
	assert.equal(app.page, 0);
	app.inputs.username.value = 'alice;reboot';
	app.inputs.password.value = app.inputs.password_confirm.value = 'unix-password-fixture';
	app.next();
	assert.equal(app.page, 0);
	assert.match(app.message, /lowercase/);
	app.inputs.username.value = 'alice\n';
	app.next();
	assert.equal(app.page, 0);
	assert.match(app.message, /lowercase/);
	app.inputs.username.value = 'alice';
	app.next();
	assert.equal(app.page, 1);
	app.inputs.rdp_password.value = 'rdp-password-fixture';
	app.inputs.rdp_confirm.value = 'mismatched-password';
	app.next();
	assert.equal(app.page, 1);
	assert.match(app.message, /do not match/);
	app.inputs.rdp_confirm.value = 'rdp-password-fixture';
	app.next();
	assert.equal(app.page, 2);
	assert.equal(app.applyButton.disabled, true);
	const checkbox = find(app.root, 'setup-confirm');
	checkbox.checked = true; checkbox.change.call(checkbox);
	assert.equal(app.applyButton.disabled, false);
	env.status = Object.assign({}, env.status, { running: true, job: { status: 'running', username: 'alice', steps: [] } });
	await app.apply();
	assert.equal(env.calls[0].method, 'apply');
	assert.deepEqual(Array.from(env.calls[0].args).slice(0, 7), ['alice', 'create', 'unix-password-fixture', 'rdp-password-fixture', '', 'portal', true]);
	assert.equal(app.plan.password, ''); assert.equal(app.plan.rdp_password, '');
	assert.equal(app.page, 3); assert.equal(env.polls.length, 1);
	env.status = Object.assign({}, env.status, { completed: true, automatic: false, running: false,
		accounts: [{ username: 'alice', uid: 1000, unlocked: true }], username: 'alice',
		features: { moonlight: true }, job: { status: 'done', steps: [{ id: 'desktop', status: 'done' }] } });
	await env.polls[0]();
	assert.equal(env.polls.length, 0);
	assert.match(JSON.stringify(app.root), /192\.0\.2\.1:47990/);
	assert.doesNotMatch(JSON.stringify(app.root), /unix-password-fixture|rdp-password-fixture/);

	const existing = environment('view/system/desktop-setup.js');
	existing.status = Object.assign({}, existing.status, { username: 'alice', completed: true,
		accounts: [{ username: 'alice', uid: 1000, unlocked: true, keyring_required: true }] });
	existing.view.render(existing.status);
	assert.equal(existing.view.plan.mode, 'existing');
	assert.equal(existing.view.inputs.password, undefined);
	existing.view.next();
	assert.match(existing.view.message, /keyring/);
	existing.view.inputs.keyring_password.value = 'old-keyring-secret';
	existing.view.next();
	assert.equal(existing.view.page, 1);
	existing.permission = false;
	existing.view.draw();
	const actions = existing.view.root.children.at(-1).children;
	assert.equal(actions.find(n => n.children.includes('Next')).disabled, true);

	const failure = environment('view/system/desktop-setup.js');
	failure.view.render(failure.status);
	Object.assign(failure.view.plan, { username: 'alice', password: 'unix-password-fixture', rdp_password: 'rdp-password-fixture' });
	failure.view.page = 2; failure.view.draw(); failure.fail = true;
	await failure.view.apply();
	assert.match(failure.view.message, /helper failed/);
	assert.equal(failure.view.plan.password, '');
	assert.equal(failure.view.applyButton.disabled, true);
	assert.doesNotMatch(env.source, /innerHTML|sessionStorage|localStorage|console\.log/);

	for (const allowed of [false, true]) {
		const banner = environment('view/status/include/00_desktop_setup.js');
		banner.access = allowed;
		banner.view.render(await banner.view.load());
		assert.equal(banner.redirects.length, allowed ? 1 : 0);
	}
	const completed = environment('view/status/include/00_desktop_setup.js');
	completed.status.automatic = false;
	completed.view.render(await completed.view.load());
	assert.equal(completed.redirects.length, 0);
	const recovery = environment('view/status/include/00_desktop_setup.js');
	recovery.status.platform.native = false;
	recovery.view.render(await recovery.view.load());
	assert.equal(recovery.redirects.length, 0);
	console.log('Desktop wizard: navigation, validation, confirmation, secret clearing, async progress, read-only access and first-login redirect passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
