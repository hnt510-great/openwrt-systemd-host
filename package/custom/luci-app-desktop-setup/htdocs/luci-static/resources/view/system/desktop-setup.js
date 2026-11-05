// SPDX-License-Identifier: Apache-2.0
'use strict';
'require view';
'require rpc';
'require ui';
'require dom';
'require poll';

var callStatus = rpc.declare({ object: 'luci.desktop-setup', method: 'status', expect: {} });
var callDefer = rpc.declare({ object: 'luci.desktop-setup', method: 'defer', expect: {} });
var callApply = rpc.declare({
	object: 'luci.desktop-setup', method: 'apply', expect: {},
	params: [ 'username', 'mode', 'password', 'rdp_password', 'keyring_password', 'capture',
		'confirm_restart', 'rdp', 'moonlight', 'containers', 'flatpak', 'virtual_machines' ]
});

var featureNames = {
	rdp: _('Remote desktop (RDP)'), moonlight: _('Moonlight streaming'),
	containers: _('Rootless containers'), flatpak: _('Flatpak applications'),
	virtual_machines: _('Virtual machine administration')
};
var stageNames = {
	account: _('Create account'), password: _('Set account password'), desktop: _('Configure GNOME'),
	rdp: _('Configure RDP credentials'), audio: _('Enable desktop audio'),
	moonlight: featureNames.moonlight, containers: featureNames.containers,
	flatpak: featureNames.flatpak, virtual_machines: featureNames.virtual_machines,
	container_access: _('Allow this account in LuCI Podman'), restart: _('Restart GNOME')
};
var errors = {
	busy: _('Another setup is running. Wait for it to finish.'),
	invalid_request: _('The setup request is invalid. Refresh and try again.'),
	invalid_username: _('Use 1–32 lowercase letters, digits, underscores or hyphens, starting with a letter or underscore.'),
	account_exists: _('This account already exists. Choose Use an existing account.'),
	invalid_existing_account: _('Choose an unlocked ordinary account with a home directory and login shell.'),
	existing_password_preserved: _('The existing account password is preserved. Leave that password field empty.'),
	invalid_password: _('A password is too long or contains an invalid control character.'),
	password_too_short: _('New passwords must contain at least 12 characters.'),
	rdp_password_required: _('Enter an RDP password for this account.'),
	keyring_password_required: _('Enter the existing login-keyring passphrase.'),
	restart_confirmation_required: _('Confirm that the desktop may be started or restarted.'),
	native_systemd_required: _('Boot the native-systemd image to configure GNOME.'),
	lan_required: _('Configure a LAN IPv4 address before setting up the desktop.'),
	missing_package: _('A selected setup helper is missing. Install the matching desktop packages first.'),
	helper_failed: _('A setup helper failed. Completed steps are retained; review the failed step and retry. Passwords and helper output are not logged.'),
	command_timeout: _('A setup helper timed out. Inspect the retained state before retrying.'),
	desktop_not_running: _('GNOME did not remain active. Check the connected display and the desktop journal before retrying.'),
	interrupted: _('Setup was interrupted. Completed steps are retained; review the account and retry.')
};
function errorText(code) { return errors[code] || _('Setup could not be completed.'); }
function field(title, input, help) {
	return E('div', { 'class': 'cbi-value' }, [
		E('label', { 'class': 'cbi-value-title', 'for': input.id }, [ title ]),
		E('div', { 'class': 'cbi-value-field' }, [ input, help ? E('div', { 'class': 'cbi-value-description' }, [ help ]) : '' ])
	]);
}
function normalizeBlocks(plan) {
	return Object.keys(featureNames).filter(function(key) { return plan[key]; });
}

