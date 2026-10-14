'use strict';
'require view';
'require baseclass';
'require rpc';
'require ui';
'require poll';

var accounts = rpc.declare({ object: 'luci.podman', method: 'accounts', expect: {} });
var list = rpc.declare({ object: 'luci.podman', method: 'list', params: [ 'user', 'resource' ], expect: {} });
var detail = rpc.declare({ object: 'luci.podman', method: 'detail', params: [ 'user', 'resource', 'id', 'logs' ], expect: {} });
var action = rpc.declare({ object: 'luci.podman', method: 'action', params: [ 'user', 'resource', 'action', 'id', 'options' ], expect: {} });
var job = rpc.declare({ object: 'luci.podman', method: 'job', params: [ 'user', 'job' ], expect: {} });

function check(result) {
	if (!result || !result.success) throw new Error(result && result.error || _('Podman request failed.'));
	return result;
}
function value(row, key) {
	return row[key] != null ? row[key] : row[key.charAt(0).toLowerCase() + key.slice(1)];
}
function display(v) {
	if (v == null) return '—';
	if (Array.isArray(v)) return v.map(display).join(', ');
	if (typeof v == 'object') return JSON.stringify(v);
	return String(v);
}
function lines(v) { return v.split('\n').map(function(s) { return s.trim(); }).filter(Boolean); }
function button(label, fn, style) {
	return E('button', { 'class': 'btn ' + (style || 'cbi-button-action'), 'click': ui.createHandlerFn(null, fn) }, label);
}

