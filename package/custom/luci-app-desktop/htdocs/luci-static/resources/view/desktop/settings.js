// SPDX-License-Identifier: GPL-2.0-only
'use strict';
'require view';
'require form';
'require poll';
'require rpc';
'require uci';
'require ui';

var callStatus = rpc.declare({
	object: 'luci.desktop',
	method: 'status',
	expect: {}
});

var callLogs = rpc.declare({
	object: 'luci.desktop',
	method: 'logs',
	params: [ 'lines' ],
	expect: {}
});

var callAction = rpc.declare({
	object: 'luci.desktop',
	method: 'action',
	params: [ 'verb' ],
	expect: {}
});

var callSwitch = rpc.declare({
	object: 'luci.desktop',
	method: 'switch',
	params: [ 'session' ],
	expect: {}
});

var callSyncBoot = rpc.declare({
	object: 'luci.desktop',
	method: 'sync_boot',
	expect: {}
});

function validateMode(value) {
	var text = String(value == null ? '' : value).trim();
	if (text == '' || text == 'preferred')
		return true;
	var m = text.match(/^([1-9][0-9]*)x([1-9][0-9]*)(?:@([1-9][0-9]*))?$/);
	if (!m)
		return _('Expecting preferred or WIDTHxHEIGHT[@HZ]');
	var w = +m[1], h = +m[2], hz = m[3] ? +m[3] : null;
	if (w < 320 || w > 16384 || h < 200 || h > 16384 || (hz !== null && (hz < 1 || hz > 240)))
		return _('Display mode out of range');
	return true;
}

function validateOutput(value) {
	var text = String(value == null ? '' : value).trim();
	if (text == '' || /^[a-zA-Z0-9_-]+$/.test(text))
		return true;
	return _('Invalid DRM output name');
}

function sessionLabel(sessions, id) {
	var list = Array.isArray(sessions) ? sessions : [];
	for (var i = 0; i < list.length; i++) {
		if (list[i].id == id)
			return list[i].title || id;
	}
	return id || _('None');
}

function statusBannerInfo(data) {
	if (!data || !data.ok) {
		var msg = (data && data.error && data.error.message) ? data.error.message : _('Unable to query desktop status.');
		return { cls: 'warning', text: msg };
	}
	var svc = data.service || {};
	var cfg = data.config || {};
	var prov = data.provisioned || {};
	var rt = data.runtime || {};
	if (svc.active_state == 'active') {
		var activeSession = (data.active && data.active.session) || data.selected_session || cfg.session || '';
		if (rt.session_ready === false) {
			return {
				cls: 'notice',
				text: _('Desktop is starting (%s, user %s, PID %d)…').format(
					sessionLabel(data.sessions, activeSession), cfg.user, svc.main_pid || 0)
			};
		}
		return {
			cls: 'notice',
			text: _('Desktop is running (%s, user %s, PID %d).').format(
				sessionLabel(data.sessions, activeSession), cfg.user, svc.main_pid || 0)
		};
	}
	if (svc.active_state == 'activating') {
		return { cls: 'notice', text: _('Desktop is starting…') };
	}
	if (svc.active_state == 'failed') {
		return { cls: 'warning', text: _('Desktop failed to start. Check the log below or switch back to another installed session.') };
	}
	if (data.selection_error) {
		return { cls: 'warning', text: data.selection_error };
	}
	var keyringMissing = prov.keyring_credential == 'missing';
	if (!prov.user_valid || keyringMissing) {
		return {
			cls: 'warning',
			text: keyringMissing ?
				_('Desktop account or keyring is not provisioned yet. Run desktop-setup USER over SSH first.') :
				(prov.error || _('Desktop account is not provisioned yet. Run desktop-setup USER over SSH first.'))
		};
	}
	if (cfg.enabled != '1') {
		return { cls: '', text: _('Desktop service is disabled.') };
	}
	return { cls: 'warning', text: _('Desktop is enabled but not currently running. Check the log below.') };
}

function formatKeyring(prov, runtime, active) {
	var cred = (prov && prov.keyring_credential) || 'missing';
	if (cred == 'not_applicable')
		return _('Not applicable');
	var credLabel = cred == 'tpm2' ? _('TPM2 sealed') :
		(cred == 'plaintext' ? _('Plaintext fallback') : _('Not provisioned'));
	if (!active)
		return credLabel;
	if (runtime && runtime.keyring_unlocked === true)
		return _('%s (unlocked)').format(credLabel);
	if (runtime && runtime.keyring_unlocked === false)
		return _('%s (locked)').format(credLabel);
	return credLabel;
}

