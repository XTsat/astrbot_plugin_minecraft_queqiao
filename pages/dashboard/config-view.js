/* Minecraft 鹊桥互通 - 配置管理（内嵌面板，顶部「⚙️ 设置」旁的「⚙️ 配置管理」按钮进入）
 * 通过 AstrBot Plugin Page Bridge 调用后端 Web API：
 *   GET  config/full  → { conf, schema, active_servers, data_dir }
 *   POST config/save  → { conf } → { saved, active_servers }
 * 可视化表单由 _conf_schema.json 驱动；JSON 模式直接编辑完整配置。
 * 面板显隐由 app.js 的视图切换（activateServerTab）控制；按钮三态循环：
 *   ① 非配置视图点击 → 进入配置表单视图（监听 queqiao:config-view-open 触发
 *      加载，detail.view 为进入前的视图，表单只渲染该视图对应部分：
 *      图床→图床配置、服务器→该服务器条目、全局→基本设置）；
 *   ② 表单态再点同一按钮 → 切全部 JSON（监听 queqiao:config-toggle-json，
 *      由 app.js 派发，此处执行 switchMode(true)）；
 *   ③ JSON 态再点 → 派发 queqiao:config-view-return，app.js 回到进入前的视图。
 * 面板内「📝 JSON 模式」按钮保留双向手动切换（不触发返回）。
 * 保存成功后派发 queqiao:config-saved 事件，dashboard 监听后刷新面板。
 */
const PLUGIN_PATH = 'astrbot_plugin_minecraft_queqiao';

const el = (id) => document.getElementById(id);
const bridge = window.AstrBotPluginPage || null;

const state = {
  conf: {},
  schema: {},
  activeServers: [],
  currentView: 'all', // 进入配置前的视图：'all' | 'image_bed' | 服务器 server_name
  dirty: false,
  jsonMode: false,
  jsonTouched: false,
  loading: true,
  loaded: false,
  personas: [],
};