var methods = {
	resource: 'info',
	title: _('Overview'),
	handleSave: null,
	handleSaveApply: null,
	handleReset: null,

	load: function() { return accounts(); },

	render: function(result) {
		check(result);
		var users = result.accounts.filter(function(a) { return a.allowed; });
		var selected = null;
		try { selected = window.localStorage.getItem('luci-podman-user'); } catch (e) {}
		this.user = users.some(function(a) { return a.user == selected; }) ? selected : (users[0] || {}).user;
		this.busy = false;
		this.body = E('div');
		this.state = E('span');
		var selector = E('select', { 'class': 'cbi-input-select', 'change': L.bind(function(ev) {
			this.user = ev.target.value;
			this.body.replaceChildren(E('p', {}, _('Loading…')));
			try { window.localStorage.setItem('luci-podman-user', this.user); } catch (e) {}
			this.refresh();
		}, this) }, users.map(function(a) {
			return E('option', { value: a.user, selected: a.user == this.user ? true : null }, a.user + ' (UID ' + a.uid + ')');
		}, this));
		var toolbar = [ E('label', {}, [ _('Rootless account'), ' ', selector ]), ' ',
			button(_('Refresh'), L.bind(this.refresh, this)), ' ' ];
		if (this.resource != 'info' && L.hasViewPermission()) toolbar.push(button(this.resource == 'images' ? _('Pull image') : _('Create'), L.bind(this.createDialog, this)), ' ');
		toolbar.push(this.state);
		var root = E('div', {}, [ E('h2', {}, _('Rootless Podman') + ' — ' + this.title),
			E('p', {}, _('Each account has its own containers, images, networks and volumes. Operations run as the selected ordinary user.')) ]);
		if (!users.length) {
			root.appendChild(E('p', { 'class': 'alert-message warning' }, [
				_('No rootless account is allowed. Enroll an existing account with podman-rootless-setup, then select it in Configuration.'), ' ',
				E('a', { href: L.url('admin/services/podman/configuration') }, _('Configuration')) ]));
			return root;
		}
		root.appendChild(E('div', { 'class': 'cbi-section' }, toolbar));
		root.appendChild(this.body);
		this.refresh();
		poll.add(L.bind(this.refresh, this), 10);
		return root;
	},

	refresh: function() {
		if (this.loading || !this.user) return Promise.resolve();
		var user = this.user;
		this.loading = true;
		return list(user, this.resource).then(check).then(L.bind(function(result) {
			if (user != this.user) return;
			this.state.textContent = _('Updated') + ' ' + new Date().toLocaleTimeString();
			this.body.replaceChildren(this.resource == 'info' ? this.overview(result.data) : this.table(result.data || []));
		}, this)).catch(L.bind(function(e) {
			if (user != this.user) return;
			this.state.textContent = _('Unavailable');
			this.body.replaceChildren(E('p', { 'class': 'alert-message warning' }, e.message));
		}, this)).finally(L.bind(function() {
			this.loading = false;
			if (user != this.user) return this.refresh();
		}, this));
	},

	overview: function(info) {
		var host = info.host || {}, store = info.store || {}, version = info.version || {};
		var rows = [ [ _('Podman version'), version.Version || version.version ],
			[ _('Rootless'), host.security && host.security.rootless ],
			[ _('Cgroup manager'), host.cgroupManager ], [ _('OCI runtime'), host.ociRuntime && host.ociRuntime.name ],
			[ _('Storage driver'), store.graphDriverName ], [ _('Storage path'), store.graphRoot ],
			[ _('Runtime path'), store.runRoot ], [ _('Containers'), store.containerStore && store.containerStore.number ],
			[ _('Running'), store.containerStore && store.containerStore.running ],
			[ _('Images'), store.imageStore && store.imageStore.number ] ];
		return E('table', { 'class': 'table' }, rows.map(function(row) {
			return E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, row[0]), E('td', { 'class': 'td' }, display(row[1])) ]);
		}));
	},

	table: function(data) {
		var columns = {
			containers: [ [ _('Name'), 'Names' ], [ _('Container image'), 'Image' ], [ _('Container state'), 'State' ], [ _('Runtime status'), 'Status' ], [ _('Ports'), 'Ports' ] ],
			pods: [ [ _('Name'), 'Name' ], [ _('Status'), 'Status' ], [ _('Containers'), 'Containers' ] ],
			images: [ [ _('Tags'), 'Names' ], [ _('ID'), 'Id' ], [ _('Size'), 'Size' ], [ _('Created'), 'Created' ] ],
			networks: [ [ _('Name'), 'name' ], [ _('Driver'), 'driver' ], [ _('Interface'), 'network_interface' ] ],
			volumes: [ [ _('Name'), 'Name' ], [ _('Driver'), 'Driver' ], [ _('Mount point'), 'Mountpoint' ] ]
		}[this.resource];
		var resource = { containers: 'container', pods: 'pod', images: 'image', networks: 'network', volumes: 'volume' }[this.resource];
		var table = E('table', { 'class': 'table cbi-section-table' }, [ E('tr', { 'class': 'tr' },
			columns.map(function(c) { return E('th', { 'class': 'th' }, c[0]); }).concat(E('th', { 'class': 'th' }, _('Actions')))) ]);
		data.forEach(function(row) {
			var id = resource == 'volume' || resource == 'network' ? value(row, 'Name') : (value(row, 'Id') || value(row, 'ID'));
			var buttons = [ button(_('Inspect'), L.bind(this.showDetail, this, resource, id, false)) ];
			if (resource == 'container') buttons.push(button(_('Logs'), L.bind(this.showDetail, this, resource, id, true)));
			if (resource == 'container' && L.hasViewPermission()) {
				var state = value(row, 'State');
				var actions = state == 'running' ? [ [ _('Stop'), 'stop' ], [ _('Restart'), 'restart' ], [ _('Pause'), 'pause' ] ] :
					state == 'paused' ? [ [ _('Unpause'), 'unpause' ] ] : [ [ _('Start'), 'start' ] ];
				actions.forEach(function(a) { buttons.push(button(a[0], L.bind(this.execute, this, resource, a[1], id, {}))); }, this);
			}
			if (resource == 'pod' && L.hasViewPermission()) [ [ _('Start'), 'start' ], [ _('Stop'), 'stop' ], [ _('Restart'), 'restart' ] ].forEach(function(a) {
				buttons.push(button(a[0], L.bind(this.execute, this, resource, a[1], id, {})));
			}, this);
			if (L.hasViewPermission()) buttons.push(button(_('Remove'), L.bind(this.confirmRemove, this, resource, id), 'cbi-button-negative'));
			var cells = columns.map(function(c) {
				var v = value(row, c[1]);
				if (this.resource == 'images' && c[1] == 'Names') v = v || value(row, 'RepoTags');
				if (this.resource == 'images' && c[1] == 'Id') v = v ? String(v).substring(0, 12) : v;
				if (this.resource == 'pods' && c[1] == 'Containers' && Array.isArray(v)) v = v.length;
				if (this.resource == 'images' && c[1] == 'Size' && typeof v == 'number') v = '%1024.2mB'.format(v);
				if (this.resource == 'containers' && c[1] == 'Ports') v = (v || []).map(function(p) {
					return (p.host_ip || '') + ':' + (p.host_port || '') + ' → ' + p.container_port + '/' + p.protocol;
				});
				return E('td', { 'class': 'td' }, display(v));
			}, this);
			cells.push(E('td', { 'class': 'td cbi-section-actions' }, buttons));
			table.appendChild(E('tr', { 'class': 'tr' }, cells));
		}, this);
		if (!data.length) table.appendChild(E('tr', { 'class': 'tr' }, E('td', { 'class': 'td', colspan: columns.length + 1 }, _('No resources found.'))));
		return table;
	},

	showDetail: function(resource, id, logs) {
		return detail(this.user, resource, id, logs).then(check).then(function(result) {
			ui.showModal(logs ? _('Container logs') : _('Inspect'), [
				E('pre', { style: 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:65vh;overflow:auto' },
					typeof result.data == 'string' ? result.data : JSON.stringify(result.data, null, 2)),
				E('div', { 'class': 'right' }, button(_('Close'), ui.hideModal)) ]);
		});
	},

	confirmRemove: function(resource, id) {
		var user = this.user;
		ui.showModal(_('Remove resource'), [ E('p', {}, _('Remove %s from account %s? Removal is permanent. Running containers and resources in use will not be forcibly removed.').format(id, this.user)),
			E('div', { 'class': 'right' }, [ button(_('Cancel'), ui.hideModal), ' ',
				button(_('Remove'), L.bind(function() { ui.hideModal(); return this.execute(resource, 'rm', id, {}, user); }, this), 'cbi-button-negative') ]) ]);
	},

	execute: function(resource, operation, id, options, selectedUser) {
		if (!L.hasViewPermission()) return Promise.reject(new Error(_('Permission denied.')));
		if (selectedUser && selectedUser != this.user) return Promise.reject(new Error(_('Account changed. Refresh and try again.')));
		if (this.busy) return Promise.reject(new Error(_('An operation is already running in this page.')));
		var user = this.user;
		this.busy = true;
		return action(user, resource, operation, id || '', JSON.stringify(options)).then(check).then(L.bind(function(result) {
			var output = E('pre', { style: 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:60vh;overflow:auto' }, _('Operation running…'));
			ui.showModal(_('Podman operation') + ' — ' + user, [ output,
				E('p', {}, _('Operations continue if this dialog is closed. Image pulls can take up to five minutes.')),
				E('div', { 'class': 'right' }, button(_('Close'), ui.hideModal)) ]);
			return new Promise(function(resolve, reject) {
				function update() {
					job(user, result.job).then(check).then(function(status) {
						output.textContent = status.output || _('Operation running…');
						if (!status.done) { window.setTimeout(update, 1500); return; }
						output.textContent = (status.code == 0 ? _('Completed') : _('Failed (exit code %s)').format(status.code)) + '\n' + status.output;
						if (status.code == 0) resolve(); else reject(new Error(status.output || _('Podman operation failed.')));
					}).catch(reject);
				}
				update();
			});
		}, this)).finally(L.bind(function() { this.busy = false; return this.refresh(); }, this));
	},

	createDialog: function() {
		var user = this.user;
		var resource = { containers: 'container', pods: 'pod', images: 'image', networks: 'network', volumes: 'volume' }[this.resource];
		var fields = {}, content = [];
		function field(key, label, multiline, placeholder) {
			fields[key] = E(multiline ? 'textarea' : 'input', { id: 'podman-create-' + key, 'class': 'cbi-input-text', style: 'width:100%', rows: 3, placeholder: placeholder || '' });
			content.push(E('div', { 'class': 'cbi-value' }, [ E('label', { 'class': 'cbi-value-title', 'for': 'podman-create-' + key }, label),
				E('div', { 'class': 'cbi-value-field' }, fields[key]) ]));
		}
		if (resource != 'image') field('name', _('Name'));
		if (resource == 'image' || resource == 'container') field('image', _('Image reference'), false, 'docker.io/library/alpine:3.23');
		if (resource == 'pod') {
			field('infra_image', _('Infra image (optional)'));
			field('infra_command', _('Infra command (optional)'));
			content.push(E('p', {}, _('An empty infra image creates a pod that groups containers without sharing namespaces. Add containers before starting it. Specify an infra image to share network, IPC and UTS namespaces.')));
		}
		if (resource == 'container') {
			content.push(E('p', {}, _('Pull the image first. Create makes a stopped container; use Start afterward. Each command argument occupies one line, without shell quoting.')));
			field('command', _('Command arguments (one per line)'), true, 'sleep\n3600');
			field('ports', _('Published ports (one per line)'), true, '8080:80/tcp');
			field('env', _('Environment (one KEY=value per line)'), true);
			field('volumes', _('Volumes (one per line)'), true, 'data:/data:rw');
			field('network', _('Network (empty uses the rootless default)'));
			field('pod', _('Pod (optional)'));
			fields.restart = E('select', { 'class': 'cbi-input-select' }, [ 'no', 'on-failure', 'always', 'unless-stopped' ].map(function(s) { return E('option', { value: s }, s); }));
			content.push(E('div', { 'class': 'cbi-value' }, [ E('label', { 'class': 'cbi-value-title' }, _('Restart policy')), E('div', { 'class': 'cbi-value-field' }, fields.restart) ]));
			content.push(E('p', {}, _('Restart policy applies while Podman is running. Boot autostart requires separate user service configuration. Rootless ports below 1024 may be restricted by the host.')));
		}
		content.push(E('div', { 'class': 'right' }, [ button(_('Cancel'), ui.hideModal), ' ', button(resource == 'image' ? _('Pull image') : _('Create'), L.bind(function() {
			var options = {};
			Object.keys(fields).forEach(function(k) { options[k] = [ 'command', 'ports', 'env', 'volumes' ].indexOf(k) >= 0 ? lines(fields[k].value) : fields[k].value.trim(); });
			ui.hideModal();
			return this.execute(resource, resource == 'image' ? 'pull' : 'create', '', options, user);
		}, this)) ]));
		ui.showModal(resource == 'image' ? _('Pull image') : _('Create'), content);
	}
};

// Shared modules are instantiated by LuCI. Only the actual page should
// instantiate a view, otherwise loading this dependency renders a second view.
return baseclass.extend({
	makeView: function(resource, title) {
		return view.extend(Object.assign({}, methods, { resource: resource, title: title }));
	}
});
