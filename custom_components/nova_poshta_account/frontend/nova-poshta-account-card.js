/* Nova Poshta Account card. Bundled with the integration; no external modules. */
const CARD_TYPE = "nova-poshta-account-card";
const DOMAIN = "nova_poshta_account";
const DEFAULT_COLUMNS = ["description", "status", "pickup", "delivery"];
const TEXT = {
  ru: {title:"Нова пошта", description:"Посылка",status:"Статус",pickup:"Получение",delivery:"Доставка",active:"Активные",ready:"Можно забирать",refresh:"Обновить",empty:"Активных посылок нет",unavailable:"Не удалось обновить посылки. Проверьте подключение и API-ключ в настройках интеграции.",missing:"Выберите датчик «Активные посылки» в настройках карточки.",error:"Не удалось обновить посылки",entity:"Датчик посылок",name:"Заголовок",columns:"Столбцы",direction:"Какие посылки показывать",both:"Входящие и исходящие",incoming:"Входящие",outgoing:"Исходящие",compact:"Компактный вид",show_refresh:"Кнопка обновления",language:"Язык",auto:"Язык Home Assistant",all:"Все направления"},
  uk: {title:"Нова пошта",description:"Посилка",status:"Статус",pickup:"Отримання",delivery:"Доставка",active:"Активні",ready:"Можна забирати",refresh:"Оновити",empty:"Активних посилок немає",unavailable:"Не вдалося оновити посилки. Перевірте підключення й API-ключ у налаштуваннях інтеграції.",missing:"Виберіть датчик активних посилок у налаштуваннях картки.",error:"Не вдалося оновити посилки",entity:"Датчик посилок",name:"Заголовок",columns:"Стовпці",direction:"Які посилки показувати",both:"Вхідні та вихідні",incoming:"Вхідні",outgoing:"Вихідні",compact:"Компактний вигляд",show_refresh:"Кнопка оновлення",language:"Мова",auto:"Мова Home Assistant",all:"Усі напрямки"},
  en: {title:"Nova Poshta",description:"Parcel",status:"Status",pickup:"Pickup",delivery:"Delivery",active:"Active",ready:"Ready for pickup",refresh:"Refresh",empty:"No active parcels",unavailable:"Unable to update parcels. Check the connection and API key in the integration settings.",missing:"Select the active parcels sensor in the card settings.",error:"Unable to refresh parcels",entity:"Parcels sensor",name:"Title",columns:"Columns",direction:"Parcels to display",both:"Incoming and outgoing",incoming:"Incoming",outgoing:"Outgoing",compact:"Compact layout",show_refresh:"Refresh button",language:"Language",auto:"Home Assistant language",all:"All directions"}
};
function texts(config, hass) {
  const language = !config.language || config.language === "auto" ? hass?.language : config.language;
  return TEXT[(language || "en").split("-")[0]] || TEXT.en;
}
function sensors(hass) {
  return Object.keys(hass?.states || {}).filter(id => id.startsWith("sensor.") && hass.states[id].attributes?.integration === DOMAIN);
}
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function cleanDescription(value) {
  return String(value || "").replace(/^\d+(\(\d+\))?\s*/, "");
}
function pickup(parcel) {
  const address = String(parcel.address || "");
  const point = address.match(/(Поштомат|Відділення|Отделение|Почтомат).*?№\s*(\d+)/i);
  return point ? `${point[1]} №${point[2]}` : address || String(parcel.city || "—");
}
function delivery(value, hass) {
  if (!value) return ["—", ""];
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return ["—", ""];
  const options = {timeZone: hass?.config?.time_zone || "Europe/Kyiv"};
  return [new Intl.DateTimeFormat("uk-UA", {...options, day:"2-digit", month:"2-digit"}).format(date),
    new Intl.DateTimeFormat("uk-UA", {...options, hour:"2-digit", minute:"2-digit", hourCycle:"h23"}).format(date)];
}

