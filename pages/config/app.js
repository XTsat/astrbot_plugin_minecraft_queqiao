/* Minecraft 鹊桥互通 - 配置管理页
 * 通过 AstrBot Plugin Page Bridge 调用后端 Web API：
 *   GET  config/full  → { conf, schema, active_servers, data_dir }
 *   POST config/save  → { conf } → { saved, active_servers }
 * 可视化表单由 _conf_schema.json 驱动；JSON 模式直接编辑完整配置。
 */
const PLUGIN_PATH = 'astrbot_plugin_minecraft_queqiao';

const el = (id) => document.getElementById(id);
const bridge = window.AstrBotPluginPage || null;

const state = {
  conf: {},
  schema: {},
  activeServers: [],
  dirty: false,
  jsonMode: false,
  jsonTouched: false,
  loading: true,
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
  switch (spec.type) {
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
function createControl(spec, onchange) {
  switch (spec.type) {
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
    default:
      return null;
  }
}

/* ---------- 字段渲染 ---------- */
function buildFieldRow(key, spec, target, onchange, opts = {}) {
  const { compact = false, noLabelDesc = false } = opts;
  const row = document.createElement('div');
  row.className = 'field-row' + (compact ? ' compact' : '');

  const label = document.createElement('div');
  label.className = 'field-label';
  const name = document.createElement('div');
  name.className = 'field-name';
  name.textContent = key;
  label.appendChild(name);
  if (!noLabelDesc && spec.description) {
    const d = document.createElement('div');
    d.className = 'field-desc';
    d.appendChild(renderDesc(spec.description));
    label.appendChild(d);
  }
  row.appendChild(label);

  const ctrl = document.createElement('div');
  ctrl.className = 'field-control';

  if (spec.type === 'object') {
    const grp = document.createElement('div');
    grp.className = 'field-group';
    const hdr = document.createElement('div');
    hdr.className = 'field-group-header';
    const t = document.createElement('span');
    t.className = 'group-title';
    t.textContent = key;
    hdr.appendChild(t);
    if (spec.hint) {
      const h = document.createElement('span');
      h.className = 'group-hint';
      h.textContent = spec.hint;
      hdr.appendChild(h);
    }
    grp.appendChild(hdr);
    const body = document.createElement('div');
    body.className = 'field-group-body';
    if (typeof target[key] !== 'object' || target[key] === null) target[key] = {};
    buildObjectFields(body, spec.items || {}, target[key], onchange, compact);
    grp.appendChild(body);
    ctrl.appendChild(grp);
  } else if (spec.type === 'template_list') {
    if (!Array.isArray(target[key])) target[key] = [];
    ctrl.appendChild(buildTemplateList(spec, target[key], onchange, opts.entryIdPrefix));
  } else {
    const control = createControl(spec, onchange);
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
    if (spec.hint) {
      const h = document.createElement('div');
      h.className = 'field-hint';
      h.textContent = spec.hint;
      ctrl.appendChild(h);
    }
  }

  row.appendChild(ctrl);
  return row;
}

function buildObjectFields(container, itemsSpec, target, onchange, compact = false) {
  for (const [key, spec] of Object.entries(itemsSpec || {})) {
    container.appendChild(buildFieldRow(key, spec, target, onchange, { compact }));
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

      const en = document.createElement('span');
      en.className = entry.enabled === false ? 'entry-disabled' : 'entry-enabled';
      en.textContent = entry.enabled === false ? '已停用' : '已启用';
      hdr.appendChild(en);

      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'btn btn-sm btn-danger';
      del.textContent = '🗑';
      del.title = '删除该条目（保存后生效）';
      del.addEventListener('click', () => {
        arr.splice(idx, 1);
        renderEntries();
        onchange();
        refreshNavTitles();
      });
      hdr.appendChild(del);

      card.appendChild(hdr);

      const body = document.createElement('div');
      body.className = 'entry-card-body';
      buildObjectFields(body, tmpl.items || {}, entry, () => {
        refreshTitle();
        onchange();
        refreshNavTitles();
      }, true);
      card.appendChild(body);

      wrap.appendChild(card);
    });

    // 添加行：多模板时先选模板
    if (tks.length) {
      const addRow = document.createElement('div');
      addRow.className = 'entry-add-row';
      const sel = document.createElement('select');
      sel.className = 'cfg-select';
      sel.style.width = 'auto';
      tks.forEach((tk) => {
        const o = document.createElement('option');
        o.value = tk;
        o.textContent = spec.templates[tk].name || tk;
        sel.appendChild(o);
      });
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'entry-add';
      btn.textContent = '＋ 添加条目';
      btn.addEventListener('click', () => {
        const tk = sel.value;
        const tmpl = spec.templates[tk];
        const fresh = { __template_key: tk };
        for (const [k, sub] of Object.entries(tmpl.items || {})) {
          fresh[k] = makeDefault(sub);
        }
        if (fresh.enabled === undefined) fresh.enabled = true;
        arr.push(fresh);
        renderEntries();
        onchange();
        refreshNavTitles();
        if (entryIdPrefix) {
          const cardEl = document.getElementById(`${entryIdPrefix}-${arr.length - 1}`);
          cardEl?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      });
      addRow.appendChild(sel);
      addRow.appendChild(btn);
      wrap.appendChild(addRow);
    }
  };

  renderEntries();
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

function scrollToSection(id) {
  const node = document.getElementById(id);
  if (node) node.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function navGroup(title) {
  const g = document.createElement('div');
  g.className = 'nav-group-title';
  g.textContent = title;
  return g;
}

function navItem(label, onClick, active = false) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'nav-item' + (active ? ' active' : '');
  b.textContent = label;
  b.addEventListener('click', onClick);
  return b;
}

const navServerLabels = {};

function renderNav() {
  const nav = el('cfg-nav');
  nav.innerHTML = '';
  nav.appendChild(navGroup('配置'));
  nav.appendChild(navItem('基本设置', () => scrollToSection('sec-root'), true));

  const servers = Array.isArray(state.conf.mc_servers) ? state.conf.mc_servers : [];
  if (servers.length) {
    nav.appendChild(navGroup('MC 服务器'));
    servers.forEach((s, i) => {
      const label = displayPathValue(s, 'server.display_name') || s.server_name || `服务器 #${i + 1}`;
      navServerLabels[i] = label;
      nav.appendChild(navItem(`🖥️ ${label}`, () => scrollToSection(`sec-server-${i}`)));
    });
  }
  if (state.schema.image_upload_services) {
    nav.appendChild(navGroup('图片转存'));
    nav.appendChild(navItem('图片转存服务', () => scrollToSection('sec-image')));
  }
}

function refreshNavTitles() {
  const servers = Array.isArray(state.conf.mc_servers) ? state.conf.mc_servers : [];
  servers.forEach((s, i) => {
    const label = displayPathValue(s, 'server.display_name') || s.server_name || `服务器 #${i + 1}`;
    if (navServerLabels[i] === label) return;
    navServerLabels[i] = label;
  });
  renderNav();
}

function buildForm() {
  const form = el('cfg-form');
  form.innerHTML = '';
  const schema = state.schema;

  // 分区 1：基本设置（非列表类顶层字段）
  const rootKeys = Object.keys(schema).filter(
    (k) => !['mc_servers', 'image_upload_services'].includes(k)
  );
  if (rootKeys.length) {
    const sec = document.createElement('section');
    sec.className = 'cfg-section';
    sec.id = 'sec-root';
    const title = document.createElement('div');
    title.className = 'cfg-section-title';
    title.innerHTML = '<h2>基本设置</h2>';
    sec.appendChild(title);
    const target = state.conf;
    buildObjectFields(sec, Object.fromEntries(rootKeys.map((k) => [k, schema[k]])), target, () => setDirty(true));
    form.appendChild(sec);
  }

  // 分区 2：MC 服务器列表
  if (schema.mc_servers) {
    const sec = document.createElement('section');
    sec.className = 'cfg-section';
    sec.id = 'sec-servers';
    const title = document.createElement('div');
    title.className = 'cfg-section-title';
    const h = document.createElement('h2');
    h.textContent = 'MC 服务器列表';
    title.appendChild(h);
    if (schema.mc_servers.description) {
      const d = document.createElement('span');
      d.className = 'cfg-section-desc';
      d.textContent = schema.mc_servers.description;
      title.appendChild(d);
    }
    sec.appendChild(title);
    sec.appendChild(buildTemplateList(schema.mc_servers, state.conf.mc_servers, () => setDirty(true), 'sec-server'));
    form.appendChild(sec);
  }

  // 分区 3：图片转存服务
  if (schema.image_upload_services) {
    const sec = document.createElement('section');
    sec.className = 'cfg-section';
    sec.id = 'sec-image';
    const title = document.createElement('div');
    title.className = 'cfg-section-title';
    const h = document.createElement('h2');
    h.textContent = '图片转存服务';
    title.appendChild(h);
    if (schema.image_upload_services.description) {
      const d = document.createElement('span');
      d.className = 'cfg-section-desc';
      d.textContent = schema.image_upload_services.description;
      title.appendChild(d);
    }
    sec.appendChild(title);
    sec.appendChild(buildTemplateList(schema.image_upload_services, state.conf.image_upload_services, () => setDirty(true), 'sec-image'));
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
    buildForm();
    renderNav();
  }
}

/* ---------- 加载与保存 ---------- */
async function load() {
  el('cfg-loading').classList.remove('hidden');
  el('cfg-form').classList.add('hidden');
  try {
    const data = await apiGet('config/full');
    state.conf = data.conf || {};
    state.schema = data.schema || {};
    state.activeServers = data.active_servers || [];
    // 保证列表字段存在
    if (!Array.isArray(state.conf.mc_servers)) state.conf.mc_servers = [];
    if (!Array.isArray(state.conf.image_upload_services)) state.conf.image_upload_services = [];
    updateSubtitle();
    renderNav();
    buildForm();
    el('cfg-loading').classList.add('hidden');
    el('cfg-form').classList.remove('hidden');
    setDirty(false);
    state.loading = false;
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

/* ---------- 事件绑定 ---------- */
el('btn-json-toggle').addEventListener('click', () => switchMode(!state.jsonMode));
el('btn-save').addEventListener('click', save);
el('cfg-json-text').addEventListener('input', () => {
  state.jsonTouched = true;
  setDirty(true);
});

load();
