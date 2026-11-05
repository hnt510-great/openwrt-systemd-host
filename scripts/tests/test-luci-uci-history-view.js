#!/usr/bin/env node
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
class Element {
 constructor(tag, attrs, children) { this.tag = tag; this.attrs = attrs || {}; this.children = children || []; this.textContent = ''; this.value = this.attrs.value; this.checked = !!this.attrs.checked; this.disabled = !!this.attrs.disabled; }
 appendChild(e) { this.children.push(e); return e; }
 replaceChildren(...e) { this.children = e; }
 text() { return this.textContent + this.children.map(c => c instanceof Element ? c.text() : String(c)).join(' '); }
}
function E(tag, attrs, children) { if (Array.isArray(attrs)) { children = attrs; attrs = {}; } return new Element(tag, attrs, children); }
async function main() {
 let state = { schema_version: 1, ok: true, head: 2, configs: ['network', 'system'], staged: {} }, writable = true, offline = false;
 const calls = [], notices = [], tx = { id: 'a'.repeat(32), deadline: Date.now() / 1000 + 90 };
 const rpc = { declare: spec => async (...args) => {
  calls.push([spec.method, ...args]);
  if (offline && spec.method == 'status') throw new Error('Unreachable');
  if (spec.method == 'status') return state;
  if (spec.method == 'log') return { ok: true, revisions: [{ revision: 1, time: 100, actor: '<script>actor</script>', note: '<img src=x>', configs: ['network'] }] };
  if (spec.method == 'diff') return { ok: true, changes: [{ config: 'network', section: 'lan', option: 'password', old: 'changed', new: 'changed' }], diff: '<script>diff</script>' };
  if (spec.method == 'restore') { if (!args[3]) state = { ...state, transaction: tx }; return { ok: true, transaction: tx }; }
  if (spec.method == 'confirm' || spec.method == 'abort') { state = { ...state, transaction: null }; return { ok: true }; }
 } };
 const L = { env: { apply_rollback: 90, apply_holdoff: 1 }, bind: (f, obj) => f.bind(obj), hasViewPermission: () => writable };
 const view = new Function('view', 'rpc', 'poll', 'ui', 'L', 'E', '_', 'window',
  fs.readFileSync(path.join(__dirname, '../../package/custom/luci-app-uci-history/htdocs/luci-static/resources/view/system/uci-history.js'), 'utf8'))(
   { extend: x => x }, rpc, { add() {} }, { addNotification: (...args) => notices.push(args), showModal() {}, hideModal() {} }, L, E, x => x, { setTimeout: f => f() });
 view.render(); await view.pending;
 assert.match(view.rows.text(), /<script>actor/);
 assert.equal(view.confirmButton.disabled, true);
 await view.select({ revision: 1, configs: ['network'] });
 assert.equal(view.boxes[0].box.checked, true);
 assert.equal(view.boxes[1].box.checked, false);
 assert.match(view.diffPanel.text(), /changed/);
 view.format.value = 'unified'; await view.showDiff();
 assert.match(view.diffPanel.text(), /<script>diff/);
 await view.previewRestore();
 assert.deepEqual(calls.find(c => c[0] == 'restore'), ['restore', '1', ['network'], 90, true]);
 await view.restore('1', ['network'], 90);
 assert.deepEqual(calls.find(c => c[0] == 'confirm'), ['confirm', tx.id]);
 calls.length = 0; offline = true;
 await view.restore('1', ['network'], 90);
 assert(!calls.some(c => c[0] == 'confirm'), 'unreachable browser must not confirm');
 assert(notices.length);
 offline = false; state = { ...state, transaction: tx }; await view.refresh();
 assert.equal(view.confirmButton.disabled, false);
 await view.finish('abort');
 assert(calls.some(c => c[0] == 'abort' && c[1] == tx.id));
 writable = false; view.render(); await view.pending;
 await view.select({ revision: 1, configs: ['network'] });
 assert.equal(view.restoreButton.disabled, true);
 const tags = []; function walk(e) { if (!(e instanceof Element)) return; tags.push(e.tag); e.children.forEach(walk); }
 walk(view.rows); walk(view.diffPanel);
 assert(!tags.includes('script') && !tags.includes('img'));
 console.log('PASS: history, diff, restore preview, transaction binding, disconnect, ACL and text escaping');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
