// SPDX-License-Identifier: GPL-2.0-only
'use strict';
'require view';
'require rpc';
'require poll';
'require ui';

var callStatus = rpc.declare({ object: 'luci.uci-history', method: 'status', expect: {} });
var callLog = rpc.declare({ object: 'luci.uci-history', method: 'log', expect: {} });
var callDiff = rpc.declare({ object: 'luci.uci-history', method: 'diff', params: [ 'revision', 'format', 'config' ], expect: {} });
var callRestore = rpc.declare({ object: 'luci.uci-history', method: 'restore', params: [ 'revision', 'configs', 'timeout', 'dry_run' ], expect: {} });
var callConfirm = rpc.declare({ object: 'luci.uci-history', method: 'confirm', params: [ 'id' ], expect: {} });
var callAbort = rpc.declare({ object: 'luci.uci-history', method: 'abort', params: [ 'id' ], expect: {} });

function checked(data) {
	if (!data.ok) throw new Error(data.error && data.error.message || _('History request failed'));
	return data;
}
function cell(v) { return E('td', {}, [ v == null ? '' : String(v) ]); }
function table(headers, rows) {
	return E('table', { 'class': 'table' }, [ E('tr', {}, headers.map(function(h) {
		return E('th', {}, [ h ]);
	})) ].concat(rows));
}
function notify(e) { ui.addNotification(null, E('p', {}, [ e.message || String(e) ]), 'error'); }

