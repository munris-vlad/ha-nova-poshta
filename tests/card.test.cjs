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
test('optional empty-card hiding respects availability and filtered rows', () => {
  assert.equal(vm.runInContext('shouldHide({hide_empty:true}, {state:"0", attributes:{parcels:[]}}, [])', context), true);
  assert.equal(vm.runInContext('shouldHide({hide_empty:false}, {state:"0", attributes:{parcels:[]}}, [])', context), false);
  assert.equal(vm.runInContext('shouldHide({hide_empty:true}, {state:"unavailable", attributes:{parcels:[]}}, [])', context), false);
  assert.equal(vm.runInContext('shouldHide({hide_empty:true}, {state:"unknown", attributes:{parcels:[]}}, [])', context), false);
  assert.equal(vm.runInContext('shouldHide({hide_empty:true}, undefined, [])', context), false);
  assert.equal(vm.runInContext('shouldHide({hide_empty:true}, {state:"1", attributes:{parcels:[{}]}}, [{}])', context), false);
  assert.equal(vm.runInContext('shouldHide({hide_empty:true}, {state:"1", attributes:{parcels:[{direction:"incoming"}]}}, [])', context), true);
});
test('a hidden card reports zero layout height', () => {
  const Card = registry.get('nova-poshta-account-card');
  const card = new Card();card.setConfig({});card.hidden=true;
  assert.equal(card.getCardSize(), 0);
});
test('every card string is provided in all supported languages', () => {
  assert.equal(vm.runInContext('JSON.stringify(Object.keys(TEXT.en).sort())', context), vm.runInContext('JSON.stringify(Object.keys(TEXT.ru).sort())', context));
  assert.equal(vm.runInContext('JSON.stringify(Object.keys(TEXT.en).sort())', context), vm.runInContext('JSON.stringify(Object.keys(TEXT.uk).sort())', context));
});
test('localized detailed statuses are selected without leaking another language', () => {
  assert.equal(vm.runInContext('statusText({status_details:{en:"Arrived",uk:"Прибула",ru:"Прибыла"}}, {}, {language:"en"})', context), 'Arrived');
  assert.equal(vm.runInContext('statusText({status_details:{en:"Arrived",uk:"Прибула",ru:"Прибыла"}}, {}, {language:"ru"})', context), 'Прибыла');
  assert.equal(vm.runInContext('statusText({status:"at_pickup_point",status_detail:"Прибула"}, {}, {language:"en"})', context), 'Ready for pickup');
  assert.equal(vm.runInContext('statusText({status:"unknown",status_text:"Статус уточняется"}, {}, {language:"en"})', context), 'Status pending');
});
test('pickup labels and card picker metadata follow the UI language', () => {
  assert.equal(vm.runInContext('pickup({address:"Поштомат №12345"},TEXT.en)', context), 'Parcel locker №12345');
  assert.equal(vm.runInContext('pickup({address:"Відділення №12"},TEXT.ru)', context), 'Отделение №12');
  assert.equal(vm.runInContext('pickup({address:"Відділення №12"},TEXT.uk)', context), 'Відділення №12');
  vm.runInContext('currentHassLanguage="uk"', context);
  assert.equal(context.window.customCards[0].name, 'Нова пошта · Посилки');
  vm.runInContext('currentHassLanguage="en"', context);
  assert.equal(context.window.customCards[0].name, 'Nova Poshta · Parcels');
});
test('the open visual editor re-renders when Home Assistant changes language', () => {
  const Editor = registry.get('nova-poshta-account-card-editor');
  const editor = new Editor();editor.setConfig({});
  let rendered=0;editor._render=()=>{rendered++;};
  editor.hass={language:'en'};editor._form={};
  editor.hass={language:'ru'};
  assert.equal(rendered,2);
});
test('language selection also works in WebViews without Object.hasOwn', () => {
  vm.runInContext('Object.hasOwn=undefined', context);
  assert.equal(vm.runInContext('languageCode({}, {language:"ru"})', context), 'ru');
});
