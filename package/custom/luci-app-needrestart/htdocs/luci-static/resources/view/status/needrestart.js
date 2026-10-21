// SPDX-License-Identifier: GPL-2.0-only
'use strict';
'require view';
'require rpc';
'require poll';
'require ui';

var callStatus = rpc.declare({ object: 'luci.needrestart', method: 'status', expect: {} });
var callScan = rpc.declare({ object: 'luci.needrestart', method: 'scan', expect: {} });

function cell(value) { return E('td', {}, [ String(value == null ? '' : value) ]); }

function table(headings, rows, empty) {
	return E('table', { 'class': 'table cbi-section-table' }, [
		E('tr', { 'class': 'tr table-titles' }, headings.map(function(h) { return E('th', {}, [ h ]); }))
	].concat(rows.length ? rows : [ E('tr', {}, [ E('td', { colspan: headings.length }, [ empty ]) ]) ]));
}

return view.extend({
	refresh: function() {
		if (this.pending) return this.pending;
		this.pending = callStatus().then(L.bind(function(data) {
			var r = data.report;
			this.scanButton.disabled = !!(data.pending || data.running);
			this.status.className = 'alert-message ' + (data.error ? 'error' :
				(!r || !r.complete || data.pending || data.running ? 'warning' : 'notice'));
			this.status.textContent = data.error || (data.running ? _('Scan running…') :
				data.pending ? _('Scan queued; waiting for the package transaction or current scan.') :
				r ? (r.complete ? _('Scan complete') : _('Coverage incomplete — this report cannot establish that everything is current.')) :
				_('No report yet. Select Scan now.'));
			if (!r) {
				this.reportKey = null;
				this.content.replaceChildren();
				return;
			}
			var key = JSON.stringify(r);
			if (key == this.reportKey) return;
			this.reportKey = key;
			this.content.replaceChildren();
			this.content.appendChild(E('p', {}, [ _('Report time:') + ' ' +
				new Date(r.timestamp * 1000).toLocaleString() + ' · ' + _('Processes scanned:') + ' ' + r.processes_scanned ]));
			var rows = (r.services || []).map(function(s) {
				var details = E('details', {}, [ E('summary', {}, [ _('Affected processes and files') ]) ]);
				(s.processes || []).forEach(function(p) {
					(p.files || []).forEach(function(f) {
						details.appendChild(E('div', {}, [ 'PID ' + p.pid + ': ' + f.path + ' (' + f.reason + ')' +
							(f.package ? ' · ' + f.package.name + ' ' + f.package.installed_version : '') ]));
					});
				});
				return E('tr', { 'class': 'tr' }, [ cell(s.container ? s.container.name + ' (' + s.name.substring(0, 12) + ')' : s.name),
					cell(s.kind), cell(s.disruptive ? _('Potentially disruptive / maintenance review') : _('Restart advised')),
					E('td', {}, [ E('code', {}, [ s.recommended_action ]), details ]) ]);
			});
			this.content.appendChild(E('h3', {}, [ _('Affected services and processes') ]));
			this.content.appendChild(table([ _('Service'), _('Owner type'), _('Advice'), _('Evidence and action') ], rows,
				_('No affected processes detected within assessed coverage.')));
			var k = r.kernel || {};
			this.content.appendChild(E('h3', {}, [ _('Kernel') ]));
			this.content.appendChild(E('p', {}, [ (k.running_release || '') + ' · ' + (k.status || 'unknown') ]));
			if (k.recommended_action || k.detail)
				this.content.appendChild(E('p', {}, [ k.recommended_action || k.detail ]));
			this.content.appendChild(E('h3', {}, [ _('Containers') ]));
			rows = (r.containers || []).map(function(c) {
				return E('tr', {}, [ cell(c.name + ' (' + c.id.substring(0, 12) + ')'),
					cell(c.account + ' / UID ' + c.uid), cell(c.image_reference),
					cell(c.image_status == 'changed' ? _('Local image changed — recreation needed through the deployment controller') : c.image_status),
					cell(c.controller || _('Deployment controller not verified')) ]);
			});
			this.content.appendChild(table([ _('Container'), _('Account'), _('Image'), _('Local image status'), _('Controller') ], rows,
				_('No inventoried running Podman containers.')));
			(r.warnings || []).forEach(L.bind(function(w) {
				this.content.appendChild(E('p', { 'class': 'alert-message warning' }, [ w ]));
			}, this));
		}, this)).catch(L.bind(function(e) {
			this.status.className = 'alert-message error';
			this.status.textContent = e.message;
			this.scanButton.disabled = false;
		}, this)).finally(L.bind(function() { this.pending = null; }, this));
		return this.pending;
	},

	render: function() {
		this.status = E('p', { 'class': 'cbi-section-descr' }, [ _('Loading restart advice…') ]);
		this.content = E('div');
		this.scanButton = E('button', { 'class': 'cbi-button cbi-button-action', click: L.bind(function() {
			this.scanButton.disabled = true;
			return callScan().then(L.bind(function(r) {
				if (!r.success) throw new Error(r.error || _('Unable to queue scan'));
				return this.refresh();
			}, this)).catch(L.bind(function(e) {
				this.scanButton.disabled = false;
				ui.addNotification(null, E('p', {}, [ e.message ]), 'error');
			}, this));
		}, this) }, [ _('Scan now') ]);
		poll.add(L.bind(this.refresh, this), 3);
		this.refresh();
		return E('div', {}, [ E('h2', {}, [ _('Restart Needed') ]),
			E('p', {}, [ _('Reports replaced executable code, pending kernel activation, and local container image changes. No services are restarted. Script and module source changes and registry updates are not assessed.') ]),
			this.scanButton, this.status, this.content ]);
	},

	handleSave: null,
	handleSaveApply: null,
	handleReset: null
});