return view.extend({
	refresh: function() {
		if (this.pending) return this.pending;
		this.pending = Promise.all([ callStatus(), callLog() ]).then(L.bind(function(data) {
			this.state = checked(data[0]);
			var revisions = checked(data[1]).revisions || [], tx = this.state.transaction;
			this.status.textContent = _('Head revision:') + ' ' + (this.state.head || '—') + ' · ' +
				(this.state.drift ? _('Uncaptured changes') : _('Captured')) +
				(tx ? ' · ' + _('Rollback deadline:') + ' ' + new Date(tx.deadline * 1000).toLocaleString() : '') +
				(this.state.rpcd_rollback ? ' · ' + _('LuCI apply rollback pending') : '') +
				(Object.keys(this.state.staged || {}).length ? ' · ' + _('Staged UCI changes pending') : '');
			this.confirmButton.disabled = this.abortButton.disabled = !tx || this.readonly;
			this.rows.replaceChildren(table([ _('Revision'), _('Time'), _('Actor'), _('Source'), _('Note'), _('Configurations'), _('Actions') ],
				revisions.map(L.bind(function(r) {
					return E('tr', {}, [ cell(r.revision), cell(new Date(r.time * 1000).toLocaleString()), cell(r.actor),
						cell(r.source), cell(r.note), cell((r.configs || []).join(', ')), E('td', {}, [ E('button', {
							'class': 'btn', click: L.bind(function() { return this.select(r).catch(notify); }, this)
						}, [ _('Inspect / restore') ]) ]) ]);
				}, this))));
			if (this.restoreButton)
				this.restoreButton.disabled = this.readonly || !!tx || this.state.rpcd_rollback;
		}, this)).catch(L.bind(function(e) { this.status.textContent = e.message; }, this)).finally(L.bind(function() {
			this.pending = null;
		}, this));
		return this.pending;
	},
	select: function(rev) {
		this.selected = rev;
		this.boxes = [];
		this.options.replaceChildren(E('h3', {}, [ _('Restore revision') + ' ' + rev.revision ]));
		Array.from(new Set((this.state.configs || []).concat(rev.configs || []))).sort().forEach(L.bind(function(c) {
			var box = E('input', { type: 'checkbox', checked: (rev.configs || []).indexOf(c) >= 0 });
			this.boxes.push({ config: c, box: box });
			this.options.appendChild(E('label', { 'class': 'cbi-value' }, [ box, ' ' + c ]));
		}, this));
		this.restoreButton = E('button', { 'class': 'btn cbi-button-action', disabled: this.readonly || !!this.state.transaction || this.state.rpcd_rollback,
			click: L.bind(this.previewRestore, this) }, [ _('Review restore') ]);
		this.options.appendChild(this.restoreButton);
		return this.showDiff();
	},
	showDiff: function() {
		if (!this.selected) return Promise.resolve();
		return callDiff(String(this.selected.revision), this.format.value || 'uci', '').then(L.bind(function(data) {
			checked(data);
			if (this.format.value == 'unified') this.diffPanel.replaceChildren(E('pre', {}, [ data.diff || _('No differences') ]));
			else this.diffPanel.replaceChildren(table([ _('Configuration'), _('Section'), _('Type'), _('Option'), _('Operation'), _('Old'), _('New') ],
				(data.changes || []).map(function(c) { return E('tr', {}, [ cell(c.config), cell(c.section), cell(c.type), cell(c.option),
					cell(c.op), cell(JSON.stringify(c.old)), cell(JSON.stringify(c.new)) ]); })));
		}, this));
	},
	previewRestore: function() {
		var configs = this.boxes.filter(function(b) { return b.box.checked; }).map(function(b) { return b.config; });
		if (!configs.length) { notify(new Error(_('Select at least one configuration'))); return Promise.resolve(); }
		var revision = String(this.selected.revision);
		var timeout = Math.max(5, Math.min(86400, Number(L.env.apply_rollback) || 90));
		return callRestore(revision, configs, timeout, true).then(L.bind(function(data) {
			checked(data);
			ui.showModal(_('Restore configuration'), [ E('p', {}, [ _('Selected configurations will be restored and reloaded. The change reverts automatically if this browser cannot reconnect.') ]),
				E('p', {}, [ configs.join(', ') ]), E('div', { 'class': 'right' }, [
					E('button', { 'class': 'btn', click: ui.hideModal }, [ _('Cancel') ]),
					E('button', { 'class': 'btn cbi-button-action', click: L.bind(function() {
						ui.hideModal();
						return this.restore(revision, configs, timeout);
					}, this) }, [ _('Restore') ]) ]) ]);
		}, this)).catch(notify);
	},
	restore: function(revision, configs, timeout) {
		this.restoreButton.disabled = true;
		return callRestore(revision, configs, timeout, false).then(L.bind(function(data) {
			checked(data);
			if (!data.transaction) throw new Error(_('Restore did not arm rollback'));
			// Verify a fresh round trip after reload. Bind confirmation to this restore's ID,
			// so another browser cannot cause us to confirm a different transaction.
			var id = data.transaction.id;
			return new Promise(function(resolve) {
				window.setTimeout(resolve, Math.max(1, Number(L.env.apply_holdoff) || 4) * 1000);
			}).then(function() { return callStatus(); }).then(function(state) {
				checked(state);
				if (!state.transaction || state.transaction.id != id) throw new Error(_('Transaction changed'));
				return callConfirm(id).then(checked);
			});
		}, this)).catch(notify).finally(L.bind(this.refresh, this));
	},
	finish: function(action) {
		if (!this.state.transaction) return Promise.resolve();
		return (action == 'confirm' ? callConfirm : callAbort)(this.state.transaction.id)
			.then(checked).catch(notify).finally(L.bind(this.refresh, this));
	},
	render: function() {
		this.readonly = !L.hasViewPermission();
		this.status = E('p', {}, [ _('Loading…') ]);
		this.rows = E('div');
		this.options = E('div');
		this.diffPanel = E('div');
		this.format = E('select', { change: L.bind(function() { return this.showDiff().catch(notify); }, this) }, [
			E('option', { value: 'uci' }, [ _('Structured UCI diff') ]), E('option', { value: 'unified' }, [ _('Unified diff') ]) ]);
		this.confirmButton = E('button', { 'class': 'btn', disabled: true, click: L.bind(function() { return this.finish('confirm'); }, this) }, [ _('Confirm') ]);
		this.abortButton = E('button', { 'class': 'btn', disabled: true, click: L.bind(function() { return this.finish('abort'); }, this) }, [ _('Abort / revert') ]);
		poll.add(L.bind(this.refresh, this), 5);
		this.refresh();
		return E('div', {}, [ E('h2', {}, [ _('Configuration History') ]),
			E('p', {}, [ _('Secrets are masked. Extra files require manual service reload after CLI restore.') ]), this.status,
			this.confirmButton, ' ', this.abortButton, this.rows, this.format, this.diffPanel, this.options ]);
	},
	handleSave: null,
	handleSaveApply: null,
	handleReset: null
});
