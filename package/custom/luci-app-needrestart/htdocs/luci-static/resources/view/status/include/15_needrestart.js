// SPDX-License-Identifier: GPL-2.0-only
'use strict';
'require baseclass';
'require rpc';

var callStatus = rpc.declare({ object: 'luci.needrestart', method: 'status', expect: {} });

return baseclass.extend({
	title: _('Restart advice'),
	load: function() { return callStatus().catch(function() { return { error: true }; }); },
	render: function(data) {
		var r = data.report, text;
		if (data.error) text = _('Restart report unavailable');
		else if (data.running || data.pending) text = _('Restart check pending');
		else if (!r) text = _('No restart report yet');
		else {
			var changed = (r.containers || []).filter(function(c) { return c.image_status == 'changed'; }).length;
			text = _('Affected services/process groups:') + ' ' + (r.services || []).length +
				' · ' + _('Changed local container images:') + ' ' + changed +
				' · ' + _('Kernel:') + ' ' + ((r.kernel || {}).status || 'unknown') +
				(!r.complete ? ' · ' + _('Incomplete coverage') : '') +
				' · ' + new Date(r.timestamp * 1000).toLocaleString();
		}
		return E('div', {}, [ E('a', { href: L.url('admin/status/needrestart') }, [ text ]) ]);
	}
});
