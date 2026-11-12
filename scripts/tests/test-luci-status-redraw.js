// Run with node from the repository root. Check that the LuCI status overview
// (feeds/luci luci-mod-status view/status/index.js) keeps unchanged include
// output in place across polls instead of rebuilding it, so icons do not
// flicker, and still replaces output that changed.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('feeds/luci/modules/luci-mod-status/htdocs/luci-static/resources/view/status/index.js', 'utf8');

// Minimal DOM: elements, text nodes and fragments with isEqualNode().
class Node {
	constructor(type) { this.nodeType = type; this.childNodes = []; this.parentNode = null; }
	get firstChild() { return this.childNodes[0] || null; }
	get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
	appendChild(child) {
		if (child.nodeType === 11) {
			for (const c of child.childNodes.slice()) this.appendChild(c);
			return child;
		}
		if (child.parentNode) child.parentNode.removeChild(child);
		child.parentNode = this;
		this.childNodes.push(child);
		return child;
	}
	replaceChild(child, old) {
		if (child.parentNode) child.parentNode.removeChild(child);
		this.childNodes[this.childNodes.indexOf(old)] = child;
		child.parentNode = this;
		old.parentNode = null;
		return old;
	}
	removeChild(child) {
		this.childNodes.splice(this.childNodes.indexOf(child), 1);
		child.parentNode = null;
		return child;
	}
	set innerHTML(html) {
		for (const c of this.childNodes.slice()) this.removeChild(c);
		this.appendChild(new Text(html));
	}
	querySelectorAll(sel) {
		assert.equal(sel, '[data-idref]');
		const out = [];
		(function walk(n) {
			for (const c of n.childNodes) {
				if (c.nodeType === 1 && c.attributes.has('data-idref')) out.push(c);
				walk(c);
			}
		})(this);
		return out;
	}
	isEqualNode(other) {
		if (!other || other.nodeType !== this.nodeType) return false;
		if (this.nodeType === 3) return this.data === other.data;
		if (this.nodeName !== other.nodeName) return false;
		if (this.attributes.size !== other.attributes.size) return false;
		for (const [k, v] of this.attributes)
			if (other.attributes.get(k) !== v) return false;
		if (this.childNodes.length !== other.childNodes.length) return false;
		return this.childNodes.every((c, i) => c.isEqualNode(other.childNodes[i]));
	}
}
class Element extends Node {
	constructor(tag) {
		super(1);
		this.nodeName = tag.toUpperCase();
		this.attributes = new Map();
		this.listeners = [];
		this.style = {};
		this.classList = { add() {} };
	}
	setAttribute(k, v) { this.attributes.set(k, String(v)); }
	getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null; }
}
class Text extends Node {
	constructor(data) { super(3); this.data = String(data); }
}
class Fragment extends Node { constructor() { super(11); } }

// The parts of LuCI's E() and dom used by the view, with LuCI's semantics.
const registry = {};
const dom = {
	elem: e => e != null && typeof e === 'object' && 'nodeType' in e,
	append(node, children) {
		if (Array.isArray(children)) {
			for (const c of children)
				if (this.elem(c)) node.appendChild(c);
				else if (c != null) node.appendChild(new Text(c));
			return node.lastChild;
		}
		if (typeof children === 'function') return this.append(node, children(node));
		if (this.elem(children)) return node.appendChild(children);
		if (children != null) { node.innerHTML = `${children}`; return node.lastChild; }
		return null;
	},
	content(node, children) {
		for (const n of node.querySelectorAll('[data-idref]'))
			delete registry[n.getAttribute('data-idref')];
		for (const c of node.childNodes.slice()) node.removeChild(c);
		return this.append(node, children);
	}
};
function E(tag, attrs, children) {
	if (Array.isArray(tag)) { const f = new Fragment(); dom.append(f, tag); return f; }
	if (Array.isArray(attrs) || typeof attrs !== 'object' || attrs === null || attrs instanceof Node) {
		children = attrs; attrs = null;
	}
	const el = new Element(tag);
	for (const [k, v] of Object.entries(attrs || {}))
		if (typeof v === 'function') el.listeners.push(k);
		else el.setAttribute(k, v);
	dom.append(el, children);
	return el;
}

const context = vm.createContext({
	E, dom,
	_: s => s,
	view: { extend: obj => obj },
	network: { flushCache: () => Promise.resolve() },
	poll: { add: () => Promise.resolve() },
	ui: { createHandlerFn: () => () => {} },
	fs: {},
	L: { bind: (fn, self, ...args) => fn.bind(self, ...args), resolveDefault: p => p },
	document: { querySelector: () => null },
	localStorage: { getItem: () => null, setItem() {}, removeItem() {} }
});
const page = vm.runInContext('(function() { ' + source.replace(/^'require [^']+';$/mg, '') + ' })()', context);

