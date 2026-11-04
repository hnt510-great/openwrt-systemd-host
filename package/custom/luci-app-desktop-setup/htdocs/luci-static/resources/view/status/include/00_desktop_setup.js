// SPDX-License-Identifier: Apache-2.0
'use strict';
'require baseclass';
'require rpc';

var callStatus = rpc.declare({ object: 'luci.desktop-setup', method: 'status', expect: {} });
var callAccess = rpc.declare({ object: 'session', method: 'access',
	params: [ 'scope', 'object', 'function' ], expect: { access: false } });

return baseclass.extend({
	title: _('Desktop setup'),
	load: function() {
		return Promise.all([ callStatus(), callAccess('ubus', 'luci.desktop-setup', 'apply') ])
			.catch(function() { return [ null, false ]; });
	},
	render: function(data) {
		var status = data[0];
		if (status && status.automatic && data[1] && status.platform && status.platform.native)
			window.location.replace(L.url('admin/system/desktop-setup'));
		return E('a', { href: L.url('admin/system/desktop-setup') }, [ _('Open Desktop Setup Wizard') ]);
	}
});