class NovaPoshtaAccountCard extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._busy=false; }
  static getConfigElement() { return document.createElement(`${CARD_TYPE}-editor`); }
  static getStubConfig(hass) {
    return {entity:sensors(hass)[0] || "", language:"auto", compact:true, direction:"both", show_refresh:true};
  }
  setConfig(config) {
    if (config.columns && (!Array.isArray(config.columns) || !config.columns.length || config.columns.some(c => !DEFAULT_COLUMNS.includes(c)))) {
      throw new Error("Choose at least one valid parcel column");
    }
    this._config={compact:true,show_refresh:true,direction:"both",language:"auto",...config};
    this._render();
  }
  set hass(hass) {
    const id=this._config?.entity || sensors(hass)[0];
    const state=hass.states[id];
    const changed=state!==this._state || hass.language!==this._hass?.language || hass.config?.time_zone!==this._hass?.config?.time_zone;
    this._hass=hass;
    this._state=state;
    if (changed) this._render();
  }
  getCardSize() { return Math.max(2, 1 + (this._state?.attributes?.parcels?.length || 0)); }
  getGridOptions() { return {columns:12, min_columns:6, rows:"auto"}; }
  async _refresh() {
    const button=this._state?.attributes?.refresh_entity;
    const id=button || this._config.entity || sensors(this._hass)[0];
    if (!id || this._busy) return;
    this._busy=true; this._error=false; this._render();
    try { await this._hass.callService(button ? "button" : "homeassistant",button ? "press" : "update_entity",{entity_id:id}); }
    catch { this._error=true; }
    finally { this._busy=false; this._render(); }
  }
  _render() {
    if (!this._config || !this._hass) return;
    const t=texts(this._config,this._hass);
    const state=this._hass.states[this._config.entity || sensors(this._hass)[0]];
    this._state=state;
    const root=this.shadowRoot;
    root.replaceChildren();
    const style=element("style");
    style.textContent=`
      :host{display:block}ha-card{overflow:hidden}.head{padding:16px 16px 12px;display:flex;align-items:center;gap:12px}.heading{flex:1;min-width:0}h2{font-size:18px;font-weight:500;margin:0 0 4px}.counts{color:var(--secondary-text-color);font-size:12px}.refresh{cursor:pointer;color:var(--primary-color);background:transparent;border:0;border-radius:50%;padding:9px;display:flex;align-items:center}.refresh:hover{background:var(--secondary-background-color)}.refresh:focus-visible,a:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}.refresh:disabled{opacity:.45;cursor:default}.refresh ha-icon{--mdc-icon-size:22px}.scroll{padding:0 16px 14px;overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px;line-height:1.45}th{text-align:left;color:var(--secondary-text-color);font-weight:500;font-size:12px}th,td{padding:10px 8px;border-bottom:1px solid var(--divider-color);vertical-align:top}th:first-child,td:first-child{padding-left:0}th:last-child,td:last-child{padding-right:0}tbody tr:last-child td{border-bottom:0}a{color:var(--primary-color);text-decoration:none;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}a:hover{text-decoration:underline}.number{display:block;color:var(--secondary-text-color);font-size:11px;margin-top:4px;white-space:nowrap}.delivery{white-space:nowrap}.date{display:block}.time{display:block;font-weight:500}.status{min-width:85px;max-width:200px}.pickup{min-width:70px;max-width:160px;overflow-wrap:anywhere}.description{min-width:110px;max-width:260px}.pickup-row .status{color:var(--success-color,#43a047)}.message{padding:4px 16px 18px;color:var(--secondary-text-color);font-size:14px}.error{color:var(--error-color)}.compact th,.compact td{padding-top:8px;padding-bottom:8px}.compact .head{padding-bottom:8px}
      @media(max-width:430px){.scroll{padding:0 12px 12px}.head{padding:14px 12px 8px}table{font-size:12px}th,td{padding-left:5px;padding-right:5px}.description{min-width:90px}.status{min-width:65px}.pickup{min-width:55px}.number{font-size:10px}h2{font-size:17px}}
      @media(max-width:350px){table,tbody,tr,td{display:block}thead{display:none}tbody tr{padding:9px 0;display:grid;grid-template-columns:1fr 1fr;gap:8px 12px;border-bottom:1px solid var(--divider-color)}td,.compact td{border:0;padding:0!important;min-width:0!important;max-width:none!important}.description{grid-column:1/-1}td:not(.description):before{content:attr(data-label);display:block;font-size:10px;color:var(--secondary-text-color);margin-bottom:2px}.date,.time{display:inline}.time:before{content:' '}}
    `;
    root.append(style);
    const card=element("ha-card",null,this._config.compact ? "compact" : "");
    const header=element("div",null,"head"),heading=element("div",null,"heading");
    heading.append(element("h2",this._config.name || t.title));
    header.append(heading); card.append(header);
    const unavailable=state && ["unknown","unavailable"].includes(state.state);
    const rows=Array.isArray(state?.attributes?.parcels) ? state.attributes.parcels.filter(p => this._config.direction === "both" || p.direction === this._config.direction) : [];
    if (state && !unavailable) heading.append(element("div",`${t.active}: ${rows.length} · ${t.ready}: ${rows.filter(p => p.status==="at_pickup_point").length}`,"counts"));
    if (this._config.show_refresh && state) {
      const button=element("button",null,"refresh");button.title=t.refresh;button.setAttribute("aria-label",t.refresh);button.disabled=this._busy;
      const icon=element("ha-icon");icon.setAttribute("icon","mdi:refresh");button.append(icon);
      button.addEventListener("click",()=>this._refresh());header.append(button);
    }
    if (!state || unavailable || !rows.length) card.append(element("div",!state ? t.missing : unavailable ? t.unavailable : t.empty,"message"));
    else {
      const wrap=element("div",null,"scroll"),table=element("table");table.setAttribute("aria-label",this._config.name || t.title);
      const columns=this._config.columns || DEFAULT_COLUMNS,thead=element("thead"),tr=element("tr");
      for (const column of columns) {const th=element("th",t[column]);th.scope="col";tr.append(th);}
      thead.append(tr);table.append(thead);const body=element("tbody");
      for (const parcel of rows) {
        const row=element("tr",null,parcel.status==="at_pickup_point" ? "pickup-row" : "");
        for (const column of columns) {
          const cell=element("td",null,column);cell.dataset.label=t[column];
          if (column==="description") {
            const link=element("a",cleanDescription(parcel.description) || t.description);
            link.href=`https://novaposhta.ua/tracking/${encodeURIComponent(parcel.tracking_number)}`;
            link.target="_blank";link.rel="noopener noreferrer";link.title=String(parcel.description || "");
            cell.append(link,element("span",`${parcel.direction==="outgoing" ? "↑" : "↓"} ${parcel.tracking_number}`,"number"));
          } else if (column==="status") cell.textContent=parcel.status_detail || parcel.status_text || "—";
          else if (column==="pickup") {cell.textContent=pickup(parcel);cell.title=[parcel.city,parcel.address].filter(Boolean).join(", ");}
          else if (column==="delivery") {const [date,time]=delivery(parcel.expected_delivery,this._hass);cell.append(element("span",date,"date"),element("span",time,"time"));}
          row.append(cell);
        }
        body.append(row);
      }
      table.append(body);wrap.append(table);card.append(wrap);
    }
    if (this._error) card.append(element("div",t.error,"message error"));
    root.append(card);
  }
}

