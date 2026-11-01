// SPDX-License-Identifier: GPL-2.0-only
'use strict';
'require view';
'require form';
'require fs';
'require poll';
'require rpc';
'require uci';
'require ui';
'require tools.widgets as widgets';

var LOG = '/var/log/daed/daed.log';

var callServiceList = rpc.declare({
	object: 'service',
	method: 'list',
	params: [ 'name' ],
	expect: { '': {} }
});

function isRunning(list) {
	var instances = ((list || {}).daed || {}).instances || {};
	return Object.keys(instances).some(function(name) {
		return !!(instances[name] && instances[name].running);
	});
}

function passwallEnabled() {
	var global = uci.sections('passwall', 'global')[0];
	return !!(global && global.enabled == '1');
}

// Returns { host, port } for "host:port", "[v6]:port" or ":port", else null.
function parseListen(value) {
	var text = String(value == null ? '' : value).trim();
	var m = text.match(/^\[([^\]]*)\]:(\d{1,5})$/) || text.match(/^([^:\[\]]*):(\d{1,5})$/);
	if (!m || +m[2] < 1 || +m[2] > 65535)
		return null;
	return { host: m[1], port: m[2] };
}

// URL of the dashboard as seen from this browser, or null when the listener
// cannot be reached from here (loopback only or an invalid address).
function dashboardURL(listen, pageHost) {
	var parsed = parseListen(listen);
	if (!parsed)
		return null;
	var host = parsed.host;
	if (host == '127.0.0.1' || host == '::1' || host == 'localhost')
		return null;
	if (host == '' || host == '0.0.0.0' || host == '::')
		host = pageHost;
	if (host.indexOf(':') >= 0 && host.charAt(0) != '[')
		host = '[' + host + ']';
	return 'http://' + host + ':' + parsed.port + '/';
}

function statusInfo(running, enabled, passwall) {
	if (running)
		return { cls: 'notice', text: _('daed is running.') };
	if (enabled && passwall)
		return { cls: 'warning', text: _('daed is enabled but not running because Passwall is enabled. daed refuses to run alongside Passwall; disable Passwall first.') };
	if (enabled)
		return { cls: 'warning', text: _('daed is enabled but not running. Check the log below.') };
	return { cls: '', text: _('daed is disabled.') };
}