// Wireless-like include, shaped like 60_wifi.js: radio boxes, a heading and
// the station list, whose per-client widgets carry unique data-idref values.
const state = { icon: 'signal-000-000.svg', ssid: 'OpenWrt-AX', clients: 0, idref: null, seq: 0 };
const wifi = {
	title: 'Wireless',
	render() {
		const badge = E('span', { 'class': 'ifacebadge', 'click': () => {} }, [
			E('img', { 'src': state.icon }),
			E('span', {}, [ state.ssid ])
		]);
		if (state.idref) badge.setAttribute('data-idref', state.idref);
		const rows = [];
		for (let i = 0; i < state.clients; i++) {
			const id = 'cb' + (++state.seq);
			registry[id] = {};
			rows.push(E('div', { 'class': 'tr', 'data-idref': id }, [ `client ${i}` ]));
		}
		return E([
			E('div', { 'class': 'network-status-table' }, [ badge ]),
			E('h3', {}, [ 'Associated Stations' ]),
			E('div', { 'class': 'assoclist' }, rows)
		]);
	}
};
const text = { title: 'Text', text: 'uptime 1h', render() { return this.text; } };
const hidden = { title: 'Hidden', hide: true, calls: 0, render() { this.calls++; return E('p', {}, [ 'x' ]); } };
const failing = { title: 'Failing', load: () => Promise.reject(new Error('rpc')), render() { return E('p'); } };

const includes = [ wifi, text, hidden, failing ];
const containers = includes.map(() => new Element('div'));
containers.forEach(c => new Element('section').appendChild(c));

const box = () => containers[0].childNodes[0];
const img = () => box().firstChild.firstChild;
const list = () => containers[0].childNodes[2];

(async () => {
	await page.poll_status(includes, containers, true);
	const firstImg = img();
	const firstHeading = containers[0].childNodes[1];
	const firstText = containers[1].firstChild;
	assert.equal(firstImg.getAttribute('src'), 'signal-000-000.svg');
	assert.equal(firstText.data, 'uptime 1h');
	assert.equal(containers[2].childNodes.length, 0, 'hidden include is rendered but not inserted on first load');
	assert.equal(containers[3].childNodes.length, 0, 'failed load leaves the container untouched');

	// Identical renders keep the existing nodes: no <img> is recreated.
	for (let n = 0; n < 3; n++) await page.poll_status(includes, containers, false);
	assert.equal(img(), firstImg, 'unchanged icon element is kept across polls');
	assert.equal(containers[0].childNodes[1], firstHeading);
	assert.equal(containers[1].firstChild, firstText, 'unchanged string content is kept');
	assert.equal(hidden.calls, 1, 'hidden include is not rendered on later polls');

	// Connected clients: the station list carries fresh data-idref values
	// on every poll and is rebuilt, but the radio box and its icon stay.
	state.clients = 2;
	await page.poll_status(includes, containers, false);
	const ids1 = list().childNodes.map(r => r.getAttribute('data-idref'));
	const list1 = list();
	await page.poll_status(includes, containers, false);
	const ids2 = list().childNodes.map(r => r.getAttribute('data-idref'));
	assert.notEqual(list(), list1, 'station list with new widgets is replaced');
	assert.equal(img(), firstImg, 'radio icon stays while the station list changes');
	assert.equal(containers[0].childNodes[1], firstHeading, 'unchanged heading stays');
	for (const id of ids1) assert.ok(!(id in registry), `replaced widget ${id} released`);
	for (const id of ids2) assert.ok(id in registry, `live widget ${id} kept`);
	assert.equal(Object.keys(registry).length, ids2.length, 'no registry entries leak from discarded renders');
	state.clients = 0;
	await page.poll_status(includes, containers, false);
	assert.equal(Object.keys(registry).length, 0);
	assert.equal(img(), firstImg);

	// A changed attribute replaces the radio box.
	state.icon = 'signal-075-100.svg';
	await page.poll_status(includes, containers, false);
	assert.notEqual(img(), firstImg, 'changed icon is replaced');
	assert.equal(img().getAttribute('src'), 'signal-075-100.svg');
	const secondImg = img();

	// Changed text replaces it too.
	state.ssid = 'Renamed';
	await page.poll_status(includes, containers, false);
	assert.notEqual(img(), secondImg);
	assert.equal(box().firstChild.childNodes[1].firstChild.data, 'Renamed');

	// A changed number of top-level nodes replaces the whole section.
	const before = img();
	const saved = wifi.render;
	wifi.render = function() { const f = saved.call(this); f.appendChild(E('p', {}, [ 'extra' ])); return f; };
	await page.poll_status(includes, containers, false);
	assert.equal(containers[0].childNodes.length, 4);
	assert.notEqual(img(), before, 'different child count rebuilds all nodes');
	wifi.render = saved;
	await page.poll_status(includes, containers, false);
	assert.equal(containers[0].childNodes.length, 3);

	// A changed string is replaced.
	text.text = 'uptime 2h';
	await page.poll_status(includes, containers, false);
	assert.equal(containers[1].firstChild.data, 'uptime 2h');

	// DOM mutated by a user action (e.g. a dimmed row) differs from a fresh
	// render, so the next poll restores it.
	box().setAttribute('style', 'opacity: 0.5');
	await page.poll_status(includes, containers, false);
	assert.equal(box().getAttribute('style'), null, 'mutated output is re-rendered');

	// A top-level registered node is always replaced and its entry released.
	state.idref = 'id1'; registry.id1 = {};
	await page.poll_status(includes, containers, false);
	state.idref = 'id2'; registry.id2 = {};
	await page.poll_status(includes, containers, false);
	assert.ok(!('id1' in registry), 'replaced widget registry entry is released');
	assert.ok('id2' in registry, 'live widget registry entry is kept');

	console.log('LuCI status redraw: unchanged sections kept, changes, mutations, hidden/failed includes and registry cleanup passed');
})().catch(err => { console.error(err); process.exit(1); });
