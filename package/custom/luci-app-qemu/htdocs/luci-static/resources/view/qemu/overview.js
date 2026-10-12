// SPDX-License-Identifier: Apache-2.0
'use strict';
'require view';
'require rpc';
'require poll';
'require dom';
'require ui';

var callStatus = rpc.declare({ object: 'luci.qemu', method: 'status' });
var callAction = rpc.declare({
	object: 'luci.qemu', method: 'action', params: [ 'uuid', 'action' ]
});

function stateName(state) {
	return ({
		0: _('Unknown'), 1: _('Running'), 2: _('Blocked'),
		3: _('Paused'), 4: _('Shutting down'), 5: _('Shut off'),
		6: _('Crashed'), 7: _('Suspended')
	})[state] || _('Unknown');
}

function bytes(value) {
	if (value == null || !Number.isFinite(value))
		return '—';
	var units = [ 'B', 'KiB', 'MiB', 'GiB', 'TiB' ], index = 0;
	while (value >= 1024 && index < units.length - 1) {
		value /= 1024;
		index++;
	}
	return value.toFixed(index ? 1 : 0) + ' ' + units[index];
}

function active(vm) {
	return [ 1, 2, 3, 4, 7 ].indexOf(vm.state) >= 0;
}

function rate(vm, previous, field, elapsed) {
	if (!previous || !active(vm) || !active(previous) || elapsed <= 0 || elapsed > 30 ||
		vm[field] == null || previous[field] == null || vm[field] < previous[field] ||
		(vm.cpu_time != null && previous.cpu_time != null && vm.cpu_time < previous.cpu_time))
		return null;
	return (vm[field] - previous[field]) / elapsed;
}

function throughput(value) {
	return value == null ? '—' : bytes(value) + '/s';
}