class NovaPoshtaAccountCardEditor extends HTMLElement {
  constructor() {super();this.attachShadow({mode:"open"});}
  setConfig(config) {this._config={language:"auto",compact:true,show_refresh:true,direction:"both",...config};this._render();}
  set hass(hass) {this._hass=hass;if(this._form)this._form.hass=hass;else this._render();}
  _render() {
    if(!this._config || !this._hass)return;
    const t=texts(this._config,this._hass),form=element("ha-form");
    form.hass=this._hass;
    form.data=this._config;
    form.schema=[
      {name:"entity",required:true,selector:{entity:{filter:{domain:"sensor",integration:DOMAIN}}}},
      {name:"name",selector:{text:{}}},
      {name:"direction",selector:{select:{options:["both","incoming","outgoing"].map(value=>({value,label:t[value]}))}}},
      {name:"columns",selector:{select:{multiple:true,options:DEFAULT_COLUMNS.map(value=>({value,label:t[value]}))}}},
      {name:"compact",selector:{boolean:{}}},
      {name:"show_refresh",selector:{boolean:{}}},
      {name:"language",selector:{select:{options:[{value:"ru",label:"Русский"},{value:"uk",label:"Українська"},{value:"en",label:"English"},{value:"auto",label:t.auto}]}}}
    ];
    if(!form.data.columns)form.data={...form.data,columns:[...DEFAULT_COLUMNS]};
    form.computeLabel=schema=>t[schema.name] || schema.name;
    form.addEventListener("value-changed",event=>{
      event.stopPropagation();
      const previous=this._config.language;
      this._config={...event.detail.value,type:`custom:${CARD_TYPE}`};
      this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:this._config},bubbles:true,composed:true}));
      if(previous!==this._config.language)this._render();
    });
    this._form=form;this.shadowRoot.replaceChildren(form);
  }
}
if(!customElements.get(CARD_TYPE))customElements.define(CARD_TYPE,NovaPoshtaAccountCard);
if(!customElements.get(`${CARD_TYPE}-editor`))customElements.define(`${CARD_TYPE}-editor`,NovaPoshtaAccountCardEditor);
window.customCards=window.customCards || [];
if(!window.customCards.some(card=>card.type===CARD_TYPE))window.customCards.push({
  type:CARD_TYPE,name:"Нова пошта · Посылки",description:"Все посылки в одной карточке: подробные статусы, получение и доставка.",preview:true,
  getEntitySuggestion:(hass,entity)=>hass.states[entity]?.attributes?.integration===DOMAIN ? {config:{type:`custom:${CARD_TYPE}`,entity}} : null
});