/* ---------- API ---------- */
async function apiGet(endpoint, params = {}) {
  if (bridge && typeof bridge.apiGet === 'function') {
    return await bridge.apiGet(endpoint, params);
  }
  const query = new URLSearchParams(params).toString();
  const url = `/api/v1/plugins/extensions/${PLUGIN_PATH}/${endpoint}${query ? '?' + query : ''}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

async function apiPost(endpoint, body = {}) {
  if (bridge && typeof bridge.apiPost === 'function') {
    return await bridge.apiPost(endpoint, body);
  }
  const url = `/api/v1/plugins/extensions/${PLUGIN_PATH}/${endpoint}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

/* ---------- 工具 ---------- */
function renderDesc(text) {
  const frag = document.createElement('span');
  if (!text) return frag;
  const parts = String(text).split(/`([^`]+)`/g);
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 1) {
      const c = document.createElement('code');
      c.textContent = parts[i];
      frag.appendChild(c);
    } else if (parts[i]) {
      frag.appendChild(document.createTextNode(parts[i]));
    }
  }
  return frag;
}

function makeDefault(spec) {
  if (!spec || typeof spec !== 'object') return null;
  // 兼容旧版 schema 的 integer 写法；当前 schema 使用 AstrBot 支持的 int。
  const type = spec.type === 'integer' ? 'int' : spec.type;
  switch (type) {
    case 'bool':
      return !!spec.default;
    case 'int':
      return typeof spec.default === 'number' ? spec.default : 0;
    case 'string':
      return typeof spec.default === 'string' ? spec.default : '';
    case 'list': {
      const arr = Array.isArray(spec.default) ? spec.default : [];
      return arr.map((v) => (Array.isArray(v) ? [...v] : v));
    }
    case 'object': {
      const obj = {};
      for (const [k, sub] of Object.entries(spec.items || {})) obj[k] = makeDefault(sub);
      return obj;
    }
    case 'template_list':
      return [];
    default:
      return null;
  }
}

function deepCopy(v) {
  return v === undefined ? undefined : JSON.parse(JSON.stringify(v));
}

function displayPathValue(entry, path) {
  let v = entry;
  for (const seg of String(path).split('.')) {
    if (v === null || v === undefined) return undefined;
    v = v[seg];
  }
  return typeof v === 'string' && v.trim() ? v.trim() : undefined;
}

/* ---------- 控件 ---------- */
// 兼容旧版 schema 的 integer 写法，统一归一化为 int 后走控件分支。
function createControl(spec, onchange) {
  const type = spec.type === 'integer' ? 'int' : spec.type;
  switch (type) {
    case 'bool': {
      const el = document.createElement('input');
      el.type = 'checkbox';
      el.addEventListener('change', () => onchange());
      return {
        el,
        set: (v) => (el.checked = !!v),
        get: () => el.checked,
      };
    }
    case 'int': {
      const el = document.createElement('input');
      el.type = 'number';
      el.className = 'cfg-input';
      el.step = '1';
      el.addEventListener('input', () => onchange());
      return {
        el,
        set: (v) => (el.value = v === undefined || v === null ? '' : String(v)),
        get: () => (el.value === '' ? 0 : Number(el.value)),
      };
    }
    case 'string': {
      // persona_select：从后端获取人格列表并渲染下拉框
      if (spec.render_type === 'persona_select') {
        const el = document.createElement('select');
        el.className = 'cfg-select';
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = '(使用会话默认人格)';
        el.appendChild(emptyOpt);
        for (const p of (state.personas || [])) {
          const o = document.createElement('option');
          o.value = p.name;
          o.textContent = p.name;
          el.appendChild(o);
        }
        el.addEventListener('change', () => onchange());
        return {
          el,
          set: (v) => (el.value = v || ''),
          get: () => el.value,
        };
      }
      if (Array.isArray(spec.options) && spec.options.length) {
        const el = document.createElement('select');
        el.className = 'cfg-select';
        for (const opt of spec.options) {
          const o = document.createElement('option');
          o.value = String(opt);
          o.textContent = String(opt);
          el.appendChild(o);
        }
        el.addEventListener('change', () => onchange());
        return {
          el,
          set: (v) => (el.value = spec.options.includes(v) ? String(v) : String(spec.options[0])),
          get: () => el.value,
        };
      }
      const el = document.createElement('input');
      el.type = 'text';
      el.className = 'cfg-input';
      el.addEventListener('input', () => onchange());
      return {
        el,
        set: (v) => (el.value = v === undefined || v === null ? '' : String(v)),
        get: () => el.value,
      };
    }
    case 'list': {
      const el = document.createElement('textarea');
      el.className = 'cfg-textarea';
      el.placeholder = '每行一项';
      el.rows = 3;
      el.addEventListener('input', () => onchange());
      return {
        el,
        set: (v) => {
          const arr = Array.isArray(v) ? v : [];
          el.value = arr.map((x) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join('\n');
        },
        get: () => {
          const out = [];
          for (const line of el.value.split('\n')) {
            const t = line.trim();
            if (!t) continue;
            try {
              const parsed = JSON.parse(t);
              out.push(parsed);
            } catch {
              out.push(t);
            }
          }
          return out;
        },
      };
    }
    case 'text': {
      const el = document.createElement('input');
      el.type = 'text';
      el.className = 'cfg-input';
      el.addEventListener('input', () => onchange());
      return {
        el,
        set: (v) => (el.value = v === undefined || v === null ? '' : String(v)),
        get: () => el.value,
      };
    }
    default:
      return null;
  }
}

/* ---------- 字段渲染（复用主页面 settings-* 表单体系） ---------- */
function buildFieldRow(key, spec, target, onchange, opts = {}) {
  const { noLabelDesc = false } = opts;
  // object：分组卡片（settings-group 容器 + 子字段行）
  if (spec.type === 'object') {
    const grp = document.createElement('div');
    grp.className = 'settings-group';
    const hdr = document.createElement('div');
    hdr.className = 'settings-group-head';
    const t = document.createElement('span');
    t.className = 'settings-group-title';
    t.textContent = key;
    hdr.appendChild(t);
    if (spec.hint) {
      const n = document.createElement('span');
      n.className = 'settings-group-note';
      n.textContent = spec.hint;
      hdr.appendChild(n);
    }
    grp.appendChild(hdr);
    if (typeof target[key] !== 'object' || target[key] === null) target[key] = {};
    buildObjectFields(grp, spec.items || {}, target[key], onchange);
    return grp;
  }
  // template_list：条目卡片列表（保留原卡片样式）
  if (spec.type === 'template_list') {
    if (!Array.isArray(target[key])) target[key] = [];
    return buildTemplateList(spec, target[key], onchange, opts.entryIdPrefix);
  }
  // 标量字段：settings-row 三列（label / control / hint）
  const row = document.createElement('div');
  row.className = 'settings-row';
  const label = document.createElement('span');
  label.className = 'settings-row-label';
  // 显示中文名称：优先使用 spec.description（schema 中的中文描述），其次 spec.label，最后回退到 key
  label.textContent = spec.description || spec.label || key;
  row.appendChild(label);
  const ctrl = document.createElement('span');
  ctrl.className = 'settings-row-control';
  const control = createControl(spec, onchange);
  if (!control) {
    // 未知类型：不渲染控件，仅显示字段名和描述
    return row;
  }
  control.set(target[key]);
  control.el.dataset.fieldKey = key;
  // 控件变更时写回 target，保持 conf 与界面同步
  control.el.addEventListener('input', () => {
    target[key] = control.get();
  });
  control.el.addEventListener('change', () => {
    target[key] = control.get();
  });
  ctrl.appendChild(control.el);
  row.appendChild(ctrl);
  const hint = document.createElement('span');
  hint.className = 'settings-row-hint';
  if (!noLabelDesc && spec.description) hint.appendChild(renderDesc(spec.description));
  if (spec.hint) {
    if (hint.childNodes.length) hint.appendChild(document.createTextNode(' '));
    hint.appendChild(document.createTextNode(spec.hint));
  }
  row.appendChild(hint);
  return row;
}

function buildObjectFields(container, itemsSpec, target, onchange) {
  for (const [key, spec] of Object.entries(itemsSpec || {})) {
    container.appendChild(buildFieldRow(key, spec, target, onchange, {}));
  }
}

/* ---------- template_list 条目列表 ---------- */
function buildTemplateList(spec, arr, onchange, entryIdPrefix = '') {
  const wrap = document.createElement('div');
  wrap.className = 'entry-list';
  const tks = Object.keys(spec.templates || {});

  const renderEntries = () => {
    wrap.innerHTML = '';
    arr.forEach((entry, idx) => {
      const tk =
        entry.__template_key && spec.templates[entry.__template_key]
          ? entry.__template_key
          : tks[0];
      const tmpl = spec.templates[tk];
      if (!tmpl) return;

const card = document.createElement('div');
      card.className = 'entry-card';
      if (entryIdPrefix) card.id = `${entryIdPrefix}-${idx}`;
      let collapsed = entry.__collapsed !== false;

      const hdr = document.createElement('div');
      hdr.className = 'entry-card-header';

      const title = document.createElement('span');
      title.className = 'entry-title';
      const refreshTitle = () => {
        const label = displayPathValue(entry, tmpl.display_item);
        title.textContent = label || `${tmpl.name || tk} #${idx + 1}`;
      };
      refreshTitle();
      hdr.appendChild(title);

      const badge = document.createElement('span');
      badge.className = 'entry-badge';
      badge.textContent = tmpl.name || tk;
      hdr.appendChild(badge);

      const enWrap = document.createElement('span');
      enWrap.className = 'entry-toggle-wrap';
      const en = document.createElement('input');
      en.type = 'checkbox';
      en.className = 'entry-toggle-enable';
      en.checked = entry.enabled !== false;
      en.addEventListener('change', () => {
        entry.enabled = en.checked;
        onchange();
      });
      enWrap.appendChild(en);
      const enLabel = document.createElement('span');
      enLabel.className = entry.enabled === false ? 'entry-disabled' : 'entry-enabled';
      enLabel.textContent = entry.enabled === false ? '已停用' : '已启用';
      enWrap.appendChild(enLabel);
      hdr.appendChild(enWrap);

      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'entry-card-del';
      del.textContent = '🗑';
      del.title = '删除该条目（保存后生效）';
      del.addEventListener('click', () => {
        arr.splice(idx, 1);
        renderEntries();
        onchange();
      });
      hdr.appendChild(del);

      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'entry-card-toggle';
      toggle.textContent = collapsed ? '▸ 展开' : '▽ 收起';
      toggle.addEventListener('click', () => {
        collapsed = !collapsed;
        entry.__collapsed = collapsed;
        body.style.display = collapsed ? 'none' : '';
        toggle.textContent = collapsed ? '▸ 展开' : '▽ 收起';
      });
      hdr.appendChild(toggle);

      card.appendChild(hdr);

      const body = document.createElement('div');
      body.className = 'entry-card-body';
      body.style.display = collapsed ? 'none' : '';
      // 过滤掉已在标题栏显示的 enabled 字段，避免重复
      const itemsSpec = Object.fromEntries(
        Object.entries(tmpl.items || {}).filter(([k]) => k !== 'enabled')
      );
      buildObjectFields(body, itemsSpec, entry, () => {
        refreshTitle();
        onchange();
      });
      card.appendChild(body);

      wrap.appendChild(card);
    });
  };

  renderEntries();
  wrap.refresh = renderEntries;
  return wrap;
}

