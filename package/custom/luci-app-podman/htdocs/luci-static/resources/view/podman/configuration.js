'use strict';
'require view';
'require form';
'require rpc';

var accounts = rpc.declare({ object: 'luci.podman', method: 'accounts', expect: {} });

return view.extend({
	load: function() { return accounts(); },
	render: function(result) {
		if (!result.success) throw new Error(result.error || _('Unable to list accounts.'));
		var m = new form.Map('luci_podman', _('Rootless Podman'),
			_('Allow LuCI administrators to manage selected existing rootless accounts. Enroll accounts with podman-rootless-setup USER first.'));
		var s = m.section(form.NamedSection, 'main', 'podman');
		var o = s.option(form.MultiValue, 'users', _('Allowed accounts'));
		o.rmempty = true;
		result.accounts.forEach(function(a) { o.value(a.user, a.user + ' (UID ' + a.uid + ', ' + a.home + ')'); });
		o.description = _('Only ordinary accounts with at least 65536 subordinate UIDs and GIDs are listed. A user runtime directory and, with systemd cgroups, the user bus are required. Log in through SSH/PAM, or enable persistent access with loginctl enable-linger USER.');
		return m.render();
	}
});