return view.extend({
	load: function() { return callStatus(); },
	render: function(data) {
		this.data = data;
		this.page = data.running ? 3 : 0;
		this.inputs = {};
		this.root = E('div');
		var accounts = data.accounts || [];
		var preferred = (data.job && (data.job.status == 'failed' || data.job.status == 'interrupted')) ? data.job.username : data.username;
		var existing = accounts.filter(function(a) { return a.username == preferred; })[0];
		this.plan = { mode: existing ? 'existing' : 'create', username: existing ? existing.username : '',
			password: '', password_confirm: '', rdp_password: '', rdp_confirm: '', keyring_password: '',
			capture: data.capture || 'portal' };
		Object.keys(featureNames).forEach(function(key) {
			this.plan[key] = data.features && key in data.features ? data.features[key] : true;
		}, this);
		this.draw();
		if (data.running) this.startPolling();
		return this.root;
	},

	input: function(name, type, value) {
		var input = E('input', { id: 'setup-' + name, type: type || 'text',
			'class': 'cbi-input-text', autocomplete: type == 'password' ? 'new-password' : 'off',
			maxlength: name == 'username' ? 32 : (name == 'keyring_password' ? 1024 : 256) });
		input.value = value || '';
		this.inputs[name] = input;
		return input;
	},

	selectedAccount: function() {
		return (this.data.accounts || []).filter(function(a) { return a.username == this.plan.username; }, this)[0];
	},

	accountPage: function() {
		var self = this, p = this.plan;
		var mode = E('select', { id: 'setup-mode', 'class': 'cbi-input-select', change: function() {
			p.mode = this.value;
			if (p.mode == 'existing' && !self.selectedAccount()) p.username = (self.data.accounts[0] || {}).username || '';
			self.clearPasswords(); self.draw();
		} }, [ E('option', { value: 'create' }, [ _('Create a new account') ]),
			E('option', { value: 'existing', disabled: !(this.data.accounts || []).length }, [ _('Use an existing account') ]) ]);
		mode.value = p.mode;
		var children = [ field(_('Account'), mode) ];
		if (p.mode == 'create') {
			children.push(field(_('Username'), this.input('username', 'text', p.username), errors.invalid_username));
		} else {
			var users = E('select', { id: 'setup-user', 'class': 'cbi-input-select', change: function() {
				p.username = this.value; self.clearPasswords(); self.draw();
			} }, (this.data.accounts || []).map(function(a) {
				return E('option', { value: a.username }, [ a.username + ' (UID ' + a.uid + ')' ]);
			}));
			users.value = p.username;
			children.push(field(_('Username'), users, _('Existing home directories, passwords and personal settings are preserved.')));
		}
		var account = this.selectedAccount();
		if (p.mode == 'create' || (account && account.recoverable)) {
			children.push(field(_('Account password'), this.input('password', 'password', p.password), _('At least 12 characters. This is the Unix/SSH password.')));
			children.push(field(_('Confirm account password'), this.input('password_confirm', 'password', p.password_confirm)));
		}
		if (p.mode == 'existing' && account && account.keyring_required)
			children.push(field(_('Existing login-keyring passphrase'), this.input('keyring_password', 'password', p.keyring_password),
				_('Needed once to enroll unattended unlock of this existing keyring.')));
		return E('div', {}, children);
	},

	featuresPage: function() {
		var self = this, p = this.plan, available = (this.data.platform || {}).available || {};
		var children = [ E('p', {}, [ _('Local GNOME is configured for the selected account. Unchecked features keep their existing settings; this wizard does not revoke previous permissions.') ]) ];
		Object.keys(featureNames).forEach(function(key) {
			var checkbox = E('input', { id: 'setup-' + key, type: 'checkbox', disabled: !available[key] });
			checkbox.checked = !!p[key] && !!available[key];
			self.inputs[key] = checkbox;
			children.push(field(featureNames[key], checkbox, available[key] ? '' : _('Matching package is not installed.')));
		});
		children.push(field(_('RDP password'), this.input('rdp_password', 'password', p.rdp_password),
			_('At least 12 characters. Leave blank only to preserve RDP already configured for this same account.')));
		children.push(field(_('Confirm RDP password'), this.input('rdp_confirm', 'password', p.rdp_confirm)));
		var capture = E('select', { id: 'setup-capture', 'class': 'cbi-input-select' }, [
			E('option', { value: 'portal' }, [ _('GNOME portal') ]), E('option', { value: 'kms' }, [ _('KMS capture') ]) ]);
		capture.value = p.capture; this.inputs.capture = capture;
		children.push(field(_('Moonlight capture'), capture,
			_('Portal capture may ask you to select a screen in GNOME. KMS grants the enrolled Sunshine executable its capture capability.')));
		return E('div', {}, children);
	},

	reviewPage: function() {
		var self = this, p = this.plan;
		var confirmation = E('input', { id: 'setup-confirm', type: 'checkbox', change: function() {
			self.applyButton.disabled = !this.checked || !L.hasViewPermission();
		} });
		return E('div', {}, [
			E('p', {}, [ _('Account:') + ' ' + p.username ]),
			E('ul', {}, [ E('li', {}, [ _('Start the local GNOME session') ]) ].concat(normalizeBlocks(p).map(function(key) {
				return E('li', {}, [ featureNames[key] ]);
			}))),
			E('p', {}, [ _('Container enrollment allocates subordinate IDs, enables user linger and grants LuCI Podman access. VM enrollment grants full local VM administration with privileges comparable to root. No sudo membership is granted.') ]),
			field(_('Apply and restart desktop'), confirmation,
				_('I agree to start or restart GNOME. Open desktop applications will close; router network configuration is not changed.'))
		]);
	},

	progressPage: function() {
		var job = this.data.job || {}, platform = this.data.platform || {};
		var children = [ E('p', {}, [ this.data.running ? _('Configuring the desktop. You may leave this page and return to view progress.') :
			(job.status == 'done' ? _('Configuration completed. Verify the desktop and remote clients before relying on unattended startup.') : errorText(job.error || 'interrupted')) ]) ];
		children.push(E('ul', {}, (job.steps || []).map(function(step) {
			return E('li', {}, [ (stageNames[step.id] || _('Setup')) + ': ' +
				(step.status == 'done' ? _('Done') : step.status == 'failed' ? _('Failed') : _('Running')) ]);
		})));
		if (job.status == 'done') {
			children.push(E('p', {}, [ _('RDP uses the selected username and separate RDP password. Moonlight needs its own Web credentials and PIN pairing.') ]));
			if (this.data.group_refresh_required) children.push(E('p', {}, [ _('Some existing user services still have old group memberships. Re-login for new shells; restart the user manager or reboot during maintenance to refresh all services. Existing containers are not stopped by this wizard.') ]));
			if (this.data.rdp_enabled && this.data.rdp_fingerprint) children.push(E('p', {}, [
				_('RDP TLS certificate fingerprint (SHA256):'), E('br'),
				E('code', { style: 'word-break:break-all' }, [ this.data.rdp_fingerprint ])
			]));
			if (/^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/.test(platform.lan_address || '')) {
				if (this.data.rdp_enabled) children.push(E('p', {}, [ _('RDP address:') + ' ' + platform.lan_address + ':' + (this.data.rdp_port || 3389) ]));
				if ((this.data.features || {}).moonlight) children.push(E('p', {}, [ E('a', {
					href: 'https://' + platform.lan_address + ':47990', target: '_blank', rel: 'noopener noreferrer'
				}, [ _('Open Sunshine Web UI') ]) ]));
			}
			children.push(E('p', {}, [ _('After a fresh ordinary-user login, use podman info, flatpak list --user and virsh -c qemu:///system list --all. Add Flathub and create your own containers and virtual machines as needed. New Fcitx profiles use Ctrl+Space.') ]));
		}
		if (job.status == 'failed' || job.status == 'interrupted')
			children.push(E('p', {}, [ _('No accounts or application data were removed. Choose the existing account when retrying; a wizard-created locked account can finish password setup. Review journalctl -u openwrt-desktop.service for desktop startup failures.') ]));
		return E('div', {}, children);
	},

	draw: function() {
		this.inputs = {};
		var self = this, platform = this.data.platform || {}, titles = [ _('Account'), _('Features'), _('Review'), _('Result') ];
		var body = [ E('h2', {}, [ _('Desktop Setup Wizard') ]),
			E('p', {}, [ _('Create or select an ordinary user, then enroll desktop and application features. You can reopen this wizard at System → Desktop Setup Wizard.') ]),
			E('p', {}, [ titles.map(function(title, index) { return (index == self.page ? '● ' : '') + title; }).join(' → ') ]) ];
		var ready = platform.native && platform.lan_address && (platform.available || {}).desktop;
		if (!ready) body.push(E('div', { 'class': 'alert-message warning' }, [
			!platform.native ? errors.native_systemd_required : !platform.lan_address ? errors.lan_required : errors.missing_package ]));
		if (this.page < 3) body.push(E('p', {}, [ _('Setup is optional. Skip setup to stop automatic prompts; you can return at System → Desktop Setup Wizard.') ]));
		if (this.data.completed && this.page < 3) body.push(E('p', {}, [ _('Setup has already completed. You can enroll additional features or configure another ordinary account.') ]));
		if (!this.data.running && (this.data.job || {}).status == 'failed' && this.page < 3)
			body.push(E('div', { 'class': 'alert-message warning' }, [ errorText(this.data.job.error) ]));
		if (this.message) body.push(E('div', { 'class': 'alert-message warning' }, [ this.message ]));
		body.push(this.page == 0 ? this.accountPage() : this.page == 1 ? this.featuresPage() : this.page == 2 ? this.reviewPage() : this.progressPage());
		var buttons = [];
		if (this.page > 0 && this.page < 3) buttons.push(E('button', { 'class': 'cbi-button', click: function() {
			self.readFields(); self.message = ''; self.page--; self.draw();
		} }, [ _('Back') ]));
		if (this.page < 2) buttons.push(E('button', { 'class': 'cbi-button cbi-button-positive', disabled: !ready || !L.hasViewPermission(), click: function() {
			self.next();
		} }, [ _('Next') ]));
		if (this.page == 2) {
			this.applyButton = E('button', { 'class': 'cbi-button cbi-button-apply', disabled: true, click: function() { self.apply(); } }, [ _('Apply configuration') ]);
			buttons.push(this.applyButton);
		}
		if (this.page < 3) buttons.push(E('button', { 'class': 'cbi-button', disabled: !L.hasViewPermission(), click: function() {
			return callDefer().then(function(result) {
				if (!result.success) throw new Error(errorText(result.error));
				window.location.assign(L.url('admin/status/overview'));
			}).catch(function(error) { ui.addNotification(null, E('p', {}, [ error.message ]), 'error'); });
		} }, [ _('Skip setup') ]));
		if (this.page == 3 && !this.data.running) {
			buttons.push(E('button', { 'class': 'cbi-button', click: function() {
				self.page = 0; self.message = ''; self.plan.mode = 'existing';
				self.plan.username = (self.data.job || {}).username || self.data.username;
				if (!self.selectedAccount()) self.plan.mode = 'create';
				self.draw();
			} }, [ _('Configure again') ]));
			buttons.push(E('a', { 'class': 'cbi-button', href: L.url('admin/status/overview') }, [ _('Go to overview') ]));
		}
		body.push(E('div', { 'class': 'cbi-page-actions' }, buttons));
		dom.content(this.root, body);
	},

	readFields: function() {
		Object.keys(this.inputs).forEach(function(key) {
			var input = this.inputs[key]; this.plan[key] = input.type == 'checkbox' ? input.checked : input.value;
		}, this);
	},

	next: function() {
		this.readFields(); this.message = '';
		var p = this.plan, account = this.selectedAccount();
		if (this.page == 0) {
			if (!/^[a-z_][a-z0-9_-]{0,31}$/.test(p.username) || p.username.trim() != p.username) this.message = errors.invalid_username;
			else if (p.mode == 'create' || (account && account.recoverable)) {
				if (p.password.length < 12) this.message = errors.password_too_short;
				else if (p.password != p.password_confirm) this.message = _('The passwords do not match.');
			}
			if (!this.message && p.mode == 'existing' && account && account.keyring_required && !p.keyring_password)
				this.message = errors.keyring_password_required;
		} else {
			if (!p.rdp) { p.rdp_password = ''; p.rdp_confirm = ''; }
			if (p.rdp && !p.rdp_password && !(this.data.username == p.username && this.data.rdp_enabled)) this.message = errors.rdp_password_required;
			else if (p.rdp && p.rdp_password && p.rdp_password.length < 12) this.message = errors.password_too_short;
			else if (p.rdp && p.rdp_password != p.rdp_confirm) this.message = _('The passwords do not match.');
		}
		if (!this.message) this.page++;
		this.draw();
	},

	clearPasswords: function() {
		[ 'password', 'password_confirm', 'rdp_password', 'rdp_confirm', 'keyring_password' ].forEach(function(key) {
			this.plan[key] = ''; if (this.inputs[key]) this.inputs[key].value = '';
		}, this);
	},

	apply: function() {
		var self = this, p = this.plan;
		this.applyButton.disabled = true;
		return callApply(p.username, p.mode, p.password, p.rdp_password, p.keyring_password, p.capture,
			true, p.rdp, p.moonlight, p.containers, p.flatpak, p.virtual_machines).then(function(result) {
			self.clearPasswords();
			if (!result.success) throw new Error(errorText(result.error));
			return callStatus().then(function(data) {
				self.data = data; self.page = 3; self.message = ''; self.draw(); if (data.running) self.startPolling();
			});
		}).catch(function(error) {
			self.clearPasswords(); self.message = error.message; self.draw();
		});
	},

	startPolling: function() {
		if (this.poller) return;
		var self = this;
		this.poller = function() {
			return callStatus().then(function(data) {
				self.data = data; self.draw();
				if (!data.running) { poll.remove(self.poller); self.poller = null; }
			}).catch(function() { self.message = _('Status is temporarily unavailable. Reopen the wizard to resume monitoring.'); self.draw(); });
		};
		poll.add(this.poller, 2);
	},

	handleSave: null,
	handleSaveApply: null,
	handleReset: null
});