/* ---------- 主渲染 ---------- */
function updateSubtitle() {
  const n = state.activeServers.length;
  el('cfg-subtitle').textContent = n
    ? `已生效 ${n} 台服务器：${state.activeServers.join('、')}`
    : '暂无已生效服务器（配置保存后热重载生效）';
}

function setDirty(dirty) {
  state.dirty = dirty;
  el('btn-save').disabled = !dirty || state.loading;
  const st = el('cfg-save-state');
  if (dirty) {
    st.textContent = '● 有未保存的修改';
    st.className = 'cfg-save-state dirty';
  } else {
    st.textContent = '';
    st.className = 'cfg-save-state';
  }
}

function toast(msg, type = '') {
  const t = el('cfg-toast');
  t.textContent = msg;
  t.className = `cfg-toast ${type}`.trim();
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), 3200);
}

/* ---------- 主渲染（按进入前的视图只渲染对应部分） ---------- */
function buildViewForm() {
  const form = el('cfg-form');
  form.innerHTML = '';
  const schema = state.schema;
  const view = state.currentView;
  const conf = state.conf;
  const sectionTitle = (text) => {
    const sec = document.createElement('section');
    sec.className = 'cfg-section';
    const title = document.createElement('div');
    title.className = 'cfg-section-title';
    const h = document.createElement('h2');
    h.textContent = text;
    title.appendChild(h);
    sec.appendChild(title);
    return sec;
  };

  // 图床视图：只渲染图床配置（开关 + 超时 + 服务列表）
  if (view === 'image_bed') {
    const sec = sectionTitle('图床配置');
    sec.id = 'sec-image';
    const imgKeys = ['enable_image_upload', 'image_upload_timeout'].filter((k) => schema[k]);
    if (imgKeys.length) {
      buildObjectFields(sec, Object.fromEntries(imgKeys.map((k) => [k, schema[k]])), conf, () => setDirty(true));
    }
    if (schema.image_upload_services) {
      sec.appendChild(buildTemplateList(schema.image_upload_services, conf.image_upload_services, () => setDirty(true), 'sec-image'));
    }
    form.appendChild(sec);
    return;
  }

  // 基础设置（非列表类顶层字段）
  const rootKeys = Object.keys(schema).filter(
    (k) => !['mc_servers', 'image_upload_services'].includes(k)
  );
  if (rootKeys.length) {
    const sec = sectionTitle('基本设置');
    sec.id = 'sec-root';
    buildObjectFields(sec, Object.fromEntries(rootKeys.map((k) => [k, schema[k]])), conf, () => setDirty(true));
    form.appendChild(sec);
  }

  // MC 服务器列表（始终渲染全部服务器卡片；卡片可收起）
  if (schema.mc_servers) {
    const sec = sectionTitle('MC 服务器');
    sec.id = 'sec-mc-servers';
    const servers = Array.isArray(conf.mc_servers) ? conf.mc_servers : [];
    // 在标题栏右侧添加「＋ 添加条目」按钮（多模板时带选择框）
    const tks = Object.keys(schema.mc_servers.templates || {});
    if (tks.length) {
      const titleEl = sec.querySelector('.cfg-section-title');
      const addRow = document.createElement('div');
      addRow.className = 'entry-add-row';
      let sel = null;
      if (tks.length > 1) {
        sel = document.createElement('select');
        sel.className = 'cfg-select';
        sel.style.width = 'auto';
        tks.forEach((tk) => {
          const o = document.createElement('option');
          o.value = tk;
          o.textContent = schema.mc_servers.templates[tk].name || tk;
          sel.appendChild(o);
        });
        addRow.appendChild(sel);
      }
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'entry-add';
      btn.textContent = '＋ 添加条目';
      btn.addEventListener('click', () => {
        const tk = tks.length > 1 ? sel.value : tks[0];
        const tmpl = schema.mc_servers.templates[tk];
        const fresh = { __template_key: tk };
        for (const [k, sub] of Object.entries(tmpl.items || {})) {
          fresh[k] = makeDefault(sub);
        }
        if (fresh.enabled === undefined) fresh.enabled = true;
        conf.mc_servers.push(fresh);
        const listEl = sec.querySelector('.entry-list');
        if (listEl && listEl.refresh) listEl.refresh();
        onchange();
        const cardEl = document.getElementById(`mc-servers-${conf.mc_servers.length - 1}`);
        cardEl?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
      addRow.appendChild(btn);
      titleEl.appendChild(addRow);
    }
    sec.appendChild(buildTemplateList(schema.mc_servers, servers, () => setDirty(true), 'mc-servers'));
    form.appendChild(sec);
  }
}

/* ---------- JSON 模式 ---------- */
function switchMode(toJson) {
  const formPanel = el('cfg-form-panel');
  const jsonPanel = el('cfg-json-panel');
  const btn = el('btn-json-toggle');
  if (toJson) {
    el('cfg-json-text').value = JSON.stringify(state.conf, null, 2);
    formPanel.classList.add('hidden');
    jsonPanel.classList.remove('hidden');
    btn.textContent = '📋 表单模式';
    state.jsonMode = true;
  } else {
    // 切回表单：若 JSON 已被编辑且合法则采用，否则保留 JSON 模式并提示
    const raw = el('cfg-json-text').value.trim();
    if (state.jsonTouched) {
      try {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          state.conf = parsed;
          state.jsonTouched = false;
        } else {
          toast('JSON 顶层需为对象，无法切换到表单模式', 'err');
          return;
        }
      } catch (e) {
        toast(`JSON 语法错误：${e.message}`, 'err');
        return;
      }
    }
    jsonPanel.classList.add('hidden');
    formPanel.classList.remove('hidden');
    btn.textContent = '📝 JSON 模式';
    state.jsonMode = false;
    state.currentView = 'all';
    buildViewForm();
  }
}

/* ---------- 加载与保存 ---------- */
async function load() {
  el('cfg-loading').classList.remove('hidden');
  el('cfg-form').classList.add('hidden');
  state.loading = true;
  try {
    const data = await apiGet('config/full');
    state.conf = data.conf || {};
    state.schema = data.schema || {};
    state.activeServers = data.active_servers || [];
    // 保证列表字段存在
    if (!Array.isArray(state.conf.mc_servers)) state.conf.mc_servers = [];
    if (!Array.isArray(state.conf.image_upload_services)) state.conf.image_upload_services = [];
    // 获取人格列表
    try {
      const personasResp = await apiGet('personas');
      state.personas = personasResp.personas || [];
    } catch (e) {
      console.warn('Failed to load personas:', e);
      state.personas = [];
    }
    updateSubtitle();
    buildViewForm();
    el('cfg-loading').classList.add('hidden');
    el('cfg-form').classList.remove('hidden');
    setDirty(false);
    state.loading = false;
    state.loaded = true;
  } catch (e) {
    console.error('Failed to load config:', e);
    el('cfg-loading').textContent = `加载配置失败：${e.message}`;
    toast(`加载配置失败：${e.message}`, 'err');
    state.loading = false;
  }
}

async function save() {
  let confToSave;
  if (state.jsonMode) {
    try {
      confToSave = JSON.parse(el('cfg-json-text').value);
    } catch (e) {
      toast(`JSON 语法错误：${e.message}`, 'err');
      return;
    }
  } else {
    confToSave = state.conf;
  }
  if (!confToSave || typeof confToSave !== 'object' || Array.isArray(confToSave)) {
    toast('配置必须是一个 JSON 对象', 'err');
    return;
  }
  el('btn-save').disabled = true;
  try {
    const resp = await apiPost('config/save', { conf: confToSave });
    if (resp && resp.saved) {
      state.activeServers = resp.active_servers || [];
      updateSubtitle();
      setDirty(false);
      toast(`✅ 配置已保存并热重载（${state.activeServers.length} 台服务器生效）`, 'ok');
      // 通知 dashboard 面板刷新（服务器列表 / 统计 / 终端可能已变化）
      window.dispatchEvent(new CustomEvent('queqiao:config-saved'));
    } else {
      const msg = (resp && (resp.message || resp.error)) || '保存失败（未知错误）';
      toast(`❌ ${msg}`, 'err');
      setDirty(true);
    }
  } catch (e) {
    toast(`❌ 保存请求失败：${e.message}`, 'err');
    setDirty(true);
  }
}

/* ---------- 视图联动（面板显隐由 app.js 标签切换控制） ---------- */
// dashboard（app.js）切到「⚙ 配置管理」视图时派发 queqiao:config-view-open，
// detail.view 为进入前的视图（'all' | 'image_bed' | 服务器 server_name）；
// 本模块据此只渲染对应部分的表单，同时重新拉取配置
// （首次与每次打开都拉，配置可能被其它入口改动）
function onConfigViewOpen(e) {
  // 进入配置视图时始终渲染全部服务器，不论进入前所在视图
  state.currentView = 'all';
  // 每次进入配置视图都从表单态开始（三态循环第①步），即使上次离开时
  // 停留在 JSON 模式：复位面板显隐与切换按钮文案
  state.jsonMode = false;
  state.jsonTouched = false;
  const formPanel = el('cfg-form-panel');
  const jsonPanel = el('cfg-json-panel');
  if (formPanel) formPanel.classList.remove('hidden');
  if (jsonPanel) jsonPanel.classList.add('hidden');
  const btn = el('btn-json-toggle');
  if (btn) btn.textContent = '📝 JSON 模式';
  load();
}

/* ---------- 事件绑定 ---------- */
function bindEvents() {
  // 入口：顶部「⚙️ 设置」旁的「⚙️ 配置管理」按钮，三态循环：
  //   ① 非配置视图点击 → 进入配置表单视图（app.js 记录进入前视图并派发
  //      queqiao:config-view-open，表单只渲染对应部分）；
  //   ② 配置表单态再点 → app.js 派发 queqiao:config-toggle-json，切全部 JSON；
  //   ③ 配置 JSON 态再点 → 派发 queqiao:config-view-return，app.js 返回原视图。
  // 面板内「📝 JSON 模式」按钮为双向手动切换，不参与返回。
  window.addEventListener('queqiao:config-view-open', onConfigViewOpen);
  window.addEventListener('queqiao:config-toggle-json', () => {
    if (state.jsonMode) {
      window.dispatchEvent(new CustomEvent('queqiao:config-view-return'));
    } else {
      switchMode(true);
    }
  });
  el('btn-json-toggle')?.addEventListener('click', () => switchMode(!state.jsonMode));
  el('btn-save')?.addEventListener('click', save);
  el('cfg-json-text')?.addEventListener('input', () => {
    state.jsonTouched = true;
    setDirty(true);
  });
}

// dashboard（app.js）在 DOMContentLoaded 中加载 config-view；本模块此时
// DOM 已就绪，直接绑定
bindEvents();
