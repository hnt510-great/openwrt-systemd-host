// Run with node from the repository root. Check the full cone NAT checkbox on
// the LuCI firewall zone page (feeds/luci luci-app-firewall view/firewall/zones.js).
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('feeds/luci/applications/luci-app-firewall/htdocs/luci-static/resources/view/firewall/zones.js', 'utf8');

// Any property is a callable stub returning another stub; assigned values stick.
function stub(record) {
	const store = {};
	const target = function() {};
	return new Proxy(target, {
		get(_, key) {
			if (key in store) return store[key];
			if (key === 'then') return undefined;
			if (key === Symbol.toPrimitive) return () => '';
			return (...args) => record ? record(key, args) : stub();
		},
		set(_, key, value) { store[key] = value; return true; },
		apply() { return stub(); },
		construct() { return stub(); }
	});
}

function render(features) {
	const options = [];
	const form = new Proxy({}, { get: (_, cls) => cls === 'Map'
		? function() {
			return stub((key, args) => {
				if (key !== 'section') return stub();
				const [, type] = args;
				return stub((method, oargs) => {
					if (method !== 'option' && method !== 'taboption') return stub();
					const [cls, name] = method === 'option' ? oargs : oargs.slice(1);
					const option = stub();
					options.push({ section: type, cls, name, option });
					return option;
				});
			});
		}
		: cls });
	const context = vm.createContext({
		_: s => s, view: { extend: obj => obj }, rpc: { declare: () => () => Promise.resolve([]) },
		uci: stub(), form, network: stub(), firewall: stub(), fwtool: stub(), widgets: stub(),
		L: { hasSystemFeature: f => features.includes(f), bind: (fn, self) => fn.bind(self) },
		E: () => ({}), cbi_update_table: () => {}, document: stub(), window: stub()
	});
	const page = vm.runInContext('(function() { ' + source.replace(/^'require [^']+';$/mg, '') + ' })()', context);
	page.renderZones([[], stub()]);
	return options;
}

const fw4 = render(['firewall4']);
const fullcone = fw4.filter(o => o.name === 'fullcone');
assert.equal(fullcone.length, 1, 'one fullcone option with firewall4');
assert.equal(fullcone[0].section, 'defaults');
assert.equal(fullcone[0].cls, 'Flag');
assert.equal(fullcone[0].option.enabled, '2', 'checked writes the Broadcom mode');
assert.equal(fullcone[0].option.disabled, '0');
assert.equal(fullcone[0].option.default, '0', 'unchecked by default');
assert.ok(!fw4.some(o => o.name === 'fullcone6'), 'no IPv6 option: nft_fullcone is not shipped');
const order = fw4.filter(o => o.section === 'defaults').map(o => o.name);
assert.ok(order.indexOf('fullcone') > order.indexOf('forward'), 'placed after the default policies');

const legacy = render([]);
assert.ok(!legacy.some(o => o.name === 'fullcone'), 'hidden without firewall4');

console.log('LuCI firewall full cone checkbox: firewall4 flag, values, placement and fw3 hiding passed');
