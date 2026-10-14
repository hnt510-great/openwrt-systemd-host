// SPDX-License-Identifier: Apache-2.0
'use strict';
'require view';
'require rpc';
'require poll';
'require ui';

var callRead = rpc.declare({
	object: 'luci.journal', method: 'read', params: [ 'boot', 'unit', 'priority', 'lines' ]
});

return view.extend({
	filters: function() {
		return [ this.boot.value, this.unit.value.trim(), this.priority.value, +this.lines.value ];
	},

	refresh: function() {
		if (this.pending)
			return this.pending;
		var filters = this.filters(), key = JSON.stringify(filters);
		this.refreshButton.disabled = true;
		this.pending = callRead.apply(null, filters).then(L.bind(function(data) {
			if (key != JSON.stringify(this.filters()))
				return;
			if (!data.success)
				throw new Error(data.error || _('Unable to read the journal.'));
			this.log = data.log || '';
			this.truncated = data.truncated;
			this.updated = new Date().toLocaleTimeString();
			this.display();
		}, this)).catch(L.bind(function(error) {
			if (key != JSON.stringify(this.filters()))
				return;
			this.log = '';
			this.output.value = '';
			this.downloadButton.disabled = true;
			this.status.className = 'alert-message error';
			this.status.textContent = error.message;
		}, this)).finally(L.bind(function() {
			this.pending = null;
			this.refreshButton.disabled = false;
			if (key != JSON.stringify(this.filters()))
				return this.refresh();
		}, this));
		return this.pending;
	},

	display: function() {
		var needle = this.search.value.toLowerCase();
		var lines = (this.log || '').split('\n').filter(function(line) {
			return line.length && (!needle || line.toLowerCase().indexOf(needle) >= 0);
		});
		this.output.value = lines.join('\n');
		this.downloadButton.disabled = !lines.length;
		if (this.scroll.checked)
			this.output.scrollTop = this.output.scrollHeight;
		this.status.className = this.truncated ? 'alert-message warning' : 'cbi-section-descr';
		this.status.textContent = _('Displayed lines:') + ' ' + lines.length +
			(this.updated ? ' · ' + _('Updated:') + ' ' + this.updated : '') +
			(this.truncated ? ' · ' + _('Output limit reached. Narrow the filters.') : '') +
			(!lines.length ? ' · ' + _('No matching journal entries.') : '');
	},

	download: function() {
		var url = URL.createObjectURL(new Blob([ this.output.value + '\n' ], { type: 'text/plain;charset=utf-8' }));
		var link = E('a', { href: url, download: 'systemd-journal.txt' });
		document.body.appendChild(link);
		link.click();
		link.remove();
		URL.revokeObjectURL(url);
	},

	render: function() {
		var refresh = L.bind(this.refresh, this);
		function select(options, value) {
			return E('select', { 'class': 'cbi-input-select', change: refresh }, options.map(function(option) {
				return E('option', { value: option[0], selected: option[0] == value || null }, [ option[1] ]);
			}));
		}
		function field(label, input) {
			return E('label', { style: 'display:flex;flex-direction:column;gap:.3em' }, [ label, input ]);
		}
		this.boot = select([ [ 'current', _('Current boot') ], [ 'previous', _('Previous boot') ], [ 'all', _('All boots') ] ], 'current');
		this.unit = E('input', { 'class': 'cbi-input-text', type: 'text', maxlength: 256,
			placeholder: 'openwrt-procd.service', change: refresh,
			keydown: function(event) { if (event.key == 'Enter') refresh(); } });
		this.priority = select([
			[ 'all', _('All priorities') ], [ '0', _('Emergency') ], [ '1', _('Alert and above') ],
			[ '2', _('Critical and above') ], [ '3', _('Error and above') ],
			[ '4', _('Warning and above') ], [ '5', _('Notice and above') ],
			[ '6', _('Info and above') ], [ '7', _('Debug and above') ]
		], 'all');
		this.lines = select([ [ '100', '100' ], [ '300', '300' ], [ '1000', '1000' ] ], '300');
		this.search = E('input', { 'class': 'cbi-input-text', type: 'search',
			placeholder: _('Filter displayed lines'), input: L.bind(this.display, this) });
		this.auto = E('input', { type: 'checkbox', checked: true });
		this.scroll = E('input', { type: 'checkbox', checked: true });
		this.status = E('p', { 'class': 'cbi-section-descr' }, [ _('Loading journal…') ]);
		this.output = E('textarea', { 'class': 'cbi-input-textarea', readonly: true, rows: 28,
			'aria-label': _('Systemd Journal'), wrap: 'off',
			style: 'width:100%;font-family:monospace;white-space:pre;overflow:auto' });
		this.refreshButton = E('button', { 'class': 'cbi-button cbi-button-action', click: refresh }, [ _('Refresh') ]);
		this.downloadButton = E('button', { 'class': 'cbi-button', disabled: true,
			click: L.bind(this.download, this) }, [ _('Download displayed log') ]);
		poll.add(L.bind(function() { if (this.auto.checked) return this.refresh(); }, this), 5);
		var root = E('div', [
			E('h2', [ _('Systemd Journal') ]),
			E('p', [ _('Read systemd service and system logs. An empty unit shows all units. Search filters the latest entries shown below.') ]),
			E('div', { style: 'display:flex;flex-wrap:wrap;gap:1em;margin-bottom:1em' }, [
				field(_('Boot'), this.boot), field(_('Unit'), this.unit),
				field(_('Minimum severity'), this.priority), field(_('Latest entries'), this.lines),
				field(_('Search'), this.search)
			]),
			E('div', { style: 'display:flex;align-items:center;flex-wrap:wrap;gap:1em' }, [
				this.refreshButton, this.downloadButton,
				E('label', [ this.auto, ' ', _('Refresh every 5 seconds') ]),
				E('label', [ this.scroll, ' ', _('Scroll to latest entries') ])
			]), this.status, this.output
		]);
		this.refresh();
		return root;
	},

	handleSave: null,
	handleSaveApply: null,
	handleReset: null
});
