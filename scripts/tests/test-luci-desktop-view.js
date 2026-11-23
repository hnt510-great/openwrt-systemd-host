#!/usr/bin/env node
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

class Element {
	constructor(tag, attrs, children) {
		this.tag = tag;
		this.attrs = attrs || {};
		this.children = children || [];
		this.textContent = '';
		this.value = this.attrs.value || '';
		this.disabled = !!this.attrs.disabled;
		this.className = this.attrs.class || '';
		this.style = { display: (this.attrs.style || '').includes('display:none') ? 'none' : '' };
	}
	replaceChildren(...items) { this.children = items; }
	text() {
		return this.textContent + this.children.map(c => c instanceof Element ? c.text() : String(c)).join(' ');
	}
}

function E(tag, attrs, children) {
	if (Array.isArray(attrs)) { children = attrs; attrs = {}; }
	return new Element(tag, attrs, children);
}

String.prototype.format = function(...args) {
	let i = 0;
	return this.replace(/%[sd]/g, () => String(args[i++]));
};

async function main() {
	let writable = true;
	let state = {
		schema_version: 1,
		ok: true,
		error: null,
		service: { active_state: 'active', sub_state: 'running', main_pid: 1234, n_restarts: 0, boot_enabled: true },
		config: {
			enabled: '1', user: '<script>alice</script>', session: 'gnome',
			output: 'auto', mode: 'preferred', kms_scheduling: 'realtime',
			sunshine_capture: 'portal', rdp_enabled: '1', rdp_port: '3389',
			audio_enabled: '1', audio_user: 'alice'
		},
		active: { session: 'gnome', user: '<script>alice</script>', kms_scheduling: 'high-priority', output: 'auto', mode: 'preferred' },
		restart_required: true,
		drifted_keys: ['kms_scheduling'],
		provisioned: { user_valid: true, uid: 1000, gid: 1000, keyring_credential: 'tpm2', tls_present: true, error: null },
		runtime: { lan_address: '192.0.2.1', keyring_unlocked: true, rdp_active: true, sunshine_active: false, audio_active: true },
		sessions: [
			{ id: 'gnome', title: 'GNOME (Wayland)', description: 'GNOME', available: true, supports_rdp: true, supports_kms_scheduling: true },
			{ id: 'plasma', title: 'KDE Plasma', description: 'KDE', available: false, supports_rdp: false, supports_kms_scheduling: false }
		],
		outputs: ['HDMI-A-1']
	};

	const calls = [];
	const modals = [];
	const notices = [];
	const rpc = {
		declare: spec => async (...args) => {
			calls.push([spec.method, ...args]);
			if (spec.method == 'status') return state;
			if (spec.method == 'logs') return { ok: true, log: 'desktop started\n' };
			if (spec.method == 'action') {
				state = { ...state, restart_required: false, drifted_keys: [] };
				return { ok: true, action: args[0], status: state };
			}
			if (spec.method == 'switch') return { ok: true, switched: true, restarted: true, status: state };
			if (spec.method == 'sync_boot') return { ok: true, boot_enabled: true };
			return { ok: true };
		}
	};

	const options = {};
	const form = {
		Flag: 'Flag', ListValue: 'ListValue', Value: 'Value', DummyValue: 'DummyValue', NamedSection: 'NamedSection',
		Map: function() {
			this.save = async () => { calls.push(['map.save']); };
			this.render = async () => E('div', { class: 'map' }, []);
			this.section = () => ({
				option: (type, name) => {
					const opt = { type, name, values: [], value(k, v) { this.values.push([k, v]); } };
					options[name] = opt;
					return opt;
				}
			});
		}
	};

	const uci = {
		load: async () => {},
		unload: () => {},
		apply: async () => { calls.push(['uci.apply']); },
		get: (cfg, sec, key) => state.config[key]
	};

	const ui = {
		createHandlerFn: (ctx, name) => (...args) => ctx[name](...args),
		addNotification: (...args) => notices.push(args),
		showModal: (title, body) => modals.push({ title, body }),
		hideModal: () => {}
	};

	const L = {
		bind: (fn, ctx) => fn.bind(ctx),
		hasViewPermission: () => writable
	};

	const raw = fs.readFileSync(
		path.join(__dirname, '../../package/custom/luci-app-desktop/htdocs/luci-static/resources/view/desktop/settings.js'),
		'utf8'
	);
	const body = raw.replace(/^'require [^']+';\s*$/gm, '');
	const view = new Function('view', 'form', 'poll', 'rpc', 'uci', 'ui', 'L', 'E', '_', body)(
		{ extend: x => x }, form, { add() {} }, rpc, uci, ui, L, E, x => x
	);

	const loaded = await view.load();
	const dom = await view.render(loaded);
	assert(dom instanceof Element);

	// Session dropdown populated dynamically from status.sessions
	assert.deepEqual(options.session.values, [
		['gnome', 'GNOME (Wayland)'],
		['plasma', 'KDE Plasma (not installed)']
	]);
	// Read-only fields stay DummyValue
	assert.equal(options.user.type, 'DummyValue');
	assert.equal(options.rdp_port.type, 'DummyValue');
	assert.equal(options.sunshine_capture.type, 'DummyValue');

	// Drift banner visible when restart_required == true
	assert.equal(view.driftBanner.style.display, '');
	assert.match(view.driftText.textContent, /kms_scheduling/);

	// Keyring status reflects TPM2 + unlocked
	assert.match(view.cells.keyring.textContent, /TPM2 sealed \(unlocked\)/);
	assert.equal(view.startBtn.disabled, true);
	assert.equal(Boolean(view.stopBtn.disabled), false);
	assert.equal(Boolean(view.restartBtn.disabled), false);

	// Mode & output validators
	assert.equal(options.mode.validate('main', '1920x1080@60'), true);
	assert.notEqual(options.mode.validate('main', '99999x10'), true);
	assert.equal(options.output.validate('main', 'HDMI-A-1'), true);
	assert.notEqual(options.output.validate('main', 'HDMI;id'), true);

	// Save & Apply saves UCI + sync_boot, does NOT auto-restart desktop
	calls.length = 0;
	await view.handleSaveApply();
	assert(calls.some(c => c[0] == 'map.save'));
	assert(calls.some(c => c[0] == 'uci.apply'));
	assert(calls.some(c => c[0] == 'sync_boot'));
	assert(!calls.some(c => c[0] == 'action' && c[1] == 'restart'));

	// Restart triggers confirmation modal before calling action('restart')
	modals.length = 0;
	view.handleRestart();
	assert.equal(modals.length, 1);
	assert(!calls.some(c => c[0] == 'action'));
	const confirmBtn = modals[0].body[1].children.find(c => c instanceof Element && c.text().includes('Confirm'));
	confirmBtn.attrs.click();
	await new Promise(r => setTimeout(r, 0));
	assert(calls.some(c => c[0] == 'action' && c[1] == 'restart'));
	assert.equal(view.driftBanner.style.display, 'none');

	// Read-only permission disables all mutating buttons
	writable = false;
	await view.render(await view.load());
	assert.equal(view.startBtn.disabled, true);
	assert.equal(view.stopBtn.disabled, true);
	assert.equal(view.restartBtn.disabled, true);
	assert.equal(view.switchBtn.disabled, true);

	// No raw <script> tags injected into DOM
	const tags = [];
	function walk(el) {
		if (!(el instanceof Element)) return;
		tags.push(el.tag);
		el.children.forEach(walk);
	}
	walk(dom);
	assert(!tags.includes('script'));

	// Non-GNOME session: keyring & RDP show Not applicable, Start remains enabled when stopped
	writable = true;
	state = {
		...state,
		service: { active_state: 'inactive', sub_state: 'dead', main_pid: 0, n_restarts: 0, boot_enabled: true },
		config: { ...state.config, session: 'dummy', enabled: '1', rdp_enabled: '0' },
		active: null,
		selected_session: 'dummy',
		selection_error: null,
		restart_required: false,
		drifted_keys: [],
		provisioned: { user_valid: true, uid: 1000, gid: 1000, keyring_required: false, keyring_credential: 'not_applicable', tls_present: false, error: null },
		runtime: { lan_address: '192.0.2.1', keyring_unlocked: null, rdp_available: false, rdp_active: false, sunshine_active: false, audio_active: false },
		sessions: [{ id: 'dummy', title: 'Dummy Wayland', description: 'Test', available: true, supports_rdp: false, supports_kms_scheduling: false }]
	};
	await view.render(await view.load());
	assert.equal(view.cells.keyring.textContent, 'Not applicable');
	assert.equal(view.cells.rdp.textContent, 'Not applicable');
	assert.equal(Boolean(view.startBtn.disabled), false);

	// No available sessions -> warning banner + Start/Restart disabled
	state = {
		...state,
		config: { ...state.config, session: '' },
		selected_session: null,
		selection_error: 'No desktop session is installed or available',
		sessions: []
	};
	await view.render(await view.load());
	assert.match(view.statusBanner.textContent, /No desktop session/);
	assert.equal(view.startBtn.disabled, true);
	assert.equal(view.restartBtn.disabled, true);

	console.log('PASS: status, sessions, drift banner, Save & Apply isolation, confirm modal, ACL, decoupling N/A states, and XSS safety');
}

main().catch(err => {
	console.error(err);
	process.exitCode = 1;
});