return view.extend({
	load: function() {
		return Promise.all([
			callServiceList('daed').catch(function() { return {}; }),
			uci.load('daed'),
			uci.load('passwall').catch(function() { return null; })
		]);
	},

	readLog: function() {
		return fs.exec('/usr/bin/tail', [ '-n', '200', LOG ]).then(function(res) {
			return (res.code == 0 && res.stdout) ? res.stdout : _('No log yet.');
		}).catch(function(err) {
			return _('Unable to read the log: %s').format(err.message || err);
		});
	},

	updateStatus: function(list) {
		var enabled = uci.get('daed', 'config', 'enabled') == '1';
		var info = statusInfo(isRunning(list), enabled, passwallEnabled());
		this.status.className = 'alert-message ' + info.cls;
		this.status.textContent = info.text;
		var listen = uci.get('daed', 'config', 'listen_addr') || '0.0.0.0:2023';
		this.renderDashboardLink(dashboardURL(listen, window.location.hostname), isRunning(list));
	},

	// The link stays visible whenever the address is reachable from this
	// browser; while daed is stopped it is shown with a hint instead.
	renderDashboardLink: function(url, running) {
		var children;
		if (!url) {
			children = [ _('The dashboard listens on loopback only; it is not reachable from this browser.') ];
		} else {
			children = [
				E('a', {
					'class': 'cbi-button cbi-button-action',
					'href': url,
					'target': '_blank',
					'rel': 'noopener noreferrer'
				}, [ _('Open dashboard') ]),
				' ',
				E('a', { 'href': url, 'target': '_blank', 'rel': 'noopener noreferrer' }, [ url ])
			];
			if (!running)
				children.push(' ', E('em', {}, [ _('(daed is not running)') ]));
		}
		var key = JSON.stringify([ url, running ]);
		if (key == this.dashboardKey)
			return;
		this.dashboardKey = key;
		this.dashboard.replaceChildren.apply(this.dashboard, children);
	},

	handleRestart: function(ev) {
		var button = ev.currentTarget;
		button.disabled = true;
		return fs.exec('/etc/init.d/daed', [ 'restart' ]).catch(function(err) {
			ui.addNotification(null, E('p', {}, [ _('Restart failed: %s').format(err.message || err) ]), 'error');
		}).then(L.bind(function() {
			button.disabled = null;
			return callServiceList('daed').catch(function() { return {}; });
		}, this)).then(L.bind(this.updateStatus, this));
	},

	handleLogRefresh: function() {
		return this.readLog().then(L.bind(function(text) {
			this.log.value = text;
			this.log.scrollTop = this.log.scrollHeight;
		}, this));
	},

	render: function(data) {
		var m, s, o;
		var writable = L.hasViewPermission ? L.hasViewPermission() : true;

		m = new form.Map('daed', _('daed'),
			_('daed is the dae eBPF transparent proxy with its own web dashboard. Nodes, groups, routing and DNS are configured in the dashboard; this page only controls the service.'));

		s = m.section(form.NamedSection, 'config', 'daed', _('Service'));
		s.addremove = false;

		o = s.option(form.Flag, 'enabled', _('Enable'),
			_('Start daed now and at boot. daed and Passwall both intercept forwarded traffic, so daed does not start while Passwall is enabled.'));
		o.rmempty = false;

		o = s.option(form.Value, 'listen_addr', _('Dashboard address'),
			_('Address and port of the dashboard and GraphQL API, for example <code>0.0.0.0:2023</code>. The WAN zone rejects it; create the admin account right after the first start, because the first visitor creates it.'));
		o.placeholder = '0.0.0.0:2023';
		o.rmempty = false;
		o.validate = function(section_id, value) {
			return parseListen(value) ? true : _('Expecting host:port, [IPv6]:port or :port');
		};

		o = s.option(widgets.DeviceSelect, 'default_lan_interface', _('Default LAN interface'),
			_('LAN interfaces that daed gives a new config created without one, such as the default config made when the dashboard is first opened. Without a LAN interface dae proxies only the router\'s own traffic. Existing configs are not changed; edit them under Global in the dashboard. Empty means <code>br-lan</code>.'));
		o.multiple = true;
		o.noaliases = true;
		o.default = 'br-lan';

		o = s.option(form.Value, 'log_maxsize', _('Log size (MB)'),
			_('Rotate /var/log/daed/daed.log at this size. The log is kept in RAM.'));
		o.datatype = 'range(1,64)';
		o.placeholder = '5';

		o = s.option(form.Value, 'log_maxbackups', _('Rotated logs kept'));
		o.datatype = 'range(0,10)';
		o.placeholder = '1';

		this.status = E('div', { 'class': 'alert-message' }, [ _('Loading…') ]);
		this.dashboard = E('span', {}, []);
		var restart = E('button', {
			'class': 'cbi-button cbi-button-reload',
			'disabled': writable ? null : true,
			'click': ui.createHandlerFn(this, 'handleRestart')
		}, [ _('Restart') ]);
		this.log = E('textarea', {
			'class': 'cbi-input-textarea',
			'readonly': 'readonly',
			'wrap': 'off',
			'rows': 20,
			'style': 'width:100%;font-family:monospace;font-size:12px'
		}, [ '' ]);

		this.updateStatus(data[0]);
		poll.add(L.bind(function() {
			return callServiceList('daed').catch(function() { return {}; }).then(L.bind(this.updateStatus, this));
		}, this), 5);

		return Promise.all([ m.render(), this.readLog() ]).then(L.bind(function(res) {
			this.log.value = res[1];
			return E([], [
				res[0],
				E('div', { 'class': 'cbi-section' }, [
					E('h3', {}, [ _('Status') ]),
					this.status,
					E('div', { 'class': 'cbi-value' }, [
						E('label', { 'class': 'cbi-value-title' }, [ _('Dashboard') ]),
						E('div', { 'class': 'cbi-value-field' }, [ this.dashboard ])
					]),
					E('div', { 'class': 'cbi-page-actions', 'style': 'text-align:left' }, [ restart ])
				]),
				E('div', { 'class': 'cbi-section' }, [
					E('h3', {}, [ _('Log') ]),
					this.log,
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
