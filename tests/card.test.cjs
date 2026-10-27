const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const registry = new Map();
const context = vm.createContext({
  HTMLElement: class { attachShadow() { return {}; } },
  customElements: {get: name => registry.get(name), define: (name, value) => registry.set(name, value)},
  window: {},
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../custom_components/nova_poshta_account/frontend/nova-poshta-account-card.js'), 'utf8'), context);

test('omitted and automatic languages follow Home Assistant', () => {
  assert.equal(vm.runInContext('texts({}, {language:"uk-UA"}).refresh', context), 'Оновити');
  assert.equal(vm.runInContext('texts({language:"auto"}, {language:"ru"}).refresh', context), 'Обновить');
  assert.equal(vm.runInContext('texts({}, {language:"en"}).refresh', context), 'Refresh');
});
test('manual language overrides Home Assistant', () => {
  assert.equal(vm.runInContext('texts({language:"uk"}, {language:"en"}).refresh', context), 'Оновити');
});
test('unsupported Home Assistant language falls back to English', () => {
  assert.equal(vm.runInContext('texts({}, {language:"de"}).refresh', context), 'Refresh');
});
test('new cards and visual editors default to automatic language', () => {
  const Card = registry.get('nova-poshta-account-card');
  const Editor = registry.get('nova-poshta-account-card-editor');
  assert.equal(Card.getStubConfig({states:{}}).language, 'auto');
  const card = new Card(); card.setConfig({});
  assert.equal(card._config.language, 'auto');
  const editor = new Editor(); editor.setConfig({});
  assert.equal(editor._config.language, 'auto');
});
test('delivery is shown in the Home Assistant time zone', () => {
  const result = vm.runInContext('delivery("2026-10-28T16:00:00Z", {config:{time_zone:"Europe/Kyiv"}})', context);
  assert.equal(result[1], '18:00');
});