return view.extend({
	load: function() {
		return Promise.all([
			callStatus().catch(function(err) {
				return { ok: false, error: { code: 1, message: err.message || String(err) } };
			}),
			uci.load('desktop')
		]);
	},

	setBusy: function(busy) {
		this.busy = !!busy;
		this.syncButtons();
	},

	syncButtons: function() {
		var data = this.latest || {};
		var writable = this.writable;
		var prov = data.provisioned || {};
		var cfg = data.config || {};
		var svc = data.service || {};
		var provisioned = !!(prov.user_valid && prov.keyring_credential != 'missing');
		var hasTargetSession = !data.selection_error;
		var running = svc.active_state == 'active' || svc.active_state == 'activating';
		var enabled = cfg.enabled == '1';

		if (this.startBtn)
			this.startBtn.disabled = (!writable || this.busy || !provisioned || !hasTargetSession || !enabled || running) ? true : null;
		if (this.stopBtn)
			this.stopBtn.disabled = (!writable || this.busy || !running) ? true : null;
		if (this.restartBtn)
			this.restartBtn.disabled = (!writable || this.busy || !provisioned || !hasTargetSession || !enabled) ? true : null;
		if (this.driftRestartBtn)
			this.driftRestartBtn.disabled = (!writable || this.busy || !provisioned || !hasTargetSession || !enabled) ? true : null;
		if (this.switchBtn) {
			var target = this.switchSelect ? this.switchSelect.value : '';
			var available = (data.sessions || []).some(function(s) { return s.id == target && s.available; });
			this.switchBtn.disabled = (!writable || this.busy || !available) ? true : null;
		}
	},

	updateStatus: function(data) {
		this.latest = data || { ok: false };
		var banner = statusBannerInfo(this.latest);
		this.statusBanner.className = 'alert-message ' + banner.cls;
		this.statusBanner.textContent = banner.text;

		var drift = !!(this.latest.ok && this.latest.restart_required);
		if (drift) {
			var keys = (this.latest.drifted_keys || []).join(', ');
			this.driftText.textContent = _('Configuration changed (%s). Restart the desktop to apply changes to the running session.').format(keys);
			this.driftBanner.style.display = '';
		} else {
			this.driftBanner.style.display = 'none';
		}

		if (this.latest.ok) {
			var cfg = this.latest.config || {};
			var svc = this.latest.service || {};
			var prov = this.latest.provisioned || {};
			var rt = this.latest.runtime || {};
			var active = svc.active_state == 'active';
			var activeSession = (this.latest.active && this.latest.active.session) || '';
			var lan = rt.lan_address || _('Unavailable');

			this.cells.activeSession.textContent = active ?
				sessionLabel(this.latest.sessions, activeSession || this.latest.selected_session || cfg.session) : _('Stopped');
			this.cells.user.textContent = cfg.user || _('Not configured');
			this.cells.keyring.textContent = formatKeyring(prov, rt, active);
			this.cells.lan.textContent = lan;
			this.cells.rdp.textContent = rt.rdp_available === false ?
				_('Not applicable') :
				(cfg.rdp_enabled == '1' ?
					(rt.rdp_active ? _('Running (%s:%s)').format(lan, cfg.rdp_port || '3389') : _('Enabled (idle)')) :
					_('Disabled'));
			this.cells.sunshine.textContent = rt.sunshine_active ?
				_('Running (%s)').format(cfg.sunshine_capture || 'portal') :
				_('Stopped (%s)').format(cfg.sunshine_capture || 'portal');
			this.cells.audio.textContent = cfg.audio_enabled == '1' ?
				(rt.audio_active ? _('Running') : _('Enabled (idle)')) :
				_('Disabled');

			this.syncSwitchSelect(this.latest.sessions || [], cfg.session || this.latest.selected_session || '');
		}
		this.syncButtons();
	},

	syncSwitchSelect: function(sessions, current) {
		if (!this.switchSelect)
			return;
		var key = JSON.stringify([ sessions.map(function(s) { return [ s.id, s.title, s.available ]; }), current ]);
		if (key == this.switchSelectKey)
			return;
		this.switchSelectKey = key;
		var options = [];
		for (var i = 0; i < sessions.length; i++) {
			var s = sessions[i];
			var label = s.available ? (s.title || s.id) : _('%s (not installed)').format(s.title || s.id);
			options.push(E('option', {
				'value': s.id,
				'selected': s.id == current ? 'selected' : null,
				'disabled': s.available ? null : true
			}, [ label ]));
		}
		this.switchSelect.replaceChildren.apply(this.switchSelect, options);
		if (current)
			this.switchSelect.value = current;
	},

	runAction: function(verb) {
		this.setBusy(true);
		return callAction(verb).then(L.bind(function(res) {
			if (!res || !res.ok) {
				var msg = (res && res.error && res.error.message) || _('Desktop action failed');
				ui.addNotification(null, E('p', {}, [ msg ]), 'error');
			}
			if (res && res.status)
				this.updateStatus(res.status);
			else
				return callStatus().then(L.bind(this.updateStatus, this));
		}, this)).catch(function(err) {
			ui.addNotification(null, E('p', {}, [ _('Desktop action failed: %s').format(err.message || err) ]), 'error');
		}).finally(L.bind(function() {
			this.setBusy(false);
		}, this));
	},

	runSwitch: function(sessionId) {
		this.setBusy(true);
		return callSwitch(sessionId).then(L.bind(function(res) {
			if (!res || !res.ok) {
				var msg = (res && res.error && res.error.message) || _('Desktop session switch failed');
				ui.addNotification(null, E('p', {}, [ msg ]), 'error');
			} else {
				ui.addNotification(null, E('p', {}, [
					res.restarted ?
						_('Switched desktop session to %s and restarted.').format(sessionId) :
						_('Saved desktop session %s.').format(sessionId)
				]), 'info');
			}
			return uci.unload('desktop') || uci.load('desktop');
		}, this)).then(L.bind(function() {
			return callStatus().then(L.bind(this.updateStatus, this));
		}, this)).catch(function(err) {
			ui.addNotification(null, E('p', {}, [ _('Desktop session switch failed: %s').format(err.message || err) ]), 'error');
		}).finally(L.bind(function() {
			this.setBusy(false);
		}, this));
	},

	confirmInterrupt: function(title, message, onConfirm) {
		ui.showModal(title, [
			E('p', {}, [ message ]),
			E('div', { 'class': 'right' }, [
				E('button', {
					'class': 'cbi-button',
					'click': function() { ui.hideModal(); }
				}, [ _('Cancel') ]),
				' ',
				E('button', {
					'class': 'cbi-button cbi-button-negative important',
					'click': function() {
						ui.hideModal();
						onConfirm();
					}
				}, [ _('Confirm') ])
			])
		]);
	},

	handleStart: function() {
		return this.runAction('start');
	},

	handleStop: function() {
		this.confirmInterrupt(
			_('Stop desktop session'),
			_('Stopping the desktop will close open graphical applications and disconnect active RDP or Sunshine streams. Continue?'),
			L.bind(function() { this.runAction('stop'); }, this)
		);
	},

	handleRestart: function() {
		this.confirmInterrupt(
			_('Restart desktop session'),
			_('Restarting the desktop will close open graphical applications and disconnect active RDP or Sunshine streams. Continue?'),
			L.bind(function() { this.runAction('restart'); }, this)
		);
	},

	handleSwitch: function() {
		var target = this.switchSelect ? this.switchSelect.value : '';
		if (!target)
			return;
		var running = this.latest && this.latest.service &&
			(this.latest.service.active_state == 'active' || this.latest.service.active_state == 'activating');
		if (!running) {
			return this.runSwitch(target);
		}
		this.confirmInterrupt(
			_('Switch desktop session'),
			_('Switching to %s will restart the running desktop session and disconnect active RDP or Sunshine streams. Continue?').format(
				sessionLabel(this.latest.sessions, target)),
			L.bind(function() { this.runSwitch(target); }, this)
		);
	},

	readLog: function() {
		return callLogs(100).then(function(res) {
			if (res && res.ok)
				return res.log || _('No log entries yet.');
			return _('Unable to read log: %s').format((res && res.error && res.error.message) || _('Unknown error'));
		}).catch(function(err) {
			return _('Unable to read log: %s').format(err.message || err);
		});
	},

	handleLogRefresh: function() {
		return this.readLog().then(L.bind(function(text) {
			this.logBox.value = text;
			this.logBox.scrollTop = this.logBox.scrollHeight;
		}, this));
	},

	handleSaveApply: function(ev, mode) {
		return this.map.save().then(function() {
			return uci.apply();
		}).then(function() {
			return callSyncBoot().catch(function() { return null; });
		}).then(L.bind(function() {
			return callStatus().then(L.bind(this.updateStatus, this));
		}, this));
	},

	render: function(data) {
		var statusData = data[0] || { ok: false };
		var sessions = (statusData.ok && Array.isArray(statusData.sessions)) ? statusData.sessions : [];
		var outputs = (statusData.ok && Array.isArray(statusData.outputs)) ? statusData.outputs : [];
		var cfg = (statusData.ok && statusData.config) ? statusData.config : {};
		this.writable = L.hasViewPermission ? L.hasViewPermission() : true;
		this.busy = false;

		var m = new form.Map('desktop', _('Desktop'),
			_('Manage the OpenWrt native-systemd desktop session and switch between installed desktop environments without replacing TPM2 keyring unlocking.'));
		this.map = m;

		var s = m.section(form.NamedSection, 'main', 'desktop', _('Configuration'));
		s.addremove = false;

		var o = s.option(form.Flag, 'enabled', _('Enable desktop service'),
			_('Start the desktop session at boot and allow starting it from LuCI or hotplug.'));
		o.rmempty = false;

		o = s.option(form.ListValue, 'session', _('Desktop environment'),
			_('Registered sessions under /usr/libexec/openwrt-desktop/sessions.d. Saving updates UCI only; restart the desktop (or use Switch & Restart above) to apply.'));
		var seenConfigured = false;
		for (var i = 0; i < sessions.length; i++) {
			var item = sessions[i];
			if (item.id == cfg.session)
				seenConfigured = true;
			o.value(item.id, item.available ? (item.title || item.id) : _('%s (not installed)').format(item.title || item.id));
		}
		if (!seenConfigured && cfg.session) {
			o.value(cfg.session, cfg.session);
		}
		if (sessions.length == 0 && !cfg.session) {
			o.value('', _('No desktop sessions installed'));
		}

		o = s.option(form.DummyValue, 'user', _('Desktop user'),
			_('Managed via <code>desktop-setup USER</code> over SSH so TPM2 keyring credentials, TLS certificates and device groups stay consistent.'));
		o.cfgvalue = function(section_id) {
			return uci.get('desktop', section_id, 'user') || _('Not configured');
		};

		o = s.option(form.Value, 'output', _('Display output'),
			_('DRM connector name or <code>auto</code>. Changing this option requires restarting the desktop.'));
		o.value('auto', _('auto (first connected display)'));
		for (var j = 0; j < outputs.length; j++)
			o.value(outputs[j], outputs[j]);
		o.default = 'auto';
		o.rmempty = false;
		o.validate = function(section_id, value) { return validateOutput(value); };

		o = s.option(form.Value, 'mode', _('Display mode'),
			_('<code>preferred</code> or <code>WIDTHxHEIGHT[@HZ]</code>, for example <code>1920x1080@60</code>. Applies before a custom monitor layout is saved in desktop settings.'));
		o.default = 'preferred';
		o.placeholder = 'preferred';
		o.rmempty = false;
		o.validate = function(section_id, value) { return validateMode(value); };

		var anySupportsKms = sessions.some(function(item) { return item.available && item.supports_kms_scheduling; });
		if (anySupportsKms || sessions.length == 0) {
			o = s.option(form.ListValue, 'kms_scheduling', _('Mutter KMS scheduling'),
				_('Applies to GNOME/Mutter via RealtimeKit. Requires restarting the desktop to take effect.'));
			o.value('high-priority', _('high-priority (default, nice -15)'));
			o.value('realtime', _('realtime (SCHED_RR 20)'));
			o.value('normal', _('normal (no elevation)'));
			o.default = 'high-priority';
		}

		o = s.option(form.Flag, 'rdp_enabled', _('Enable LAN RDP'),
			_('Expose LAN IPv4 RDP for the active desktop session after provisioning credentials with <code>desktop-rdp-setup USER</code>. Applies live without restarting the desktop.'));
		o.rmempty = false;

		o = s.option(form.DummyValue, 'rdp_port', _('RDP port'),
			_('Configured via <code>desktop-rdp-setup USER</code> over SSH.'));
		o.cfgvalue = function(section_id) {
			return uci.get('desktop', section_id, 'rdp_port') || '3389';
		};

		o = s.option(form.DummyValue, 'sunshine_capture', _('Sunshine capture mode'),
			_('Configured via <code>sunshine-setup USER --capture=portal|--enable-kms</code> over SSH.'));
		o.cfgvalue = function(section_id) {
			return uci.get('desktop', section_id, 'sunshine_capture') || 'portal';
		};

		this.statusBanner = E('div', { 'class': 'alert-message' }, [ _('Loading…') ]);
		this.driftText = E('span', {}, []);
		this.driftRestartBtn = E('button', {
			'class': 'cbi-button cbi-button-reload',
			'style': 'margin-left:1em',
			'click': ui.createHandlerFn(this, 'handleRestart')
		}, [ _('Restart desktop') ]);
		this.driftBanner = E('div', {
			'class': 'alert-message warning',
			'style': 'display:none'
		}, [ this.driftText, this.driftRestartBtn ]);

		this.cells = {
			activeSession: E('span', {}, [ '-' ]),
			user: E('span', {}, [ '-' ]),
			keyring: E('span', {}, [ '-' ]),
			lan: E('span', {}, [ '-' ]),
			rdp: E('span', {}, [ '-' ]),
			sunshine: E('span', {}, [ '-' ]),
			audio: E('span', {}, [ '-' ])
		};

		this.startBtn = E('button', {
			'class': 'cbi-button cbi-button-apply',
			'click': ui.createHandlerFn(this, 'handleStart')
		}, [ _('Start') ]);
		this.stopBtn = E('button', {
			'class': 'cbi-button cbi-button-negative',
			'click': ui.createHandlerFn(this, 'handleStop')
		}, [ _('Stop') ]);
		this.restartBtn = E('button', {
			'class': 'cbi-button cbi-button-reload',
			'click': ui.createHandlerFn(this, 'handleRestart')
		}, [ _('Restart') ]);

		this.switchSelect = E('select', {
			'class': 'cbi-input-select',
			'style': 'min-width:14em',
			'change': L.bind(this.syncButtons, this)
		}, []);
		this.switchBtn = E('button', {
			'class': 'cbi-button cbi-button-action',
			'style': 'margin-left:0.5em',
			'click': ui.createHandlerFn(this, 'handleSwitch')
		}, [ _('Switch & Restart') ]);

		this.logBox = E('textarea', {
			'class': 'cbi-input-textarea',
			'readonly': 'readonly',
			'wrap': 'off',
			'rows': 16,
			'style': 'width:100%;font-family:monospace;font-size:12px'
		}, [ '' ]);

		this.updateStatus(statusData);
		poll.add(L.bind(function() {
			return callStatus().catch(function(err) {
				return { ok: false, error: { code: 1, message: err.message || String(err) } };
			}).then(L.bind(this.updateStatus, this));
		}, this), 5);

		function statusRow(label, node) {
			return E('tr', { 'class': 'tr' }, [
				E('td', { 'class': 'td left', 'width': '33%' }, [ label ]),
				E('td', { 'class': 'td left' }, [ node ])
			]);
		}

		return Promise.all([ m.render(), this.readLog() ]).then(L.bind(function(res) {
			this.logBox.value = res[1];
			return E([], [
				E('div', { 'class': 'cbi-section' }, [
					E('h3', {}, [ _('Status') ]),
					this.statusBanner,
					this.driftBanner,
					E('table', { 'class': 'table' }, [
						statusRow(_('Active session'), this.cells.activeSession),
						statusRow(_('Desktop user'), this.cells.user),
						statusRow(_('Keyring'), this.cells.keyring),
						statusRow(_('LAN address'), this.cells.lan),
						statusRow(_('RDP'), this.cells.rdp),
						statusRow(_('Sunshine'), this.cells.sunshine),
						statusRow(_('Audio'), this.cells.audio)
					]),
					E('div', { 'class': 'cbi-value', 'style': 'margin-top:0.75em' }, [
						E('label', { 'class': 'cbi-value-title' }, [ _('Quick switch') ]),
						E('div', { 'class': 'cbi-value-field' }, [ this.switchSelect, this.switchBtn ])
					]),
					E('div', { 'class': 'cbi-page-actions', 'style': 'text-align:left' }, [
						this.startBtn, ' ', this.stopBtn, ' ', this.restartBtn
					])
				]),
				res[0],
				E('div', { 'class': 'cbi-section' }, [
					E('h3', {}, [ _('Service Log') ]),
					this.logBox,
					E('div', { 'class': 'cbi-page-actions', 'style': 'text-align:left' }, [
						E('button', {
							'class': 'cbi-button',
							'click': ui.createHandlerFn(this, 'handleLogRefresh')
						}, [ _('Refresh log') ])
					])
				])
			]);
		}, this));
	}
});