return view.extend({
	load: function() {
		return callStatus().catch(function(error) {
			return { success: false, error: error.message };
		});
	},

	refresh: function() {
		// Share an in-flight read between polling and button completion.
		if (this.refreshing)
			return this.refreshing;
		this.refreshing = callStatus().then(L.bind(this.update, this)).catch(L.bind(function(error) {
			this.update({ success: false, error: error.message });
		}, this)).finally(L.bind(function() {
			this.refreshing = null;
		}, this));
		return this.refreshing;
	},

	handleAction: function(vm, action) {
		if (this.busy[vm.uuid])
			return;
		this.busy[vm.uuid] = true;
		this.root.querySelectorAll('[data-vm="' + vm.uuid + '"]').forEach(function(button) {
			button.disabled = true;
		});
		return callAction(vm.uuid, action).then(function(result) {
			if (!result.success)
				throw new Error(result.error || _('Operation failed'));
			ui.addNotification(null, E('p', [
				vm.name + ': ' + ({
					start: _('Start request accepted.'),
					shutdown: _('Shutdown request accepted. Waiting for the guest to shut down.'),
					reboot: _('Reboot request accepted. Waiting for the guest to reboot.')
				})[action]
			]), 'info');
		}).catch(function(error) {
			ui.addNotification(null, E('p', [ vm.name + ': ' + error.message ]), 'error');
		}).finally(L.bind(function() {
			delete this.busy[vm.uuid];
			// An earlier poll may have observed the state before this action.
			return Promise.resolve(this.refreshing).then(L.bind(this.refresh, this));
		}, this));
	},

	button: function(vm, action, label, enabled) {
		return E('button', {
			'class': 'cbi-button ' + (action == 'start' ? 'cbi-button-action' : 'cbi-button-neutral'),
			'data-vm': vm.uuid,
			'disabled': (!enabled || !this.writable || !!this.busy[vm.uuid]) || null,
			'click': L.bind(this.handleAction, this, vm, action)
		}, [ label ]);
	},

	update: function(data) {
		if (!data.success) {
			this.previous = {};
			this.timestamp = null;
			this.status.textContent = _('Unable to connect to libvirt:') + ' ' + (data.error || _('Operation failed'));
			this.status.className = 'alert-message error';
			// Do not leave stale measurements or actionable buttons on screen.
			dom.content(this.rows, E('tr', { 'class': 'tr' }, [
				E('td', { 'class': 'td', 'colspan': 7 }, [ _('Resource data unavailable') ])
			]));
			return;
		}

		var elapsed = data.timestamp - this.timestamp;
		var previous = this.previous, next = {};
		var running = data.domains.filter(active).length;
		this.status.className = 'cbi-section-descr';
		this.status.textContent = _('Connection:') + ' ' + data.uri + ' · ' +
			_('Active:') + ' ' + running + ' / ' + data.domains.length + ' · ' +
			_('Updated:') + ' ' + new Date().toLocaleTimeString();

		var rows = data.domains.map(L.bind(function(vm) {
			var old = previous[vm.uuid];
			var cpu = rate(vm, old, 'cpu_time', elapsed);
			next[vm.uuid] = vm;
			return E('tr', { 'class': 'tr' }, [
				E('td', { 'class': 'td' }, [
					E('strong', [ vm.name ]), E('br'),
					E('small', { 'style': 'overflow-wrap:anywhere' }, [ vm.uuid ])
				]),
				E('td', { 'class': 'td' }, [ stateName(vm.state) ]),
				E('td', { 'class': 'td' }, [
					cpu == null ? '—' : (cpu / 1e7).toFixed(1) + '%', E('br'),
					E('small', [ (vm.vcpus == null ? '—' : vm.vcpus) + ' vCPU' ])
				]),
				E('td', { 'class': 'td' }, [
					_('Host RSS:') + ' ' + bytes(active(vm) && vm.rss_kib != null ? vm.rss_kib * 1024 : null),
					E('br'), E('small', [ _('Allocated:') + ' ' + bytes(vm.memory_kib == null ? null : vm.memory_kib * 1024) ])
				]),
				E('td', { 'class': 'td' }, [
					_('Read:') + ' ' + throughput(rate(vm, old, 'disk_read', elapsed)), E('br'),
					_('Write:') + ' ' + throughput(rate(vm, old, 'disk_write', elapsed))
				]),
				E('td', { 'class': 'td' }, [
					_('RX:') + ' ' + throughput(rate(vm, old, 'net_rx', elapsed)), E('br'),
					_('TX:') + ' ' + throughput(rate(vm, old, 'net_tx', elapsed))
				]),
				E('td', { 'class': 'td' }, [ E('div', { 'style': 'display:flex;gap:.4em;flex-wrap:wrap' }, [
					this.button(vm, 'start', _('Start'), vm.state == 5),
					this.button(vm, 'shutdown', _('Shut down'), [ 1, 2, 3, 7 ].indexOf(vm.state) >= 0),
					this.button(vm, 'reboot', _('Reboot'), vm.state == 1)
				]) ])
			]);
		}, this));
		if (!rows.length)
			rows.push(E('tr', { 'class': 'tr' }, [
				E('td', { 'class': 'td', 'colspan': 7 }, [ _('No virtual machines defined in qemu:///system.') ])
			]));
		dom.content(this.rows, rows);
		this.previous = next;
		this.timestamp = data.timestamp;
	},

	render: function(data) {
		this.previous = {};
		this.busy = {};
		this.timestamp = null;
		this.writable = L.hasViewPermission();
		this.status = E('p');
		this.rows = E('tbody');
		this.root = E('div', [
			E('h2', [ _('QEMU Virtual Machines') ]),
			E('p', [ _('Manage existing virtual machines. Resource usage refreshes every 5 seconds.') ]),
			this.status,
			E('div', { 'style': 'overflow-x:auto' }, [ E('table', { 'class': 'table', 'style': 'min-width:960px' }, [
				E('thead', [ E('tr', { 'class': 'tr table-titles' }, [
					_('Virtual machine'), _('State'), _('CPU'), _('Memory'), _('Disk I/O'), _('Network'), _('Actions')
				].map(function(label) { return E('th', { 'class': 'th' }, [ label ]); })) ]),
				this.rows
			]) ]),
			E('p', { 'class': 'cbi-section-descr' }, [
				_('CPU: 100% equals one host logical core. Host RSS is the QEMU process memory, not guest memory usage. Rates appear after two samples; unavailable counters show —.')
			]),
			E('p', { 'class': 'cbi-section-descr' }, [
				_('Shutdown and reboot require guest ACPI support or a guest agent. An accepted request does not mean the operation has completed.')
			])
		]);
		this.update(data);
		poll.add(L.bind(this.refresh, this), 5);
		return this.root;
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
