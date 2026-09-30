/**
 * Minecraft QueQiao Plugin - Dashboard Logic
 */

// 新建服务器时的默认值，与 core/constants.py 的 DEFAULT_WS_URL / _conf_schema.json 保持一致
const DEFAULT_WS_URL = 'ws://127.0.0.1:8080/minecraft/ws';
const DEFAULT_SERVER_NAME = 'Server';

// 图床面板的视图键（顶部标签 data-view）：独立于 'all' 与各服务器名，
// renderServerTabs 的 valid 判定需显式放行，不能落进「服务器视图」分支
const IMAGE_BED_VIEW = 'image_bed';
// 配置管理视图键（顶部标签 data-view）：与图床一致，作为内嵌面板切换
const CONFIG_VIEW = 'config_view';

// MC 格式码到 CSS 类名的映射
const MC_COLOR_MAP = {
  '0': 'mc-black',
  '1': 'mc-dark-blue',
  '2': 'mc-dark-green',
  '3': 'mc-dark-aqua',
  '4': 'mc-dark-red',
  '5': 'mc-dark-purple',
  '6': 'mc-gold',
  '7': 'mc-gray',
  '8': 'mc-dark-gray',
  '9': 'mc-blue',
  'a': 'mc-green',
  'b': 'mc-aqua',
  'c': 'mc-red',
  'd': 'mc-light-purple',
  'e': 'mc-yellow',
  'f': 'mc-white',
  'l': 'mc-bold',
  'm': 'mc-strikethrough',
  'n': 'mc-underlined',
  'o': 'mc-italic',
  'k': 'mc-obfuscated',
  'r': 'mc-reset',
};

// 剥离/转换 MC 颜色代码为带样式的 HTML
function renderMcText(rawText) {
  if (!rawText) return '';
  const parts = rawText.split('§');
  if (parts.length === 1) return escapeHtml(parts[0]);

  let html = escapeHtml(parts[0]);
  let currentClasses = [];

  for (let i = 1; i < parts.length; i++) {
    const part = parts[i];
    if (!part) continue;
    const code = part.charAt(0).toLowerCase();
    const text = part.slice(1);

    if (code === 'r') {
      currentClasses = [];
    } else if (MC_COLOR_MAP[code]) {
      if (code >= '0' && code <= 'f') {
        currentClasses = currentClasses.filter(c => !c.startsWith('mc-') || ['mc-bold', 'mc-italic', 'mc-underlined', 'mc-strikethrough'].includes(c));
        currentClasses.push(MC_COLOR_MAP[code]);
      } else {
        currentClasses.push(MC_COLOR_MAP[code]);
      }
    }

    if (text) {
      if (currentClasses.length > 0) {
        html += `<span class="${currentClasses.join(' ')}">${escapeHtml(text)}</span>`;
      } else {
        html += escapeHtml(text);
      }
    }
  }
  return html;
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// 字节数 → 人类可读 MB 文本（1024 进制，与后端 usage_text 口径一致）
function fmtMB(size) {
  if (!(typeof size === 'number' && size > 0)) return '--';
  return `${(size / 1024 / 1024).toFixed(1)}MB`;
}

// 状态时间戳（秒）→ 「刚刚 / N 秒前 / N 分钟前 / N 小时前」
function formatAgeText(tsSeconds) {
  if (!(typeof tsSeconds === 'number' && tsSeconds > 0)) return '';
  const ageSec = Math.max(0, Math.floor(Date.now() / 1000 - tsSeconds));
  if (ageSec < 5) return '刚刚';
  if (ageSec < 60) return `${ageSec} 秒前`;
  if (ageSec < 3600) return `${Math.floor(ageSec / 60)} 分钟前`;
  return `${Math.floor(ageSec / 3600)} 小时前`;
}

class DashboardApp {
  constructor() {
    this.bridge = window.AstrBotPluginPage || null;
    this.servers = [];
    this.stats = null;
    this.refreshInterval = null;
    this.isRefreshing = false;
    // 当前激活的服务器视图标签（'all' 或 server_name）。刷新页面时保留
    // 上一次打开的服务器视图（localStorage 加速首屏，后端无此状态）。
    // 受限 iframe 下 localStorage 可能被沙箱禁止，一律 try/catch 兜底；
    // 服务器被删除时 renderServerTabs 的 valid 检查会回退全局视图。
    // 配置管理视图不持久化：刷新后回到正常主页面（'all'）
    this.activeServerTab = 'all';
    try {
      const savedTab = localStorage.getItem('queqiao_active_tab');
      if (savedTab && savedTab !== 'all' && savedTab !== CONFIG_VIEW) {
        this.activeServerTab = savedTab;
      }
    } catch (e) {
      this.activeServerTab = 'all';
    }
    this.defaultServerIcon = './default-server-icon.png';
    // 性能监控状态
    this.monitorRange = '24'; // 分析时间窗（小时）
    // 性能监控子页面（'tps' | 'latency'）：默认展示项由后端持久化
    // （server.monitor.default_tab，存 settings.json，不依赖浏览器存储）。
    // _defaultTabServer 记录已应用默认展示项的服务器：切换服务器时
    // 重新套用该服务器的默认子页面，同一服务器内手动切换保持
    this.monitorTab = 'tps';
    this._defaultTabServer = null;
    this.monitorSeriesCache = new Map(); // server_name -> 最近一次 series payload
    this.isMonitorLoading = false;
    // 实时模式：连续采样 + 高频刷新最近 60 秒（realtimeActive 标记、timer 句柄）。
    // 频率 realtimeInterval（秒）来自后端设置（默认 5，1~60）
    this.realtimeActive = false;
    this.realtimeTimer = null;
    this.realtimeInterval = 5;
    // 实时链代次标记：每次 startRealtime/stopRealtime 递增；进行中的刷新
    // await 完成后比较 round，不匹配即自然消亡——任何断链后重新切实时
    // 按钮必启动新链，绝不因 realtimeActive 残留哑火
    this._realtimeRound = 0;
    // 自动刷新轮询间隔（秒）：后端设置持久化（默认 10，10~3600）
    this.autoRefreshInterval = 10;
    this.chartState = null; // { canvas, opts } 供 resize/hover 重算
    // 互通终端轮询句柄：单服务器视图下 4 秒增量拉取，切换视图时停止
    this.terminalPollTimer = null;
    // 互通终端自动滚动：开启时新消息自动滚到底部；关闭时停在当前位置
    // 阅读历史（保持关闭，直到再次点击按钮）
    this.terminalAutoscroll = true;
    // 互通终端加载天数：每台服务器独立配置（conf 条目顶层 terminal_days，
    // 缺省 2），由 terminalDaysFor() 按当前服务器读取，启动时无全局缓存
    // 顶部自动刷新开关：启动缓存与 terminal_days 同模式——权威数据在后端
    // panel_prefs.json（init 异步拉取覆盖），localStorage 仅加速首屏恢复
    let savedAuto = null;
    try {
      const rawAuto = localStorage.getItem('queqiao_auto_refresh');
      if (rawAuto === '1') savedAuto = true;
      else if (rawAuto === '0') savedAuto = false;
    } catch (e) {
      savedAuto = null;
    }
    this.autoRefreshPref = savedAuto;
    // 自动刷新间隔的**全局偏好**（后端 panel_prefs.json 的
    // auto_refresh_interval）：null 时回落每台服务器监控设置里的
    // auto_refresh_interval。该间隔不再属于监控参数（监控弹窗已瘦身），
    // 改由「功能设置」面板维护
    this.autoRefreshIntervalPref = null;
    // 「功能设置」面板折叠状态（后端 panel_prefs.json 的 settings_collapsed）：
    // 默认展开——开关存在的意义就是被看见，折叠只用于临时腾出纵向空间
    this.settingsCollapsed = true;
    // conf（mc_servers）里的服务器条目，含**未启用**的条目：来自
    // /config/servers。未启用条目在运行时不会建实例（main 层启动时跳过），
    // 此前在这块面板上完全不可见，只能改配置文件才能启用。现在以灰色卡片
    // 呈现，点进去即可启用/编辑/删除
    this.configServers = [];
    this.serverFormMode = null; // 'create' | 'edit'：服务器弹窗当前模式
    // 图床面板状态：status 为 /image_bed/status 的原始响应；entries 为
    // /config/image_bed 的原始条目（含 __template_key，表单编辑回显用）。
    // 面板数据独立于服务器视图轮询：进入图床视图时单独拉取，保存走
    // 局部生效（免重连 MC）
    this.imageBedStatus = null;
    this.imageBedEntries = [];
    this.imageBedFormMode = null; // 'create' | 'edit'
    this.imageBedFormIndex = null;
    this.imageBedTesting = false;
    this.imageBedTestResults = {}; // index → {cls, html}：自动刷新重绘后回填单条目测试结果
    this.imageBedMasterEnabled = true; // 根级总开关（启动缓存；权威由后端回拉）
    this.imageBedTimeout = 30; // 上传超时（秒）
    // 模板清单缓存（/image_bed/templates 返回 {key: {name, hint, defaults}}）：
    // 新建表单切换模板时用 defaults 预填字段；成功拉取后重建模板下拉
    this.imageBedTemplates = null;
    // 模板选择器里除 builtin/custom 外的第三方模板键（与 _conf_schema.json
    // 的 image_upload_services.templates 键集合对齐；后端模板接口未拉到时兜底）
    this.imageBedTemplateKeys = [
      'builtin_http', 'custom', 'catbox', 'litterbox', 'imglink', 'imgloc',
      'img402', 'pngurl', 'see', 'imgbb', 'picui', 'anyapi', 'xinyew', 'xunjinlu',
    ];
  }

  async init() {
    this.initThemeSync();
    this.initDefaultIcon();
    this.bindEvents();
    this.bindTerminalActions();
    this.bindMonitorActions();
    this.bindSettingsActions();
    this.bindImageBedActions();

    if (this.bridge) {
      try {
        await this.bridge.ready();
        this.applyThemeFromBridge();
        if (typeof this.bridge.onContext === 'function') {
          this.bridge.onContext(() => {
            this.applyThemeFromBridge();
          });
        }
      } catch (err) {
        console.warn('Bridge ready warning:', err);
      }
    } else {
      console.warn('window.AstrBotPluginPage not found; falling back to direct HTTP mode');
    }

    // 打开页面首次加载同样强制探测一次 RCON（与手动刷新一致）；
    // 之后的自动轮询不强制，避免向未开启 RCON 的鹊桥端反复发请求刷报错
    await this.refreshAll(false, true);
    // 自动刷新间隔 / 实时显示频率：长期存储在后端（每台服务器 settings.json），
    // 前端按「当前激活服务器 → 第一台」读取；切换服务器视图时重新同步
    // （activateServerTab）。此前用 localStorage 记录最后保存值，但受限
    // iframe 沙箱可能禁止 localStorage、清缓存即丢——后端持久化才是真相
    this.syncMonitorFreqFromBackend();
    // 面板偏好（互通终端加载天数等）：权威数据在后端 panel_prefs.json，
    // 异步拉取覆盖本地启动缓存（localStorage 仅加速首屏，以后端为准）
    this.loadPanelPrefs();
    this.syncAutoRefreshLabel();
    // 自动刷新默认关闭（防止对鹊桥持续轮询刷屏）；先按 localStorage 启动
    // 缓存恢复勾选（加速首屏），权威值随后由 loadPanelPrefs 异步覆盖
    const cachedAuto = this.autoRefreshPref;
    if (cachedAuto !== null) {
      const toggle = document.getElementById('auto-refresh-toggle');
      if (toggle) toggle.checked = cachedAuto;
    }
    this.setupAutoRefresh(
      document.getElementById('auto-refresh-toggle')?.checked || false
    );
  }

  initDefaultIcon() {
    const preloadImg = document.getElementById('default-server-icon-preload');
    if (preloadImg) {
      this.defaultServerIcon = preloadImg.currentSrc || preloadImg.src || './default-server-icon.png';
    }
  }

  initThemeSync() {
    // 1. 若 URL query 显式包含 ?theme=dark / light，预先设定
    const urlParams = new URLSearchParams(window.location.search);
    const themeParam = urlParams.get('theme');
    if (themeParam === 'dark' || themeParam === 'light') {
      document.documentElement.setAttribute('data-theme', themeParam);
    }

    // 2. 监听系统 prefers-color-scheme 变化
    if (window.matchMedia) {
      const darkMedia = window.matchMedia('(prefers-color-scheme: dark)');
      darkMedia.addEventListener('change', (e) => {
        if (!document.documentElement.getAttribute('data-theme')) {
          document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
        }
      });
    }
  }

  applyThemeFromBridge() {
    if (!this.bridge || typeof this.bridge.getContext !== 'function') return;
    const ctx = this.bridge.getContext();
    if (ctx && typeof ctx.isDark === 'boolean') {
      document.documentElement.setAttribute('data-theme', ctx.isDark ? 'dark' : 'light');
    }
  }

  bindEvents() {
    // 配置视图（config-view.js）保存成功后通知本面板刷新：
    // 服务器列表 / 统计 / 连接状态可能已变化，静默刷新即可
    window.addEventListener('queqiao:config-saved', () => {
      this.refreshAll(true, true);
    });
    document.getElementById('btn-refresh')?.addEventListener('click', () => {
      // 手动刷新强制重新探测一次 RCON（自动轮询不强制，避免向未开启
      // RCON 的鹊桥端反复发 send_rcon_command、在 MC 控制台刷报错）
      this.refreshAll(false, true);
    });

    const autoToggle = document.getElementById('auto-refresh-toggle');
    autoToggle?.addEventListener('change', (e) => {
      const on = !!e.target.checked;
      this.setupAutoRefresh(on);
      this.saveAutoRefreshPref(on);
    });

    // 服务器条目弹窗（新建 / 编辑 / 启用 / 删除）
    document.getElementById('btn-new-server')?.addEventListener('click', () => {
      this.openServerForm('create');
    });
    document.getElementById('sf-close')?.addEventListener('click', () => this.closeServerForm());
    document.getElementById('sf-cancel')?.addEventListener('click', () => this.closeServerForm());
    document.getElementById('sf-save')?.addEventListener('click', () => this.submitServerForm());
    document.getElementById('sf-delete')?.addEventListener('click', () => this.deleteServerEntry());
    document.getElementById('sf-mode')?.addEventListener('change', () => this.syncServerFormModeRows());
    const sfOverlay = document.getElementById('server-form-modal');
    sfOverlay?.addEventListener('click', (e) => {
      if (e.target === sfOverlay) this.closeServerForm();
    });
    // 回车提交（多行目标会话框除外）
    document.getElementById('server-form-modal')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT') {
        e.preventDefault();
        this.submitServerForm();
      }
    });

    // 图床面板：顶部标签 / 总开关 / 超时 / 测试上传 / 条目管理
    document.getElementById('tab-image-bed')?.addEventListener('click', () => {
      this.activateServerTab(IMAGE_BED_VIEW);
    });
    // 配置管理：顶部「⚙️ 设置」旁按钮。三态循环：
    // ① 非配置视图点击 → 进入配置表单视图，记录进入前的视图（_configReturnView），
    //    表单只渲染当前视图对应部分（图床→图床配置、服务器→该服务器、全局→基本设置）
    // ② 配置视图表单态再点 → 切全部 JSON（config-view.js 收到后执行 switchMode(true)）
    // ③ 配置视图 JSON 态再点 → config-view.js 派发 queqiao:config-view-return，
    //    本监听回到进入前的视图，而不是在两个配置之间循环
    document.getElementById('btn-config-view')?.addEventListener('click', () => {
      if (!this.isConfigView()) {
        this._configReturnView = this.activeServerTab;
        this.activateServerTab(CONFIG_VIEW);
      } else {
        window.dispatchEvent(new CustomEvent('queqiao:config-toggle-json'));
      }
    });
    // JSON 态再点按钮时返回进入前的视图（由 config-view.js 派发返回事件）
    window.addEventListener('queqiao:config-view-return', () => {
      const view = this._configReturnView || 'all';
      this._configReturnView = null;
      this.activateServerTab(view);
    });
    document.getElementById('ib-enabled')?.addEventListener('change', (e) => {
      this.toggleImageBed(!!e.target.checked);
    });
    document.getElementById('ib-timeout')?.addEventListener('change', () => {
      this.saveImageBedTimeout();
    });
    document.getElementById('ib-test')?.addEventListener('click', () => {
      this.testImageBed();
    });
    document.getElementById('ib-new')?.addEventListener('click', () => {
      this.openImageBedForm('create');
    });
    document.getElementById('ibf-close')?.addEventListener('click', () => this.closeImageBedForm());
    document.getElementById('ibf-cancel')?.addEventListener('click', () => this.closeImageBedForm());
    document.getElementById('ibf-save')?.addEventListener('click', () => this.submitImageBedForm());
    document.getElementById('ibf-delete')?.addEventListener('click', () => this.deleteImageBedEntry());
    document.getElementById('ibf-template')?.addEventListener('change', () => {
      // 新建模式切模板 = 换一种图床方案：整体重置为新模板默认值；
      // 编辑模式仅回填空字段（不覆盖条目已有数据）
      this.syncImageBedFormTemplate(this.imageBedFormMode === 'create');
    });
    const ibfOverlay = document.getElementById('image-bed-form-modal');
    ibfOverlay?.addEventListener('click', (e) => {
      if (e.target === ibfOverlay) this.closeImageBedForm();
    });
    document.getElementById('image-bed-form-modal')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT') {
        e.preventDefault();
        this.submitImageBedForm();
      }
    });
    // 条目操作：容器内事件委托（列表每次重渲染，避免重复绑定）
    document.getElementById('ib-list')?.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-ib-action]');
      if (!btn) return;
      const index = btn.dataset.index;
      const action = btn.dataset.ibAction;
      if (action === 'edit') this.openImageBedForm('edit', index);
      else if (action === 'toggle') this.toggleImageBedEntry(index);
      else if (action === 'delete') this.deleteImageBedEntry(index);
      else if (action === 'test') this.testImageBedEntry(index);
    });
  }

  // 顶部自动刷新开关持久化：后端 panel_prefs.json 为权威（换设备/清缓存
  // 均保持），localStorage 仅作启动缓存；受限 iframe 下 localStorage 可能
  // 被禁，失败仅影响本次会话，不阻断页面
  async saveAutoRefreshPref(on) {
    try {
      localStorage.setItem('queqiao_auto_refresh', on ? '1' : '0');
    } catch (e) {
      // 忽略：仅本次会话生效
    }
    try {
      await this.apiPost('panel/prefs', { auto_refresh: on });
    } catch (e) {
      console.warn('保存自动刷新偏好失败:', e);
    }
  }

  setupAutoRefresh(enable) {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
    if (enable) {
      // 间隔取后端设置（秒），越界时按 10~3600 收拢
      const secs = Math.max(10, Math.min(3600, this.autoRefreshInterval || 10));
      this.refreshInterval = setInterval(() => {
        this.refreshAll(true);
      }, secs * 1000);
    }
  }

  async apiGet(endpoint, params = {}) {
    if (this.bridge && typeof this.bridge.apiGet === 'function') {
      return await this.bridge.apiGet(endpoint, params);
    }
    const query = new URLSearchParams(params).toString();
    const url = `/api/v1/plugins/extensions/astrbot_plugin_minecraft_queqiao/${endpoint}${query ? '?' + query : ''}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  }

  async apiPost(endpoint, body = {}) {
    if (this.bridge && typeof this.bridge.apiPost === 'function') {
      return await this.bridge.apiPost(endpoint, body);
    }
    const url = `/api/v1/plugins/extensions/astrbot_plugin_minecraft_queqiao/${endpoint}`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  }

  async refreshAll(silent = false, force = false) {
    if (this.isRefreshing) return;
    this.isRefreshing = true;

    const refreshBtn = document.getElementById('btn-refresh');
    if (refreshBtn && !silent) {
      refreshBtn.classList.add('loading');
      refreshBtn.disabled = true;
    }

    try {
      // 1. 获取服务器列表（带超时：后端/网络卡死时若 fetch 永不返回，
      // isRefreshing 防重入锁会永久 true → 自动刷新与手动刷新双双哑火，
      // 整页"静默冻住"——与实时模式此前的"fetch 挂起卡死链"同病）
      const serversData = await Promise.race([
        this.apiGet('servers', force ? { force: 1 } : {}),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('服务器列表请求超时')), 10000)
        ),
      ]);
      this.servers = serversData?.servers || [];

      // 1b. 配置中的服务器条目（含未启用）：失败不影响主流程，只丢灰卡区
      try {
        const confServers = await Promise.race([
          this.apiGet('config/servers'),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('配置服务器列表请求超时')), 8000)
          ),
        ]);
        this.configServers = confServers?.servers || [];
      } catch (e) {
        console.warn('Failed to fetch config servers:', e);
      }

      // 2. 获取统计数据（独立超时，失败不影响列表渲染）
      try {
        this.stats = await Promise.race([
          this.apiGet('stats'),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('统计请求超时')), 8000)
          ),
        ]);
      } catch (e) {
        console.warn('Failed to fetch stats:', e);
      }

      // 3. 渲染界面（输入框与终端输出独立于服务器卡片区，不会被重建打断）
      this.renderServerTabs();
      if (this.isImageBedView() || this.isConfigView()) {
        // 图床/配置视图：不渲染服务器统计/卡片/终端/监控（stats-grid 与
        // layout-main 已在 activateServerTab 隐藏）；仅同步图床面板。
        // 静默刷新（自动轮询）不重拉图床数据，避免后台空转
        if (this.isImageBedView() && !silent) await this.loadImageBedStatus();
      } else {
        this.renderOverview();
        this.renderServers();
        await this.renderTerminal();
        this.renderMonitorPanel();
        this.renderSettingsPanel();
      }
      this.updateLastRefreshTime();
    } catch (err) {
      console.error('Refresh failed:', err);
      if (!silent) {
        this.showToast('刷新失败: ' + (err.message || '网络错误'), 'error');
      }
    } finally {
      this.isRefreshing = false;
      if (refreshBtn) {
        refreshBtn.classList.remove('loading');
        refreshBtn.disabled = false;
      }
    }
  }

  updateLastRefreshTime() {
    const el = document.getElementById('last-refresh-time');
    if (el) {
      const now = new Date();
      el.textContent = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
    }
  }

  // 顶部「自动刷新 (Ns)」按钮文字与当前间隔保持同步
  syncAutoRefreshLabel() {
    const label = document.querySelector('.auto-refresh-toggle span');
    if (label) {
      label.textContent = `自动刷新 (${this.autoRefreshInterval}s)`;
    }
  }

  // 自动刷新间隔 / 实时显示频率以后端设置（每台服务器 settings.json 持久化）
  // 为准：当前激活服务器优先，全局视图回落第一台。此前曾用 localStorage
  // 记录「最后保存值」，但受限 iframe 沙箱可能禁止 localStorage、清缓存即丢
  syncMonitorFreqFromBackend() {
    const server = this.activeServerObject() ||
      (this.servers && this.servers[0]) || null;
    const m = server && server.monitor;
    // 自动刷新间隔：优先「功能设置」面板的全局偏好（panel_prefs.json），
    // 未设置时回落该服监控设置里的同名字段（历史配置继续生效，不回退默认值）
    if (Number.isFinite(this.autoRefreshIntervalPref)) {
      this.autoRefreshInterval =
        Math.max(10, Math.min(3600, this.autoRefreshIntervalPref));
    } else if (m && Number.isFinite(m.auto_refresh_interval)) {
      this.autoRefreshInterval =
        Math.max(10, Math.min(3600, m.auto_refresh_interval));
    }
    if (m && Number.isFinite(m.realtime_interval)) {
      this.realtimeInterval =
        Math.max(1, Math.min(60, m.realtime_interval));
    }
    this.syncAutoRefreshLabel();
  }

  // 面板级偏好（互通终端加载天数等）：权威数据在后端 panel_prefs.json
  // （长期存储），异步拉取并覆盖本地启动缓存；失败时保留现有值不阻断
  async loadPanelPrefs() {
    try {
      const resp = await Promise.race([
        this.apiGet('panel/prefs'),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('面板偏好请求超时')), 5000)
        ),
      ]);
      const prefs = (resp && resp.prefs) || {};
      // 互通终端加载天数已迁移为每台服务器独立配置（conf 条目顶层），
      // 不再从全局偏好读取；此处保留后端兼容字段，但不再覆盖任何值
      // 自动刷新间隔（全局偏好，10~3600）：后端为权威，覆盖启动缓存并
      // 按新间隔重建定时器（保持当前开关状态），顶部标签同步刷新
      if (Number.isFinite(prefs.auto_refresh_interval)) {
        this.autoRefreshIntervalPref =
          Math.max(10, Math.min(3600, prefs.auto_refresh_interval));
        this.autoRefreshInterval = this.autoRefreshIntervalPref;
        this.syncAutoRefreshLabel();
        this.setupAutoRefresh(
          document.getElementById('auto-refresh-toggle')?.checked || false
        );
      }
      // 「功能设置」面板折叠状态：后端记忆（不反向回写，避免加载即覆盖）
      if (typeof prefs.settings_collapsed === 'boolean') {
        this.setSettingsCollapsed(prefs.settings_collapsed, { persist: false });
      }
      // 自动刷新开关：后端为权威，覆盖启动缓存并重建定时器
      if (typeof prefs.auto_refresh === 'boolean') {
        const toggle = document.getElementById('auto-refresh-toggle');
        if (toggle) toggle.checked = prefs.auto_refresh;
        this.setupAutoRefresh(prefs.auto_refresh);
      }
      // 恢复上次打开的服务器视图：权威在后端（localStorage 在沙箱
      // iframe 下不可用）。此时 refreshAll 已完成、servers 已填充；
      // 无效值（服务器已被删除）由 renderServerTabs 的 valid 检查兜底
      // 回退全局视图。仅切视图不回写，避免「读取即覆盖」
      if (typeof prefs.active_tab === 'string') {
        const savedTab = prefs.active_tab.trim();
        // 配置管理视图（CONFIG_VIEW）不持久化：即使后端残留该值
        // 也判无效，刷新后保持正常主页面
        const valid = savedTab === 'all' || savedTab === IMAGE_BED_VIEW ||
          this.servers.some(s => s.server_name === savedTab);
        if (savedTab && valid && savedTab !== this.activeServerTab) {
          this.activateServerTab(savedTab, { persist: false });
        }
      }
    } catch (e) {
      console.warn('拉取面板偏好失败:', e);
    }
  }

  // 当前服务器视图对应的服务器对象；全局/图床/配置视图返回 null
  activeServerObject() {
    if (this.activeServerTab === 'all' || this.isImageBedView() || this.isConfigView()) return null;
    return this.servers.find(s => s.server_name === this.activeServerTab) || null;
  }

  // 单台服务器在线人数（与服务器卡片取数优先级一致）
  countServerOnline(server) {
    const players = server.players;
    const status = server.status;
    if (players && typeof players.online === 'number' && players.online > 0) {
      return players.online;
    }
    if (status && typeof status.online_players === 'number' && status.online_players > 0) {
      return status.online_players;
    }
    if (players && Array.isArray(players.names) && players.names.length > 0) {
      return players.names.length;
    }
    if (status && Array.isArray(status.online_player_names) && status.online_player_names.length > 0) {
      return status.online_player_names.length;
    }
    return 0;
  }

  formatDuration(seconds) {
    const total = Math.max(0, Math.floor(seconds || 0));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${total % 60}s`;
    return `${total}s`;
  }

  setStatCard(labelId, valueId, label, value) {
    const labelEl = document.getElementById(labelId);
    if (labelEl) labelEl.textContent = label;
    const valueEl = document.getElementById(valueId);
    if (valueEl) valueEl.textContent = value;
  }

  // 四个统计卡片跟随顶部服务器标签切换：全局汇总 or 单服务器指标
  renderOverview() {
    const server = this.activeServerObject();

    if (!server) {
      const totalServers = this.servers.length;
      const connectedServers = this.servers.filter(s => s.connected).length;
      const totalOnlinePlayers = this.servers.reduce(
        (sum, s) => sum + this.countServerOnline(s),
        0
      );
      const totalEvents = this.stats?.total_events ?? 0;
      const uptime = this.stats?.uptime_seconds ?? 0;
      const h = Math.floor(uptime / 3600);
      const m = Math.floor((uptime % 3600) / 60);

      this.setStatCard('stat-servers-label', 'stat-servers', '已连接 / 总服务器', `${connectedServers} / ${totalServers}`);
      this.setStatCard('stat-players-label', 'stat-players', '全服在线玩家', `${totalOnlinePlayers} 人`);
      this.setStatCard('stat-events-label', 'stat-events', '累计互通事件', `${totalEvents} 条`);
      this.setStatCard('stat-uptime-label', 'stat-uptime', '插件运行时间', `${h}h ${m}m`);
      // 重连状态：正在重试（断线且未达上限）/ 已放弃（达上限停止）
      const reconnecting = this.stats?.reconnecting_servers ?? 0;
      const exhausted = this.stats?.exhausted_servers ?? 0;
      const reconnectText = (reconnecting > 0 || exhausted > 0)
        ? `${reconnecting} 重试 / ${exhausted} 放弃`
        : '正常';
      this.setStatCard('stat-reconnect-label', 'stat-reconnect', '重连状态', reconnectText);
      return;
    }

    const connected = !!server.connected;
    const onlineCount = this.countServerOnline(server);
    const eventsTotal = server.events_total ?? 0;
    const connectedSeconds = server.connected_seconds ?? 0;

    this.setStatCard('stat-servers-label', 'stat-servers', '连接状态', connected ? '已连接' : '未连接');
    this.setStatCard('stat-players-label', 'stat-players', '本服在线玩家', `${onlineCount} 人`);
    this.setStatCard('stat-events-label', 'stat-events', '本服互通事件', `${eventsTotal} 条`);
    this.setStatCard(
      'stat-uptime-label',
      'stat-uptime',
      '本次连接时长',
      connected ? this.formatDuration(connectedSeconds) : '--'
    );
    // 本服重连状态：达上限停止 / 正在重试 / 正常
    const cst = server.client || null;
    const retryCount = cst?.retry_count ?? 0;
    const exhausted = !!cst?.reconnect_exhausted;
    const reconnectText = exhausted
      ? '已放弃重连'
      : (retryCount > 0 ? `重连 ${retryCount} 次` : '正常');
    this.setStatCard('stat-reconnect-label', 'stat-reconnect', '重连状态', reconnectText);
  }

  renderServers() {
    const container = document.getElementById('servers-container');
    if (!container) return;

    const titleEl = document.getElementById('servers-section-title');
    const activeServer = this.activeServerObject();
    if (titleEl) {
      const nameEl = titleEl.querySelector('span');
      if (nameEl) {
        nameEl.textContent = activeServer
          ? `🌐 服务器实例状态 · ${activeServer.server_label || activeServer.server_name}`
          : '🌐 服务器实例状态';
      }
    }

    // 单服务器视图只展示该服务器卡片；全局视图展示全部
    const list = activeServer ? [activeServer] : this.servers;
    let html = list.map(server => this.buildServerCardHtml(server)).join('');

    // 全局视图额外追加：配置里存在但未生效的条目（灰色卡片，可点开启用）。
    // 单服务器视图下不追加，避免切走当前实例的视野。
    // 新建入口只保留区块标题右上角的「＋ 新建服务器」按钮，网格内不再放虚线新建卡
    if (!activeServer) {
      const pending = this.pendingConfigServers();
      html += pending.map(item => this.buildDisabledServerCardHtml(item)).join('');
      if (!list.length && !pending.length) {
        html = `
        <div class="empty-box">
          <p>⚠️ 暂未配置任何 Minecraft 服务器</p>
          <p style="margin-top: 8px; font-size: 12px;">点右上角「＋ 新建服务器」即可在面板里直接添加，保存后自动热重载生效</p>
        </div>`;
      }
    }

    container.innerHTML = html;
    this.bindServerCardActions();
    this.bindServerManageActions();
    // 玩家进出/卡片高度变化后立即同步右侧监控面板高度（等一帧布局结算，
    // 避免 innerHTML 重建后读到旧高度）
    requestAnimationFrame(() => this.syncMonitorPanelHeight());
  }

  // 配置里存在、但运行时没有实例的条目：未启用（enabled=false）或启用了
  // 却没生效（server_name 为空 / 与其它条目重复，被 main 层跳过）。
  // 两类都必须显示出来，否则用户在面板上根本看不到它们
  pendingConfigServers() {
    const running = new Set(this.servers.map(s => s.server_name));
    return (this.configServers || []).filter(
      item => !item.enabled || !(item.running || running.has(item.server_name))
    );
  }

  buildDisabledServerCardHtml(item) {
    const modeText = item.ws_mode === 'reverse' ? '反向监听' : '正向连接';
    const endpoint = item.ws_mode === 'reverse'
      ? `${item.reverse_host || '0.0.0.0'}:${item.reverse_port || ''}${item.reverse_path || ''}`
      : (item.ws_url || '--');
    const label = item.label || item.server_name || `服务器 #${item.index + 1}`;
    const idTag = item.server_name
      ? `<span class="server-id-tag">(${escapeHtml(item.server_name)})</span>`
      : '<span class="server-id-tag">(未命名)</span>';
    const badge = item.enabled ? '未生效' : '未启用';
    const hint = item.enabled
      ? '已勾选启用但没有建立实例：服务器名可能为空或与其它条目重复'
      : '配置存在但未启用';
    const sessions = (item.target_sessions || []).length;

    return `
      <div class="server-card disabled" data-config-index="${item.index}"
        title="点击打开配置：启用 / 编辑 / 删除">
        <div class="server-card-header">
          <div class="server-title-group">
            <img class="server-favicon" src="${escapeHtml(this.defaultServerIcon)}" alt="">
            <div class="server-name-wrap">
              <div class="server-display-name">${escapeHtml(label)} ${idTag}</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                ${escapeHtml(modeText)} · ${escapeHtml(endpoint)}
              </div>
            </div>
          </div>
          <div class="badges-group">
            <div class="badges-row">
              <span class="badge badge-disabled">${badge}</span>
              <span class="badge badge-mode">${sessions} 个目标会话</span>
            </div>
          </div>
        </div>
        <div class="disabled-hint">${escapeHtml(hint)}</div>
        <div class="disabled-actions">
          <button class="btn btn-sm" data-server-action="edit" data-config-index="${item.index}">⚙ 配置</button>
          <button class="btn btn-primary btn-sm" data-server-action="${item.enabled ? 'disable' : 'enable'}"
            data-config-index="${item.index}">
            ${item.enabled ? '⏸ 停用' : '▶ 启用'}
          </button>
        </div>
      </div>`;
  }

  // 灰卡的事件绑定（与运行中卡片的 bindServerCardActions 分开，
  // 避免 innerHTML 重建后重复绑定到旧节点）
  bindServerManageActions() {
    document.querySelectorAll('#servers-container .server-card[data-config-index]')
      .forEach(card => {
        card.addEventListener('click', (e) => {
          if (e.target.closest('[data-server-action]')) return; // 按钮自行处理
          this.openServerForm('edit', parseInt(card.dataset.configIndex, 10));
        });
      });
    document.querySelectorAll('#servers-container [data-server-action]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const index = parseInt(btn.dataset.configIndex, 10);
        const action = btn.dataset.serverAction;
        if (action === 'edit') this.openServerForm('edit', index);
        else await this.setServerEnabled(index, action === 'enable');
      });
    });
  }

  // 启用 / 停用一台已配置的服务器：写回 conf → 热重载（断开旧连接重建）
  async setServerEnabled(index, enabled) {
    const item = (this.configServers || []).find(s => s.index === index);
    const label = item ? (item.label || item.server_name) : `#${index}`;
    try {
      const resp = await this.apiPost('config/server/update', { index, enabled });
      this.configServers = resp?.servers || this.configServers;
      this.showToast(
        enabled ? `已启用「${label}」，正在热重载连接…` : `已停用「${label}」`,
        'success'
      );
      await this.refreshAll(true);
    } catch (e) {
      this.showToast(`${enabled ? '启用' : '停用'}失败: ${e.message || '网络错误'}`, 'error');
    }
  }

  // ---- 服务器条目弹窗（新建 / 编辑 / 删除）----

  // 新建时的默认服务器名：取 conf 默认值 Server，已占用则递增到 Server2 / Server3 …
  nextServerName() {
    const used = new Set(
      (this.configServers || []).map(s => (s.server_name || '').trim()).filter(Boolean)
    );
    if (!used.has(DEFAULT_SERVER_NAME)) return DEFAULT_SERVER_NAME;
    let n = 2;
    while (used.has(DEFAULT_SERVER_NAME + n)) n++;
    return DEFAULT_SERVER_NAME + n;
  }

  openServerForm(mode, index = null) {
    const item = mode === 'edit'
      ? (this.configServers || []).find(s => s.index === index)
      : null;
    if (mode === 'edit' && !item) {
      this.showToast('该服务器条目已不存在，请刷新后重试', 'warn');
      return;
    }
    this.serverFormMode = mode;
    this.serverFormIndex = mode === 'edit' ? index : null;
    const set = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value ?? '';
    };
    const title = document.getElementById('sf-title');
    const sub = document.getElementById('sf-sub');
    const delBtn = document.getElementById('sf-delete');
    const tokenHint = document.getElementById('sf-token-hint');

    if (mode === 'edit') {
      if (title) title.textContent = `⚙ 服务器配置 · ${item.label || item.server_name || '#' + index}`;
      if (sub) {
        sub.textContent = '';
        sub.classList.add('hidden');
      }
      document.getElementById('sf-enabled').checked = !!item.enabled;
      set('sf-name', item.server_name);
      set('sf-display', item.display_name);
      set('sf-mode', item.ws_mode === 'reverse' ? 'reverse' : 'forward');
      set('sf-wsurl', item.ws_url);
      set('sf-rhost', item.reverse_host || '0.0.0.0');
      set('sf-rport', item.reverse_port || 8080);
      set('sf-rpath', item.reverse_path || '/minecraft/ws');
      set('sf-token', '');
      // 目标会话与功能设置面板共用 conf 条目顶层字段，天然同步
      set('sf-sessions', (item.target_sessions || []).join('\n'));
      if (tokenHint) {
        tokenHint.textContent = item.access_token_set
          ? '已设置（留空 = 保持原值；填入新值即覆盖）'
          : '与鹊桥端 access_token 一致；留空表示不修改';
      }
      delBtn?.classList.remove('hidden');
    } else {
      if (title) title.textContent = '＋ 新建服务器';
      if (sub) sub.textContent = '按 conf 模板补齐其余字段，保存后立即热重载生效';
      sub?.classList.remove('hidden');
      document.getElementById('sf-enabled').checked = true;
      set('sf-name', this.nextServerName());
      set('sf-display', '');
      set('sf-mode', 'forward');
      set('sf-wsurl', DEFAULT_WS_URL);
      set('sf-rhost', '0.0.0.0');
      set('sf-rport', 8080);
      set('sf-rpath', '/minecraft/ws');
      set('sf-token', '');
      set('sf-sessions', '');
      if (tokenHint) tokenHint.textContent = '与鹊桥端 access_token 一致；无鉴权留空即可';
      delBtn?.classList.add('hidden');
    }
    this.syncServerFormModeRows();
    document.getElementById('server-form-modal')?.classList.remove('hidden');
    // 名称已带默认值，聚焦并全选便于直接覆盖
    const nameEl = document.getElementById('sf-name');
    nameEl?.focus();
    nameEl?.select();
  }

  // 连接方式联动：forward 只填 WS 地址，reverse 只填监听地址/路径
  syncServerFormModeRows() {
    const reverse = document.getElementById('sf-mode')?.value === 'reverse';
    document.getElementById('sf-row-wsurl')?.classList.toggle('hidden', reverse);
    document.getElementById('sf-row-reverse')?.classList.toggle('hidden', !reverse);
    document.getElementById('sf-row-rpath')?.classList.toggle('hidden', !reverse);
  }

  closeServerForm() {
    document.getElementById('server-form-modal')?.classList.add('hidden');
    this.serverFormMode = null;
  }

  async submitServerForm() {
    const mode = this.serverFormMode;
    const nameEl = document.getElementById('sf-name');
    const name = (nameEl?.value || '').trim();
    if (!name) {
      this.showToast('请填写服务器名称', 'error');
      nameEl?.focus();
      return;
    }
    const reverse = document.getElementById('sf-mode')?.value === 'reverse';
    const payload = {
      display_name: (document.getElementById('sf-display')?.value || '').trim(),
      ws_mode: reverse ? 'reverse' : 'forward',
      enabled: !!document.getElementById('sf-enabled')?.checked,
      // 与功能设置面板共用同一 conf 字段，任一侧保存都写入同一目标会话
      target_sessions: (document.getElementById('sf-sessions')?.value || '')
        .split('\n').map(s => s.trim()).filter(Boolean),
    };
    if (reverse) {
      payload.reverse_host = (document.getElementById('sf-rhost')?.value || '').trim() || '0.0.0.0';
      payload.reverse_port = parseInt(document.getElementById('sf-rport')?.value, 10) || 8080;
      payload.reverse_path = (document.getElementById('sf-rpath')?.value || '').trim() || '/minecraft/ws';
    } else {
      payload.ws_url = (document.getElementById('sf-wsurl')?.value || '').trim();
    }
    // 留空 = 不修改（编辑态尤其重要：不能因为没填就把已有 token 清掉）
    const token = document.getElementById('sf-token')?.value || '';
    if (token) payload.access_token = token;

    const saveBtn = document.getElementById('sf-save');
    if (saveBtn) saveBtn.disabled = true;
    try {
      let resp;
      if (mode === 'edit') {
        const index = this.serverFormIndex;
        resp = await this.apiPost('config/server/update', {
          index,
          new_server_name: name,
          ...payload,
        });
        this.showToast(
          `已保存「${name}」${payload.enabled ? '（启用）' : '（停用）'}，热重载中…`,
          'success'
        );
      } else {
        resp = await this.apiPost('config/server/create', { server_name: name, ...payload });
        this.showToast(`已新建「${name}」，热重载中…`, 'success');
      }
      this.configServers = resp?.servers || this.configServers;
      this.closeServerForm();
      await this.refreshAll(true);
    } catch (e) {
      this.showToast(`保存失败: ${e.message || '网络错误'}`, 'error');
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  async deleteServerEntry() {
    const index = this.serverFormIndex;
    const item = (this.configServers || []).find(s => s.index === index);
    if (!item) {
      this.showToast('该服务器条目已不存在，请刷新后重试', 'warn');
      return;
    }
    const label = item.label || item.server_name || `#${index}`;
    const ok = await this.confirmDialog(
      '删除服务器条目',
      `将从插件配置中删除「${label}」，其连接与监控随之停止。`
        + `\n配置会先备份到 data/conf_backups/，可手动恢复。`,
      '确认删除'
    );
    if (!ok) return;
    try {
      const resp = await this.apiPost('config/server/delete', { index });
      this.configServers = resp?.servers || this.configServers;
      this.showToast(`已删除「${label}」`, 'success');
      this.closeServerForm();
      await this.refreshAll(true);
    } catch (e) {
      this.showToast(`删除失败: ${e.message || '网络错误'}`, 'error');
    }
  }

  buildServerCardHtml(server) {
    const status = server.status || null;
    const players = server.players || null;
    const isConnected = server.connected;

    // 服务器图标：仅当服务端返回合法的 data:image 图标时才使用（标准 SLP
    // favicon 即 base64 data URL）。鹊桥有时会回传需鉴权的代理 URL 或错误
    // JSON（如 {"status":"error","message":"未授权"}），这类无法作为 <img> 源，
    // 一律回退默认图标。
    const defaultIcon = this.defaultServerIcon || './default-server-icon.png';
    const faviconRaw = status && status.favicon;
    const faviconSrc = (typeof faviconRaw === 'string' && faviconRaw.startsWith('data:image/'))
      ? faviconRaw
      : defaultIcon;

    // 内存进度条（物理内存：同机部署后端已按宿主机 MemAvailable 口径修正，
    // 跨机部署清零不显示；此处仅在有数据时渲染，避免 "--" 占位误导）
    let memoryHtml = '';
    if (status && status.memory_total > 0) {
      const percent = Math.min(100, Math.max(0, status.memory_percentage || 0));
      let stateClass = 'normal';
      if (percent > 85) stateClass = 'danger';
      else if (percent > 65) stateClass = 'warning';

      memoryHtml = `
        <div class="progress-wrap">
          <div class="progress-header">
            <span class="detail-label">物理内存</span>
            <span class="detail-val">${status.memory_usage_text || '--'}</span>
          </div>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill ${stateClass}" style="width: ${percent}%;"></div>
          </div>
        </div>`;
    }

    // JVM 堆内存进度条（鹊桥 get_status 扩展字段；分母优先 max，缺失回落 total）
    let jvmMemoryHtml = '';
    const jvm = (status && status.jvm_memory) || null;
    if (jvm && jvm.total > 0) {
      const jvmDenom = jvm.max > 0 ? jvm.max : jvm.total;
      let jvmPercent = (typeof jvm.percentage === 'number' && jvm.percentage > 0)
        ? jvm.percentage
        : (jvmDenom > 0 ? (jvm.used / jvmDenom * 100) : 0);
      jvmPercent = Math.min(100, Math.max(0, jvmPercent));
      let jvmStateClass = 'normal';
      if (jvmPercent > 85) jvmStateClass = 'danger';
      else if (jvmPercent > 65) jvmStateClass = 'warning';
      const mbInt = (size) => `${Math.round(size / 1048576)}MB`;
      const jvmSegs = [`${mbInt(jvm.used)} 已用`];
      if (jvm.total > 0) jvmSegs.push(`${mbInt(jvm.total)} 已申请`);
      if (jvm.max > 0) jvmSegs.push(`${mbInt(jvm.max)} 上限`);
      const jvmText = `${jvmSegs.join(' / ')} (${jvmPercent.toFixed(1)}%)`;
      jvmMemoryHtml = `
        <div class="progress-wrap jvm-progress">
          <div class="progress-header">
            <span class="detail-label">JVM 堆</span>
            <span class="detail-val">${jvmText}</span>
          </div>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill ${jvmStateClass}" style="width: ${jvmPercent}%;"></div>
          </div>
        </div>`;
    }

    // 玩家名单与人数解析
    let playerNames = [];
    let onlineCount = 0;
    let maxCount = 0;
    let playerSourceText = '';

    if (players && players.source !== 'none') {
      if (Array.isArray(players.names) && players.names.length) {
        playerNames = players.names;
      } else if (status && Array.isArray(status.online_player_names) && status.online_player_names.length) {
        playerNames = status.online_player_names;
      }
      onlineCount = (typeof players.online === 'number' && players.online > 0)
        ? players.online
        : (playerNames.length || (status ? status.online_players : 0));
      maxCount = (typeof players.max === 'number' && players.max > 0)
        ? players.max
        : (status ? status.max_players : 0);

      if (players.source === 'rcon') {
        const ch = players.rcon_channel === 'queqiao' ? '鹊桥RCON' : (players.rcon_channel === 'direct' ? '直连RCON' : 'RCON');
        playerSourceText = `[${ch}]`;
      } else if (players.source === 'slp') {
        playerSourceText = '[在线查询]';
      } else if (players.source === 'event_cache') {
        playerSourceText = '[事件追踪]';
      } else if (players.source === 'count') {
        playerSourceText = '[仅人数]';
      }
    } else if (status) {
      playerNames = status.online_player_names || [];
      onlineCount = status.online_players || playerNames.length;
      maxCount = status.max_players || 0;
      playerSourceText = '[免RCON在线查询]';
    }

    const playersCountText = `${onlineCount} / ${maxCount}`;

    // 玩家胶囊列表
    let playersListHtml = '';
    if (playerNames.length > 0) {
      playersListHtml = playerNames.map(name => `
        <div class="player-tag" data-player="${escapeHtml(name)}" data-server="${escapeHtml(server.server_name)}" title="点击快捷操作">
          <img class="player-avatar" src="https://crafatar.com/avatars/${encodeURIComponent(name)}?size=24&default=MHF_Steve&overlay" alt="" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'18\\' height=\\'18\\' fill=\\'%2394a3b8\\' viewBox=\\'0 0 16 16\\'><path d=\\'M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm2-3a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm4 8c0 1-1 1-1 1H3s-1 0-1-1 1-4 6-4 6 3 6 4zm-1-.004c-.001-.246-.154-.986-.832-1.664C11.516 10.68 10.289 10 8 10c-2.29 0-3.516.68-4.168 1.332-.678.678-.83 1.418-.832 1.664h10z\\'/></svg>'">
          <span>${escapeHtml(name)}</span>
        </div>
      `).join('');
    } else if (onlineCount > 0) {
      playersListHtml = `
        <div class="no-players" style="color: var(--mc-yellow); font-style: normal; display: flex; align-items: center; gap: 6px;">
          <span>👥 当前在线 ${onlineCount} 人</span>
          <span style="color: var(--text-muted); font-size: 11px;">（服务端未广播具体玩家名单；开启 RCON 可获取完整玩家列表）</span>
        </div>`;
    } else {
      playersListHtml = `<span class="no-players">${isConnected ? '当前暂无玩家在线' : '服务器未连接'}</span>`;
    }

    // CPU 负载：系统负载（system_load）+ 进程负载（process_load）+ 负载均值
    // （load_average）。process_load/load_average 为 -1.0 或 null 表示鹊桥侧
    // 不可用，展示层过滤为「--」。
    let cpuHtml = '--';
    if (status && status.cpu_cores) {
      const loadParts = [];
      if (typeof status.system_load === 'number' && status.system_load >= 0) {
        loadParts.push(`系统 ${status.system_load.toFixed(2)}`);
      }
      if (typeof status.process_load === 'number' && status.process_load >= 0) {
        loadParts.push(`进程 ${status.process_load.toFixed(2)}`);
      }
      if (typeof status.load_average === 'number' && status.load_average >= 0) {
        loadParts.push(`平均 ${status.load_average.toFixed(2)}`);
      }
      cpuHtml = `${status.cpu_cores} 核${loadParts.length ? ` (${loadParts.join(' / ')})` : ''}`;
    }

    // SLP 探测健康徽章：available 为明确布尔时显示，未知（旧版鹊桥/未连接）不显示
    let slpBadgeHtml = '';
    if (status && typeof status.slp_available === 'boolean') {
      const slpOk = status.slp_available;
      const slpReason = status.slp_reason || status.slp_error || '';
      slpBadgeHtml = `
        <span class="badge ${slpOk ? 'badge-online' : 'badge-offline'}"
              title="${escapeHtml(slpOk ? 'SLP 探测正常' : `SLP 探测异常：${slpReason}`)}">
          SLP ${slpOk ? '正常' : '异常'}
        </span>`;
    }

    // 状态数据新鲜度（timestamp 为鹊桥状态时间戳，毫秒）：
    // 位于卡片右上角徽章行下方，右对齐，超 60 秒标黄
    let freshnessHtml = '';
    if (status && status.timestamp_seconds > 0) {
      const ageText = formatAgeText(status.timestamp_seconds);
      const stale = ageText.includes('分钟') || ageText.includes('小时');
      freshnessHtml = `
        <span class="status-freshness ${stale ? 'stale' : ''}">🕐 更新于 ${ageText || '--'}</span>`;
    }

    // MOTD 渲染：过滤鹊桥错误响应 JSON（如 {"status":"error","message":"未授权"}）
    let motdHtml = '';
    const motdRaw = (status && typeof status.description === 'string') ? status.description.trim() : '';
    if (motdRaw && !/^\{\s*"(status|code|message|error)"\s*:/.test(motdRaw)) {
      motdHtml = `<div class="server-motd">${renderMcText(motdRaw)}</div>`;
    }

    const wsModeText = server.is_reverse ? `反向 WS (:端口 ${server.reverse_port || '--'})` : '正向 WS';

    // RCON 通道徽章：具体连接了什么就显示什么（鹊桥 RCON 需真实执行确认，仅 WS 连接不算）
    const rconChannels = Array.isArray(server.rcon_channels) ? server.rcon_channels : [];
    const hasQueqiaoRcon = rconChannels.includes('queqiao');
    const hasDirectRcon = rconChannels.includes('direct') || server.rcon_connected;

    let rconBadgeText = '未连接 RCON';
    let rconBadgeClass = 'badge-offline';
    if (hasQueqiaoRcon && hasDirectRcon) {
      rconBadgeText = '鹊桥RCON · 直连RCON';
      rconBadgeClass = 'badge-rcon';
    } else if (hasQueqiaoRcon) {
      rconBadgeText = '鹊桥RCON';
      rconBadgeClass = 'badge-rcon';
    } else if (hasDirectRcon) {
      rconBadgeText = '直连RCON';
      rconBadgeClass = 'badge-rcon';
    }

    // 性能监控徽标行（仅启用监控的服务器显示；全局视图同样可见）
    const monitorRowHtml = this.buildMonitorBadgesHtml(server);

    // 连接层运行观测徽章：已达重连上限（红）/ 正在重试（黄，附次数与阶段）
    let reconnectBadgeHtml = '';
    const cst = server.client || null;
    if (cst) {
      if (cst.reconnect_exhausted) {
        reconnectBadgeHtml = `<span class="badge badge-danger" title="已达重连上限，停止重连">⛔ 已放弃重连</span>`;
      } else if (!isConnected && (cst.retry_count ?? 0) > 0) {
        const stageText = cst.reconnect_stage === '低频' ? '低频重试' : '退避重试';
        const reason = cst.last_disconnect_reason || '';
        const tip = `已尝试 ${cst.retry_count} 次（${stageText}）${reason ? `\n断开原因: ${reason}` : ''}`;
        reconnectBadgeHtml = `
          <span class="badge badge-warn" title="${escapeHtml(tip)}">
            🔁 重连 ${cst.retry_count} 次
          </span>`;
      }
    }

    // 运行中的服务器同样提供「配置 / 停用」入口：下标按 conf 条目反查，
    // 查不到（实例不由 conf 建立）时整行不渲染，避免出现点空的按钮
    const cfgIndex = (this.configServers || [])
      .find(s => s.server_name === server.server_name)?.index;
    const manageHtml = cfgIndex === undefined ? '' : `
        <div class="card-manage-actions">
          <button class="btn btn-sm" data-server-action="edit" data-config-index="${cfgIndex}"
            title="在面板里修改这台服务器的连接、Token 与目标会话">⚙ 配置</button>
          <button class="btn btn-sm" data-server-action="disable" data-config-index="${cfgIndex}"
            title="停用后立即断开连接，服务器转为灰色卡片保留，随时可再启用">⏸ 停用</button>
        </div>`;

    return `
      <div class="server-card ${isConnected ? 'connected' : 'disconnected'}" id="server-card-${escapeHtml(server.server_name)}">
        <div class="server-card-header">
          <div class="server-title-group">
            <img class="server-favicon" src="${escapeHtml(faviconSrc)}" alt="" onerror="this.onerror=null;this.src='${escapeHtml(defaultIcon)}';">
            <div class="server-name-wrap">
              <div class="server-display-name">
                ${escapeHtml(server.server_label || server.server_name)}
                <span class="server-id-tag">(${escapeHtml(server.server_name)})</span>
              </div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                ${wsModeText} · 目标会话: ${server.target_sessions_count} 个
              </div>
            </div>
          </div>
          <div class="badges-group">
            <div class="badges-row">
              <span class="badge ${isConnected ? 'badge-online' : 'badge-offline'}">
                <span class="pulse-dot"></span>
                ${isConnected ? '在线' : '未连接'}
              </span>
              <span class="badge badge-mode">${server.is_reverse ? '反向监听' : '正向连接'}</span>
              <span class="badge ${rconBadgeClass}">${rconBadgeText}</span>
              ${slpBadgeHtml}
              ${reconnectBadgeHtml}
            </div>
            ${freshnessHtml}
          </div>
        </div>

        ${motdHtml}

        <div class="details-grid">
          <div class="detail-item">
            <span class="detail-label">服务端核心 / 版本</span>
            <span class="detail-val">${status?.server_type || '--'} ${status?.server_version || ''}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">CPU 核心与负载</span>
            <span class="detail-val">${cpuHtml}</span>
          </div>
          <div class="detail-item" style="grid-column: span 2;">
            <span class="detail-label">内存占用</span>
            ${memoryHtml}
            ${jvmMemoryHtml}
          </div>
        </div>

        ${monitorRowHtml}

        <div class="players-box">
          <div class="players-header">
            <span>在线玩家 (${playersCountText})</span>
            <span class="players-source-tag">${playerSourceText}</span>
          </div>
          <div class="players-tags-list">
            ${playersListHtml}
          </div>
        </div>

        ${manageHtml}

      </div>
    `;
  }

  bindServerCardActions() {
    // 监控「图表」按钮：全局视图点击切到该服视图并展开监控面板
    document.querySelectorAll('.monitor-mini-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this.focusServer(btn.dataset.server);
      });
    });
    // 玩家标签点击：快捷私聊/踢出/OP 管理，结果统一显示在互通终端
    document.querySelectorAll('.player-tag').forEach(tag => {
      tag.addEventListener('click', async () => {
        const player = tag.dataset.player;
        const serverName = tag.dataset.server;
        const action = prompt(`对玩家 ${player} 执行快捷操作：\n1. kick (踢出)\n2. msg (私聊)\n3. op (设为OP)\n4. deop (取消OP)`, 'msg');
        if (!action) return;

        // 全局视图无终端，切到该服务器视图展示操作反馈
        this.focusServer(serverName);

        if (action === 'kick' || action === '1') {
          const reason = prompt(`踢出 ${player} 的原因：`, 'Kicked by admin') || 'Kicked by admin';
          try {
            await this.apiPost(`server/${encodeURIComponent(serverName)}/action`, { action: 'kick', player, reason });
            this.terminalLog('system', serverName, `已踢出 ${player}`);
            this.refreshAll(true);
          } catch (e) {
            this.terminalLog('error', serverName, `踢出 ${player} 失败: ${e.message}`);
          }
        } else if (action === 'msg' || action === '2') {
          const msg = prompt(`向 ${player} 发送私聊：`);
          if (!msg) return;
          try {
            await this.apiPost(`server/${encodeURIComponent(serverName)}/action`, { action: 'private_msg', player, message: msg });
            this.terminalLog('broadcast', serverName, `私聊 ${player}: ${msg}`);
          } catch (e) {
            this.terminalLog('error', serverName, `私聊发送失败: ${e.message}`);
          }
        } else if (action === 'op' || action === '3') {
          try {
            await this.apiPost(`server/${encodeURIComponent(serverName)}/action`, { action: 'op', player });
            this.terminalLog('system', serverName, `已设 ${player} 为 OP`);
          } catch (e) {
            this.terminalLog('error', serverName, `设置 OP 失败: ${e.message}`);
          }
        } else if (action === 'deop' || action === '4') {
          try {
            await this.apiPost(`server/${encodeURIComponent(serverName)}/action`, { action: 'deop', player });
            this.terminalLog('system', serverName, `已取消 ${player} 的 OP`);
          } catch (e) {
            this.terminalLog('error', serverName, `取消 OP 失败: ${e.message}`);
          }
        }
      });
    });
  }

  // ---- 服务器视图标签（全局 + 每台服务器）----

  // 当前是否图床视图（独立于服务器视图与全局视图）
  isImageBedView() {
    return this.activeServerTab === IMAGE_BED_VIEW;
  }

  // 当前是否配置管理视图（同图床，独立于服务器视图与全局视图）
  isConfigView() {
    return this.activeServerTab === CONFIG_VIEW;
  }

  // 重建顶部服务器标签栏：全局 + 每台服务器，保留当前激活视图
  renderServerTabs() {
    const tabsEl = document.getElementById('server-tabs');
    if (!tabsEl) return;
    tabsEl.innerHTML = '';

    tabsEl.appendChild(this.buildServerTab('all', '🌐 全部服务器', null));
    for (const s of this.servers) {
      tabsEl.appendChild(
        this.buildServerTab(s.server_name, s.server_label || s.server_name, !!s.connected)
      );
    }

    // 原激活视图已不存在（服务器被移除）则回退全局视图；图床/配置视图键独立放行
    const valid = this.activeServerTab === 'all' ||
      this.activeServerTab === IMAGE_BED_VIEW ||
      this.activeServerTab === CONFIG_VIEW ||
      this.servers.some(s => s.server_name === this.activeServerTab);
    if (!valid) this.activeServerTab = 'all';

    // 图床标签的提示点与激活态由外部维护（#tab-image-bed 不在本容器内，
    // innerHTML 重建不会波及它，因此只需同步高亮与红点提示）
    this.syncImageBedDot();

    // 仅同步高亮，实际渲染交由 refreshAll 统一执行；不加持久化写入，
    // 避免每轮自动刷新都向后端重复写当前值
    this.activateServerTab(this.activeServerTab, { render: false, persist: false });
  }

  buildServerTab(key, label, connected) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'server-tab';
    btn.dataset.view = key;
    btn.title = key === 'all' ? '查看全部服务器汇总' : `查看服务器: ${label}`;

    if (connected !== null) {
      const dot = document.createElement('span');
      dot.className = `server-tab-dot ${connected ? 'online' : 'offline'}`;
      btn.appendChild(dot);
    }
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener('click', () => this.activateServerTab(key));
    return btn;
  }

  // 切换视图（全局 / 服务器 / 图床 / 配置管理）：统计卡片、服务器面板、终端、
  // 图床面板与配置面板按视图显示/隐藏。图床/配置视图独立于服务器：隐藏
  // stats-grid 与 layout-main（服务器主体），显示对应面板并停止终端轮询
  activateServerTab(key, { render = true, persist = true } = {}) {
    const isImageBed = key === IMAGE_BED_VIEW;
    const isConfig = key === CONFIG_VIEW;
    this.activeServerTab = key;
    // 刷新页面后仍停留在当前打开的视图
    try {
      localStorage.setItem('queqiao_active_tab', key);
    } catch (e) {
      // AstrBot 插件页 iframe 沙箱无 allow-same-origin 时 localStorage
      // 不可用，此处仅失去首屏缓存，权威值由 persistActiveTab 走后端兜底
    }
    if (persist) this.persistActiveTab(key);
    // 图床标签在 #server-tabs 之外（不受内渲染重建），需一并高亮
    document.querySelectorAll('#server-tabs .server-tab, #tab-image-bed')
      .forEach(b => {
        b.classList.toggle('active', b.dataset.view === key);
      });

    if (isImageBed) {
      // 图床视图：隐藏统计卡与服务器主体，显示图床面板；停止所有服务器
      // 视图的轮询/监控动作（终端、实时采样），切回时由 render 重新拉起
      const stats = document.querySelector('.stats-grid');
      if (stats) stats.classList.add('hidden');
      const main = document.querySelector('.layout-main');
      if (main) main.classList.add('hidden');
      const cfgPanel = document.getElementById('config-view');
      if (cfgPanel) cfgPanel.classList.add('hidden');
      const panel = document.getElementById('image-bed-panel');
      if (panel) panel.classList.remove('hidden');
      this.stopTerminalPolling();
      this.stopRealtime();
      if (render) {
        // 首拉图床状态与条目（失败不阻断，面板内显示错误提示）
        this.loadImageBedStatus();
        this.loadImageBedEntries();
      }
      this.syncMonitorFreqFromBackend();
      return;
    }

    if (isConfig) {
      // 配置管理视图：与图床一致——隐藏统计卡、服务器主体与图床面板，
      // 显示配置面板；配置加载由 config-view.js 监听 queqiao:config-view-open 执行
      const stats = document.querySelector('.stats-grid');
      if (stats) stats.classList.add('hidden');
      const main = document.querySelector('.layout-main');
      if (main) main.classList.add('hidden');
      const ibPanel = document.getElementById('image-bed-panel');
      if (ibPanel) ibPanel.classList.add('hidden');
      const panel = document.getElementById('config-view');
      if (panel) panel.classList.remove('hidden');
      this.stopTerminalPolling();
      this.stopRealtime();
      if (render) {
        // 携带进入前的视图，config-view.js 据此只渲染对应部分的表单
        window.dispatchEvent(new CustomEvent('queqiao:config-view-open', {
          detail: { view: this._configReturnView },
        }));
      }
      return;
    }

    // 服务器/全局视图：恢复主体显示，隐藏图床面板与配置面板
    const panel = document.getElementById('image-bed-panel');
    if (panel) panel.classList.add('hidden');
    const cfgPanel = document.getElementById('config-view');
    if (cfgPanel) cfgPanel.classList.add('hidden');
    const stats = document.querySelector('.stats-grid');
    if (stats) stats.classList.remove('hidden');
    const main = document.querySelector('.layout-main');
    if (main) main.classList.remove('hidden');

    if (render) {
      this.renderOverview();
      this.renderServers();
      // 异步拉取后端历史日志；内部已捕获异常，无需等待
      this.renderTerminal();
      this.renderMonitorPanel();
      this.renderSettingsPanel();
    }
    // 自动刷新间隔/实时频率为每台服务器独立持久化的设置：切换视图后
    // 重读该服（或回落第一台）的后端值，顶部按钮与状态行实时跟随
    this.syncMonitorFreqFromBackend();
  }

  // 服务器视图持久化：localStorage 在 AstrBot 沙箱 iframe（无
  // allow-same-origin）下不可用，权威落在后端 panel_prefs.json。
  // 防抖 800ms 合并连续切换；值未变不发请求；写失败只记日志
  persistActiveTab(key) {
    if (this._persistTabTimer) {
      clearTimeout(this._persistTabTimer);
      this._persistTabTimer = null;
    }
    this._persistTabTimer = setTimeout(() => {
      this._persistTabTimer = null;
      if (this._lastPersistedTab === key) return;
      this._lastPersistedTab = key;
      this.apiPost('panel/prefs', { active_tab: key }).catch((e) => {
        console.warn('保存服务器视图偏好失败:', e);
      });
    }, 800);
  }

  // 全局视图下对某台服务器执行操作时，切到该服视图以展示终端反馈
  focusServer(serverName) {
    // 全局视图或图床视图下对某台服务器执行操作时，切到该服视图以展示终端
    // 反馈；图床视图与服务器视图互斥，进入服务器视图需先退出图床面板
    if (serverName && this.activeServerTab !== serverName &&
        (this.activeServerTab === 'all' || this.isImageBedView() || this.isConfigView())) {
      this.activateServerTab(serverName);
    }
  }

  // ---- 图床面板 ----

  // 图床视图进入时拉取运行态（总开关/超时/内置服务/条目生效视图）。
  // 失败不阻断：面板内显示错误提示，顶部标签的红点提示同步兜底
  async loadImageBedStatus() {
    try {
      const resp = await Promise.race([
        this.apiGet('image_bed/status'),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('图床状态请求超时')), 8000)
        ),
      ]);
      this.imageBedStatus = (resp && resp.data) ? resp.data : resp;
    } catch (e) {
      console.warn('拉取图床状态失败:', e);
      this.imageBedStatus = null;
    }
    this.renderImageBedList();
    this.syncImageBedDot();
  }

  // 拉取 conf 里的图床条目原始数据（表单编辑回显用）与根级开关/超时
  async loadImageBedEntries() {
    try {
      const resp = await Promise.race([
        this.apiGet('config/image_bed'),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('图床配置请求超时')), 8000)
        ),
      ]);
      const data = (resp && resp.data) ? resp.data : resp;
      this.imageBedEntries = (data && Array.isArray(data.items)) ? data.items : [];
      if (data && typeof data.enable_image_upload === 'boolean') {
        this.imageBedMasterEnabled = data.enable_image_upload;
      }
      if (data && Number.isFinite(data.image_upload_timeout)) {
        this.imageBedTimeout = data.image_upload_timeout;
      }
      const toggle = document.getElementById('ib-enabled');
      if (toggle && typeof this.imageBedMasterEnabled === 'boolean') {
        toggle.checked = this.imageBedMasterEnabled;
      }
      const timeoutEl = document.getElementById('ib-timeout');
      if (timeoutEl && Number.isFinite(this.imageBedTimeout)) {
        timeoutEl.value = this.imageBedTimeout;
      }
    } catch (e) {
      console.warn('拉取图床配置失败:', e);
    }
  }

  // 拉取图床模板清单（含各模板字段默认值），成功后重建模板下拉。
  // 失败不阻断：保留 imageBedTemplateKeys 兜底下拉；表单预填用 defaults 优先
  async loadImageBedTemplates() {
    try {
      const resp = await Promise.race([
        this.apiGet('image_bed/templates'),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('图床模板请求超时')), 8000)
        ),
      ]);
      const data = (resp && resp.data) ? resp.data : resp;
      if (data && typeof data === 'object') {
        this.imageBedTemplates = data;
        this.rebuildImageBedTemplateOptions();
      }
    } catch (e) {
      console.warn('拉取图床模板失败:', e);
    }
  }

  // 重建「模板选择」下拉：优先用后端模板清单（名称/说明来自 schema），
  // 未拉到后端数据时退回 imageBedTemplateKeys 硬编码集合
  rebuildImageBedTemplateOptions() {
    const tpl = document.getElementById('ibf-template');
    if (!tpl) return;
    const labels = {
      builtin_http: '内置图片HTTP服务',
      custom: '通用图床接口',
    };
    const entries = this.imageBedTemplates
      ? Object.entries(this.imageBedTemplates)
      : this.imageBedTemplateKeys.map((key) => [key, null]);
    tpl.innerHTML = '';
    for (const [key, meta] of entries) {
      const opt = document.createElement('option');
      opt.value = key;
      const label = meta && meta.name ? meta.name : (labels[key] || key);
      opt.textContent = label === key ? key : `${key} · ${label}`;
      tpl.appendChild(opt);
    }
  }

  // 渲染图床条目列表（运行态视图：生效状态 + 未生效原因 + 操作按钮）
  renderImageBedList() {
    const listEl = document.getElementById('ib-list');
    if (!listEl) return;
    const status = this.imageBedStatus;
    const statusEl = document.getElementById('ib-status');
    if (statusEl) {
      statusEl.textContent = status && status.status_text
        ? status.status_text
        : (status ? '图床数据异常' : '加载失败');
    }

    if (!status) {
      listEl.innerHTML = `<div class="ib-empty">图床状态加载失败，请确认后端已注入图床子系统</div>`;
      return;
    }
    const items = Array.isArray(status.items) ? status.items : [];
    if (items.length === 0) {
      listEl.innerHTML = `<div class="ib-empty">尚未配置任何图床条目 — 点击右上「＋ 新建条目」添加</div>`;
      return;
    }

    const builtinRunning = Array.isArray(status.builtin_running)
      ? status.builtin_running : [];
    const html = items.map((it) => {
      const kindLabel = it.kind === 'builtin' ? '内置HTTP' : '第三方图床';
      const stateCls = it.active ? 'ok' : 'warn';
      const stateTxt = it.active ? '已生效' : '未生效';
      const runningMark = it.kind === 'builtin' && it.template_key === 'builtin_http'
        ? this._builtinRunningMark(it, builtinRunning) : '';
      const reasonHtml = it.reason
        ? `<div class="ib-item-reason">⚠ ${escapeHtml(it.reason)}</div>` : '';
      const detailHtml = it.detail
        ? `<div class="ib-item-detail">${escapeHtml(it.detail)}</div>` : '';
      const toggleLabel = it.enabled ? '停用' : '启用';
      return `<div class="ib-item ${it.active ? 'active' : 'inactive'}">
        <div class="ib-item-head">
          <span class="ib-item-kind ${it.kind}">${kindLabel}</span>
          <span class="ib-item-name">${escapeHtml(it.name)}</span>
          ${runningMark}
          <span class="ib-item-state ${stateCls}">${stateTxt}</span>
        </div>
        ${detailHtml}
        ${reasonHtml}
        <div class="ib-item-actions">
          <button type="button" class="btn btn-sm" data-ib-action="test" data-index="${it.index}">🧪 测试</button>
          <button type="button" class="btn btn-sm" data-ib-action="edit" data-index="${it.index}">✏ 编辑</button>
          <button type="button" class="btn btn-sm" data-ib-action="toggle" data-index="${it.index}">${toggleLabel}</button>
          <button type="button" class="btn btn-sm btn-danger" data-ib-action="delete" data-index="${it.index}">🗑 删除</button>
        </div>
        <div class="ib-item-test-result hidden" data-test-result="${it.index}"></div>
      </div>`;
    }).join('');
    listEl.innerHTML = `<div class="ib-list-inner">${html}</div>`;
    this._restoreImageBedTestResults(); // 重绘后回填最近一次的单条目测试结果
  }

  // 内置HTTP条目：运行态徽标（运行中 / 已停止；仅当条目为内置且已启用时）
  _builtinRunningMark(item, builtinRunning) {
    if (!item.enabled) return '';
    const host = (item.detail || '').trim();
    if (!host) return '';
    const isRunning = (builtinRunning || []).some(
      b => b.running === true && b.base_url === host
    );
    return `<span class="ib-item-running ${isRunning ? 'on' : 'off'}">${isRunning ? '● 运行中' : '○ 已停止'}</span>`;
  }

  // 图床标签红点：内置服务全停或存在未生效条目时提示（不打断服务器标签）
  syncImageBedDot() {
    const tab = document.getElementById('tab-image-bed');
    if (!tab) return;
    const status = this.imageBedStatus;
    let needsAttention = false;
    if (status) {
      const items = Array.isArray(status.items) ? status.items : [];
      // 任一「已启用但未生效」条目 → 提示（配置不完整）
      needsAttention = items.some(it => it.enabled && !it.active);
      // 内置条目已启用但对应服务未运行 → 提示
      const builtinRunning = Array.isArray(status.builtin_running)
        ? status.builtin_running : [];
      needsAttention = needsAttention || items.some(it => {
        if (it.kind !== 'builtin' || !it.enabled || !it.detail) return false;
        return !(builtinRunning || []).some(b => b.running === true && b.base_url === it.detail);
      });
    }
    tab.classList.toggle('attention', needsAttention);
    tab.classList.toggle('active', this.isImageBedView());
  }

  // 打开图床条目弹窗：create（新条目） / edit（回显原始条目）
  openImageBedForm(mode, index) {
    this.imageBedFormMode = mode;
    this.imageBedFormIndex = (mode === 'edit') ? String(index) : null;
    const overlay = document.getElementById('image-bed-form-modal');
    const title = document.getElementById('ibf-title');
    const sub = document.getElementById('ibf-sub');
    const delBtn = document.getElementById('ibf-delete');
    if (title) title.textContent = mode === 'create' ? '新建图床条目' : '编辑图床条目';
    if (sub) sub.textContent = mode === 'create'
      ? '按 conf 模板补齐其余字段，保存后免重连生效'
      : '仅改动显式字段；未填的保持原值，保存后免重连生效';
    if (delBtn) delBtn.classList.toggle('hidden', mode !== 'edit');
    this.syncImageBedFormTemplate();
    if (mode === 'edit') {
      this.fillImageBedForm(index);
    } else {
      this.resetImageBedFormFields();
    }
    if (overlay) overlay.classList.remove('hidden');
  }

  // 编辑回显：从 conf 原始条目（带 __template_key）填充表单
  fillImageBedForm(index) {
    const entry = (this.imageBedEntries || []).find(e => String(e.index) === String(index));
    const raw = entry && entry.entry ? entry.entry : null;
    if (!raw) {
      this.showToast('未找到该图床条目（可能已被删除）', 'error');
      this.closeImageBedForm();
      return;
    }
    const templateKey = (raw.__template_key || entry.template_key || 'custom');
    const tpl = document.getElementById('ibf-template');
    if (tpl) {
      const exists = Array.from(tpl.options).some(o => o.value === templateKey);
      if (!exists) {
        const opt = document.createElement('option');
        opt.value = templateKey;
        opt.textContent = `${templateKey} · 已有条目`;
        tpl.appendChild(opt);
      }
      tpl.value = templateKey;
    }
    this.syncImageBedFormTemplate();
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.value = (val === undefined || val === null) ? '' : String(val);
    };
    setVal('ibf-enabled', raw.enabled);
    const enabledEl = document.getElementById('ibf-enabled');
    if (enabledEl && typeof raw.enabled === 'boolean') enabledEl.checked = raw.enabled;
    setVal('ibf-name', raw.name);
    setVal('ibf-host', raw.host);
    setVal('ibf-port', raw.port);
    setVal('ibf-base-url', raw.base_url);
    setVal('ibf-upload-url', raw.upload_url);
    setVal('ibf-token', raw.token);
    setVal('ibf-response', raw.response);
    setVal('ibf-file-field', raw.file_field);
    setVal('ibf-headers', this._fieldsToLines(raw.headers));
    setVal('ibf-form-fields', this._fieldsToLines(raw.form_fields));
  }

  // headers/form_fields 的「名字: 值」行文本 ↔ 字段存储格式互转
  _fieldsToLines(value) {
    if (!value) return '';
    const s = String(value).trim();
    if (s.startsWith('{')) return s; // JSON 对象原样展示
    const lines = [];
    for (const part of s.split('|')) {
      const p = part.trim();
      if (p) lines.push(p);
    }
    return lines.join('\n');
  }

  _linesToFields(value) {
    const s = String(value || '').trim();
    if (!s) return '';
    if (s.startsWith('{')) return s;
    return s.split('\n').map(l => l.trim()).filter(Boolean).join('|');
  }

  // 模板下拉变化：按模板显示/隐藏专属字段行，并回填各自默认值。
  // force=true（新建模式切换模板）→ 整体覆盖为新模板默认值，清掉上一个
  // 模板的残留（否则 name 等通用字段一直停在第一个模板的默认值上）；
  // force=false（编辑回显/打开新建）→ 仅填尚未填写的字段，不覆盖用户输入
  syncImageBedFormTemplate(force) {
    const tpl = document.getElementById('ibf-template');
    if (!tpl) return;
    const key = tpl.value || 'custom';
    const isBuiltin = key === 'builtin_http';
    // 模板显示名：与 rebuildImageBedTemplateOptions 的 labels 同源；
    // 用于模板默认 name 为空或模板清单未拉到时的兜底文本
    const templateDisplayNames = {
      builtin_http: '内置图片HTTP服务',
      custom: '通用图床接口',
    };
    const toggleRow = (id, show) => {
      const row = document.getElementById(id);
      if (row) row.classList.toggle('hidden', !show);
    };
    toggleRow('ibf-row-builtin-host', isBuiltin);
    toggleRow('ibf-row-builtin-url', isBuiltin);
    toggleRow('ibf-row-third-url', !isBuiltin);
    toggleRow('ibf-row-third-token', !isBuiltin);
    toggleRow('ibf-row-third-response', !isBuiltin);
    toggleRow('ibf-row-third-file', !isBuiltin);
    toggleRow('ibf-row-third-headers', !isBuiltin);
    toggleRow('ibf-row-third-forms', !isBuiltin);
    // 按模板 defaults 回填：与后端 _new_image_entry 生成的新条目默认值同源
    const template = this.imageBedTemplates ? this.imageBedTemplates[key] : null;
    if (template && template.defaults) {
      const d = template.defaults;
      const applyDefault = (elId, value) => {
        const el = document.getElementById(elId);
        if (!el) return;
        if (el.type === 'checkbox') {
          if (typeof value === 'boolean' && (force || !el.checked)) el.checked = value;
          return;
        }
        if (force || el.value === '') {
          el.value = (value === undefined || value === null) ? '' : String(value);
        }
      };
      // name 优先用模板默认名；模板默认名为空（如 custom）或缺失时，
      // 换成该模板的显示文本，而不是停在上一个模板（如内置图床）的名字上
      const nameValue = (d.name === undefined || d.name === null || d.name === '')
        ? (templateDisplayNames[key] || key)
        : String(d.name);
      applyDefault('ibf-name', nameValue);
      applyDefault('ibf-host', d.host);
      applyDefault('ibf-port', d.port);
      applyDefault('ibf-base-url', d.base_url);
      applyDefault('ibf-upload-url', d.upload_url);
      applyDefault('ibf-token', d.token);
      applyDefault('ibf-response', d.response);
      applyDefault('ibf-file-field', d.file_field);
      applyDefault('ibf-headers', this._fieldsToLines(d.headers));
      applyDefault('ibf-form-fields', this._fieldsToLines(d.form_fields));
      applyDefault('ibf-enabled', d.enabled);
    }
    // 兜底：模板清单未拉到（后端接口失败）或模板未给默认值的字段，补最小
    // 默认（force 时 applyDefault 已清空模板未给值的字段，兜底正好补齐）。
    // name 独立处理：清单缺失时也要换成对应模板文本，避免停在前一个模板上
    const nameEl = document.getElementById('ibf-name');
    if (nameEl && (force || !nameEl.value)) {
      nameEl.value = templateDisplayNames[key] || key;
    }
    const hostEl = document.getElementById('ibf-host');
    if (isBuiltin) {
      if (hostEl && !hostEl.value) hostEl.value = '0.0.0.0';
      const portEl = document.getElementById('ibf-port');
      if (portEl && !portEl.value) portEl.value = '8765';
      const respEl = document.getElementById('ibf-response');
      if (respEl && !respEl.value) respEl.value = 'text';
    } else {
      const respEl = document.getElementById('ibf-response');
      if (respEl && !respEl.value) respEl.value = 'text';
      const ffEl = document.getElementById('ibf-file-field');
      if (ffEl && !ffEl.value) ffEl.value = 'file';
    }
  }

  resetImageBedFormFields() {
    const tpl = document.getElementById('ibf-template');
    if (tpl) tpl.value = 'builtin_http';
    const enabledEl = document.getElementById('ibf-enabled');
    if (enabledEl) enabledEl.checked = true;
    const fields = ['ibf-name', 'ibf-host', 'ibf-port', 'ibf-base-url',
      'ibf-upload-url', 'ibf-token', 'ibf-response', 'ibf-file-field',
      'ibf-headers', 'ibf-form-fields'];
    fields.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    const respEl = document.getElementById('ibf-response');
    if (respEl) respEl.value = 'text';
    this.syncImageBedFormTemplate();
  }

  closeImageBedForm() {
    const overlay = document.getElementById('image-bed-form-modal');
    if (overlay) overlay.classList.add('hidden');
    this.imageBedFormMode = null;
    this.imageBedFormIndex = null;
  }

  // 收集弹窗表单字段（仅收集当前模板可见且非空字段）
  _collectImageBedForm() {
    const tpl = document.getElementById('ibf-template');
    const templateKey = tpl ? tpl.value : 'custom';
    const enabledEl = document.getElementById('ibf-enabled');
    const nameEl = document.getElementById('ibf-name');
    const payload = {
      template_key: templateKey,
      enabled: enabledEl ? enabledEl.checked : true,
      name: nameEl ? nameEl.value.trim() : '',
    };
    if (templateKey === 'builtin_http') {
      payload.host = (document.getElementById('ibf-host')?.value || '').trim();
      payload.port = (document.getElementById('ibf-port')?.value || '').trim();
      payload.base_url = (document.getElementById('ibf-base-url')?.value || '').trim();
    } else {
      payload.upload_url = (document.getElementById('ibf-upload-url')?.value || '').trim();
      payload.token = (document.getElementById('ibf-token')?.value || '').trim();
      payload.response = (document.getElementById('ibf-response')?.value || 'text').trim();
      payload.file_field = (document.getElementById('ibf-file-field')?.value || '').trim();
      payload.headers = this._linesToFields(document.getElementById('ibf-headers')?.value);
      payload.form_fields = this._linesToFields(document.getElementById('ibf-form-fields')?.value);
    }
    return payload;
  }

  // 保存（新建/更新）图床条目：局部生效免重连，成功后重拉面板数据
  async submitImageBedForm() {
    const payload = this._collectImageBedForm();
    const btn = document.getElementById('ibf-save');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '保存中...';
    }
    try {
      let endpoint = 'config/image_bed/create';
      if (this.imageBedFormMode === 'edit') {
        endpoint = 'config/image_bed/update';
        payload.index = this.imageBedFormIndex;
      }
      await this.apiPost(endpoint, payload);
      this.showToast('图床配置已保存并生效（未重连 MC）', 'success');
      this.closeImageBedForm();
      await this.loadImageBedStatus();
      await this.loadImageBedEntries();
    } catch (e) {
      this.showToast('保存失败: ' + (e.message || '网络错误'), 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '保存并生效';
      }
    }
  }

  // 删除条目：二次确认（受限 iframe 无 window.confirm）后删除并局部生效
  async deleteImageBedEntry(index) {
    const targetIndex = (index !== undefined && index !== null) ? String(index) : this.imageBedFormIndex;
    if (targetIndex === null || targetIndex === undefined) return;
    const entry = (this.imageBedEntries || []).find(e => String(e.index) === String(targetIndex));
    const label = entry && entry.entry && entry.entry.name
      ? entry.entry.name : `#${targetIndex}`;
    const ok = await this.confirmDialog(
      '🗑 删除图床条目',
      `确定删除图床条目「${label}」吗？\n` +
      '该操作会从 conf 中移除条目并立即生效（不可撤销）。',
      '删除'
    );
    if (!ok) return;
    try {
      await this.apiPost('config/image_bed/delete', { index: targetIndex });
      this.showToast('已删除图床条目', 'success');
      this.closeImageBedForm();
      // 删除条目后其余条目的 conf 下标全部前移 1：同步迁移单条目测试
      // 结果的键，否则重绘后因 index 错位其余图床的测试结果全部丢失
      this._shiftImageBedTestResults(targetIndex);
      await this.loadImageBedStatus();
      await this.loadImageBedEntries();
    } catch (e) {
      this.showToast('删除失败: ' + (e.message || '网络错误'), 'error');
    }
  }

  // 删除图床条目后迁移单条目测试结果键：被删下标的结果丢弃，
  // 其后各条目的测试结果键 -1 跟随条目（与后端 conf 下标前移一致）
  _shiftImageBedTestResults(targetIndex) {
    const removed = Number(targetIndex);
    if (!Number.isFinite(removed)) return;
    const shifted = {};
    for (const [idx, saved] of Object.entries(this.imageBedTestResults)) {
      const n = Number(idx);
      if (n === removed) continue; // 被删条目：其结果随条目一起消失
      shifted[String(n > removed ? n - 1 : n)] = saved;
    }
    this.imageBedTestResults = shifted;
  }

  // 列表内单条目启用/停用：仅显式改 enabled，免重连
  async toggleImageBedEntry(index) {
    const entry = (this.imageBedEntries || []).find(e => String(e.index) === String(index));
    if (!entry || !entry.entry) return;
    const next = !entry.entry.enabled;
    try {
      await this.apiPost('config/image_bed/update', { index, enabled: next });
      this.showToast(next ? '已启用该条目' : '已停用该条目', 'success');
      await this.loadImageBedStatus();
      await this.loadImageBedEntries();
    } catch (e) {
      this.showToast('操作失败: ' + (e.message || '网络错误'), 'error');
    }
  }

  // 根级总开关（enable_image_upload）：免重连局部生效
  async toggleImageBed(enabled) {
    const btn = document.getElementById('ib-enabled');
    if (btn) btn.disabled = true;
    try {
      await this.apiPost('image_bed/switch', { enable_image_upload: enabled });
      this.showToast(enabled ? '图片转存已开启' : '图片转存已关闭', 'success');
      await this.loadImageBedStatus();
      await this.loadImageBedEntries();
    } catch (e) {
      this.showToast('保存失败: ' + (e.message || '网络错误'), 'error');
      if (btn && typeof this.imageBedMasterEnabled === 'boolean') {
        btn.checked = this.imageBedMasterEnabled;
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // 上传超时（image_upload_timeout）：免重连局部生效
  async saveImageBedTimeout() {
    const input = document.getElementById('ib-timeout');
    if (!input) return;
    const raw = parseInt(input.value, 10);
    const timeout = Number.isFinite(raw) && raw >= 1 ? raw : 30;
    if (!Number.isFinite(raw) || raw < 1) {
      this.showToast('超时需为 ≥1 的整数，已回落默认值 30', 'error');
      input.value = timeout;
    }
    try {
      await this.apiPost('image_bed/switch', { image_upload_timeout: timeout });
      this.showToast(`上传超时已设为 ${timeout} 秒`, 'success');
    } catch (e) {
      this.showToast('保存失败: ' + (e.message || '网络错误'), 'error');
    }
  }

  // 测试上传：逐条串行跑上传链，测完一条立即回填到该条目的结果容器
  async testImageBed() {
    if (this.imageBedTesting) return;
    this.imageBedTesting = true;
    const btn = document.getElementById('ib-test');
    const result = document.getElementById('ib-test-result');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '测试中...';
    }
    if (result) {
      result.classList.remove('hidden');
      result.className = 'ib-test-result pending';
      result.innerHTML = '<span class="ib-test-pending">⏳ 正在测试...</span>';
    }
    // 条目清单：优先用已加载的运行态 items，必要时现拉一次
    let items = Array.isArray(this.imageBedStatus && this.imageBedStatus.items)
      ? this.imageBedStatus.items : [];
    if (items.length === 0) {
      try {
        await this.loadImageBedStatus();
        items = Array.isArray(this.imageBedStatus && this.imageBedStatus.items)
          ? this.imageBedStatus.items : [];
      } catch (e) {
        console.warn('测试前拉取图床状态失败:', e);
      }
    }
    let okCount = 0;
    let failCount = 0;
    try {
      const total = items.length;
      for (let i = 0; i < total; i++) {
        const it = items[i];
        if (typeof it.index !== 'number') continue;
        const idx = Number(it.index);
        const entryName = String(it.name || '未命名条目');
        if (result) {
          result.innerHTML = `<span class="ib-test-pending">⏳ 正在测试 ${i + 1}/${total}...</span>`;
        }
        // 单条目串行：每测完一条立刻展示到该条目自己的结果容器
        const resp = await this.apiPost('image_bed/test', { index: idx });
        const data = (resp && resp.data) ? resp.data : resp;
        this._applyItemTestResult(idx, data, entryName);
        if (data && data.ok) okCount += 1;
        else failCount += 1;
      }
      if (result) {
        result.className = okCount > 0 ? 'ib-test-result ok' : 'ib-test-result fail';
        result.innerHTML = okCount > 0
          ? `✅ ${okCount} 个可用${failCount > 0 ? `，${failCount} 个不可用` : ''}`
          : `❌ 全部不可用（${failCount} 个）`;
      }
    } catch (e) {
      if (result) {
        result.className = 'ib-test-result fail';
        result.innerHTML = `<div class="ib-test-fail">✗ 测试请求失败: ${escapeHtml(e.message || '网络错误')}</div>`;
      }
    } finally {
      this.imageBedTesting = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🧪 测试上传';
      }
    }
  }

  // 逐条结果表格：每条目一行，展示 名称 / 状态 / 耗时 / URL 或原因
  _renderTestRows(data) {
    const results = Array.isArray(data && data.results) ? data.results : null;
    if (!results || results.length === 0) return '';
    const rows = results.map(r => {
      const ok = r.ok === true;
      const active = r.active !== false;
      const status = ok ? '✅ 可用'
        : (active ? '❌ 不可用' : '⚠ 未生效');
      const statusCls = ok ? 'row-ok'
        : (active ? 'row-fail' : 'row-warn');
      const elapsed = (typeof r.elapsed_ms === 'number' && r.elapsed_ms >= 0)
        ? `${(r.elapsed_ms / 1000).toFixed(2)}s` : '—';
      const detail = ok
        ? `<a href="${escapeHtml(r.url || '')}" target="_blank" rel="noopener">${escapeHtml(r.url || '')}</a>`
        : (r.reason ? escapeHtml(r.reason) : '无详细原因');
      return `<div class="ib-test-row">
        <span class="ib-test-row-name">${escapeHtml(r.name || '未命名条目')}</span>
        <span class="ib-test-row-status ${statusCls}">${status}</span>
        <span class="ib-test-row-time">${elapsed}</span>
        <span class="ib-test-row-detail">${detail}</span>
      </div>`;
    }).join('');
    return `<div class="ib-test-rows">${rows}</div>`;
  }

  // 单条目测试：结果临时展示在对应条目的 ib-item-test-result 容器里
  async testImageBedEntry(index) {
    const box = document.querySelector(`.ib-item-test-result[data-test-result="${index}"]`);
    const item = box ? box.closest('.ib-item') : null;
    const btn = item ? item.querySelector(`button[data-ib-action="test"][data-index="${index}"]`) : null;
    if (!box) return;
    const entryName = item && item.querySelector('.ib-item-name')
      ? item.querySelector('.ib-item-name').textContent.trim() : '';
    this.imageBedTesting = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = '测试中...';
    }
    box.classList.remove('hidden');
    box.className = 'ib-item-test-result pending';
    box.innerHTML = '<span class="ib-test-pending">⏳ 正在测试该条目...</span>';
    try {
      const resp = await this.apiPost('image_bed/test', { index: Number(index) });
      const data = (resp && resp.data) ? resp.data : resp;
      this._applyItemTestResult(index, data, entryName);
    } catch (e) {
      box.className = 'ib-item-test-result fail';
      box.innerHTML = `<div class="ib-test-fail">✗ 测试请求失败: ${escapeHtml(e.message || '网络错误')}</div>`;
      // 失败状态同样保存：自动刷新重绘后回填
      this.imageBedTestResults[String(index)] = {
        cls: box.className, html: box.innerHTML, name: entryName,
      };
    } finally {
      this.imageBedTesting = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🧪 测试';
      }
    }
  }

  // 把一次测试响应渲染进该条目的结果容器并保存（单条目与全量测试共用；
  // 全量测试逐条回填到各自条目，自动刷新重绘后同样能恢复）
  _applyItemTestResult(index, data, entryName) {
    const box = document.querySelector(`.ib-item-test-result[data-test-result="${index}"]`);
    if (!box) return;
    box.classList.remove('hidden');
    const rows = this._renderTestRows(data);
    if (data && data.ok) {
      box.className = 'ib-item-test-result ok';
      box.innerHTML = `✅ 可用${data.url
        ? `：<a href="${escapeHtml(data.url)}" target="_blank" rel="noopener">${escapeHtml(data.url)}</a>` : ''}${rows}`;
    } else {
      box.className = 'ib-item-test-result fail';
      box.innerHTML = `❌ 不可用${rows}`;
    }
    // 存最近一次测试结果：自动刷新重绘条目列表后回填，避免结果一闪而过
    this.imageBedTestResults[String(index)] = {
      cls: box.className, html: box.innerHTML, name: entryName,
    };
  }

  // 全量测试结果逐条回填到各条目自己的结果容器：与单条目测试同一套
  // 渲染/保存逻辑，仅按条目名匹配定位（条目名可直接防 index 错位）
  _applyFullImageBedTestResults(data) {
    const results = Array.isArray(data && data.results) ? data.results : [];
    if (results.length === 0) return;
    const boxes = document.querySelectorAll('.ib-item-test-result');
    boxes.forEach((box) => {
      const item = box.closest('.ib-item');
      const entryName = item && item.querySelector('.ib-item-name')
        ? item.querySelector('.ib-item-name').textContent.trim() : '';
      if (!entryName) return;
      const hit = results.find(r => (r.name || '') === entryName);
      if (!hit) return;
      this._applyItemTestResult(
        box.getAttribute('data-test-result'),
        { ok: hit.ok === true, url: hit.url || '', results: [hit] },
        entryName,
      );
    });
  }

  // 自动刷新重绘后回填最近一次的单条目测试结果（条目名匹配防错位）
  _restoreImageBedTestResults() {
    for (const [index, saved] of Object.entries(this.imageBedTestResults)) {
      const box = document.querySelector(`.ib-item-test-result[data-test-result="${index}"]`);
      if (!box) continue;
      const item = box.closest('.ib-item');
      const entryName = item && item.querySelector('.ib-item-name')
        ? item.querySelector('.ib-item-name').textContent.trim() : '';
      if (saved.name && entryName !== saved.name) continue; // index 已错位则跳过
      box.className = saved.cls;
      box.innerHTML = saved.html;
    }
  }

  // 图床面板其余动作绑定（模板下拉按后端 schema 键集合重建，避免硬编码漂移）
  bindImageBedActions() {
    // 先按兜底键集合渲染，再异步拉取后端模板清单重建（成功后名称/默认值
    // 全部来自 schema，与后端 _new_image_entry 生成的新条目默认值一致）
    this.rebuildImageBedTemplateOptions();
    this.loadImageBedTemplates();
    // 进入图床视图时若数据尚未拉取，立即补拉（activateServerTab 的 render
    // 分支只负责首拉；此处兜底标签直接点击的场景）
    this.syncImageBedDot();
  }

  // ---- 互通终端 ----

  // 当前终端目标服务器：全局/图床/配置视图返回 null（终端整体隐藏）
  terminalServer() {
    return (this.activeServerTab === 'all' || this.isImageBedView() || this.isConfigView())
      ? null : this.activeServerTab;
  }

  // server_name → 显示名称（便于终端日志可读）
  terminalServerLabel(name) {
    const s = this.servers.find(item => item.server_name === name);
    return s ? (s.server_label || s.server_name) : name;
  }

  // 渲染互通终端：全局/图床视图整体隐藏；服务器视图显示该服务器的日志流。
  // 每次进入都做增量拉取并启动 4 秒轮询，新日志自动追加、实时可见
  async renderTerminal() {
    const panel = document.getElementById('terminal-panel');
    const key = this.activeServerTab;
    const isServerView = !!key && key !== 'all' && !this.isImageBedView() && !this.isConfigView();

    if (panel) panel.classList.toggle('hidden', !isServerView);
    // 输入区可用性始终同步（非服务器视图无目标服务器，禁用输入）
    this.updateTerminalInputState();
    if (!isServerView) {
      this.stopTerminalPolling();
      return;
    }

    // 轮询只跟随当前视图服务器；切换视图时旧轮询自动停止
    this.startTerminalPolling(key);

    const server = this.activeServerObject();
    const titleEl = document.getElementById('terminal-title');
    if (titleEl) {
      const label = server ? (server.server_label || server.server_name) : key;
      titleEl.textContent = `🖥️ 互通终端 · ${label}`;
    }

    const stream = this.ensureTerminalStream(key);
    document.querySelectorAll('.terminal-stream').forEach(s => {
      s.classList.toggle('active', s.id === `terminal-stream-${key}`);
    });
    // 增量拉取历史日志（网页未打开期间的事件也已记录）
    await this.loadTerminalLogs(key, stream);
    // 无任何历史时给出操作提示（提示行本身计入流，后续轮询不会重复打出）
    if (stream.children.length === 0) {
      this.terminalLog('system', key, '互通终端就绪 — 输入内容回车=广播，以 / 开头回车=执行指令');
    }
    this.updateTerminalInputState();
  }

  // 互通终端轮询：固定 4 秒增量拉取（只读本地持久化日志，不打扰鹊桥）
  startTerminalPolling(key) {
    if (this.terminalPollTimer) {
      clearInterval(this.terminalPollTimer);
      this.terminalPollTimer = null;
    }
    this.terminalPollTimer = setInterval(() => {
      const current = this.activeServerTab;
      if (!current || current === 'all' || current !== key) {
        this.stopTerminalPolling();
        return;
      }
      this.loadTerminalLogs(key, this.ensureTerminalStream(key));
    }, 4000);
  }

  stopTerminalPolling() {
    if (this.terminalPollTimer) {
      clearInterval(this.terminalPollTimer);
      this.terminalPollTimer = null;
    }
  }

  // 互通终端加载天数：按当前服务器 conf（条目顶层 terminal_days）取值，
  // 钳制 0~30；conf 未就绪或缺省时回落 2（今天+昨天）
  terminalDaysFor(key) {
    const conf = (this.configServers || []).find((s) => s.server_name === key);
    const raw = conf && Number.isFinite(conf.terminal_days) ? conf.terminal_days : 2;
    return Math.max(0, Math.min(30, raw));
  }

  // 从后端拉取某台服务器的持久化日志，只追加尚未渲染的新条目。
  // 请求带 5 秒超时保护：桥通道异常时降级跳过本次拉取，避免拖死整页刷新
  async loadTerminalLogs(key, stream) {
    try {
      const res = await Promise.race([
        this.apiGet('terminal_logs', { server: key, days: this.terminalDaysFor(key) }),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('terminal_logs 请求超时')), 5000)
        ),
      ]);
      // 拉取期间用户已切换视图，丢弃过期结果
      if (this.activeServerTab !== key) return;
      const logs = res?.logs || [];
      let rendered = parseInt(stream.dataset.rendered || '0', 10);
      // 后端被清屏（条目数回退）时重置渲染游标，避免新日志无法再追加
      if (logs.length < rendered) {
        stream.innerHTML = '';
        stream.dataset.lastDate = '';
        rendered = 0;
      }
      for (let i = rendered; i < logs.length; i++) {
        const entry = logs[i];
        this.appendTerminalLine(
          stream,
          entry.type || 'system',
          key,
          entry.message || '',
          entry.time || '--:--:--'
        );
      }
      stream.dataset.rendered = String(logs.length);
    } catch (e) {
      console.warn('拉取终端日志失败:', e);
    }
    // 追加完成后补滚一次（字体/布局稳定后 scrollHeight 才准确）
    this.ensureTerminalScrolled();
  }

  // 获取（不存在则创建）某服务器对应的日志流容器
  ensureTerminalStream(key) {
    const body = document.getElementById('terminal-body');
    let stream = document.getElementById(`terminal-stream-${key}`);
    if (!stream) {
      stream = document.createElement('div');
      stream.id = `terminal-stream-${key}`;
      stream.className = 'terminal-stream';
      // 创建时若恰为当前视图的服务器，立即显示（否则日志会隐形）
      if (key === this.activeServerTab) {
        stream.classList.add('active');
      }
      body.appendChild(stream);
    }
    return stream;
  }

  // 终端仅在单服务器视图可用；全局/图床/配置视图隐藏面板并禁用输入
  updateTerminalInputState() {
    const isServerView = !!this.activeServerTab &&
      this.activeServerTab !== 'all' && !this.isImageBedView() && !this.isConfigView();
    const locked = !isServerView;
    const input = document.getElementById('terminal-input');
    const bBtn = document.getElementById('terminal-broadcast');
    const cBtn = document.getElementById('terminal-cmd');
    if (input) {
      input.disabled = locked;
      input.placeholder = '输入内容回车 = 广播；以 / 开头回车 = 执行指令 (如 /list)';
    }
    if (bBtn) bBtn.disabled = locked;
    if (cBtn) cBtn.disabled = locked;
  }

  // 向指定日志流追加一行（纯 DOM 操作）；跨天时先插入日期分割线，
  // 自动滚动开启时滚到底部
  appendTerminalLine(stream, type, key, message, time) {
    // 日期分割线：time 形如 "MM-DD HH:MM:SS"，取前 5 位作为分片日期；
    // 与上一行日期不同（含首行）时插入「── MM-DD ──」
    const datePart = (time || '').slice(0, 5);
    const lastDate = stream.dataset.lastDate || '';
    if (datePart && datePart !== lastDate) {
      const divider = document.createElement('div');
      divider.className = 'terminal-date-divider';
      divider.textContent = `── ${datePart} ──`;
      stream.appendChild(divider);
      stream.dataset.lastDate = datePart;
    }
    const tagMap = {
      broadcast: '📢', cmd: '⚡', out: '↳', error: '✖', system: 'ℹ',
      chat: '💬', qq_chat: '📲', join: '🟢', quit: '🔴', death: '💀',
      achievement: '🏆', command: '⌨', conn: '🔁',
    };
    const line = document.createElement('div');
    line.className = `terminal-line terminal-${type}`;
    // 单行流式：时间不折行，图标/[服务器]/消息紧凑排列，消息过长自动换行
    line.innerHTML =
      `<span class="terminal-time">${escapeHtml(time)}</span>` +
      `<span class="terminal-tag">${tagMap[type] || '•'}</span>` +
      `<span class="terminal-server">[${escapeHtml(this.terminalServerLabel(key))}]</span>` +
      `<span class="terminal-msg">${escapeHtml(message)}</span>`;
    stream.appendChild(line);
    this.scrollTerminalToBottom();
  }

  // 终端滚动容器是 .terminal-body；自动滚动开启时滚到底部
  scrollTerminalToBottom() {
    if (!this.terminalAutoscroll) return;
    const body = document.getElementById('terminal-body');
    if (body) body.scrollTop = body.scrollHeight;
  }

  // 确保首屏滚到真正的底部：append 循环里的同步滚动发生在等宽字体加
  // 载/布局稳定之前，行高变化后 scrollHeight 会增长，需在稳定后再补滚。
  // 双 rAF 等首帧布局，document.fonts.ready 等字体加载完成。
  ensureTerminalScrolled() {
    if (!this.terminalAutoscroll) return;
    const scroll = () => this.scrollTerminalToBottom();
    requestAnimationFrame(() => requestAnimationFrame(scroll));
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(scroll);
    }
  }

  // 更新自动滚动按钮的 UI 状态
  syncAutoscrollButton() {
    const btn = document.getElementById('terminal-autoscroll');
    if (!btn) return;
    btn.classList.toggle('active', this.terminalAutoscroll);
    if (this.terminalAutoscroll) {
      btn.title = '新消息自动滚动到底部；点击暂停';
      btn.textContent = '📌 自动滚动';
    } else {
      btn.title = '已暂停自动滚动；点击恢复';
      btn.textContent = '📌 已暂停';
    }
  }

  // 向对应服务器的日志流追加一行（即时反馈；持久化由后端负责）
  terminalLog(type, serverName, message) {
    const key = serverName || this.activeServerTab;
    if (!key || key === 'all') return;
    const stream = this.ensureTerminalStream(key);
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    // 与后端持久化日志的时间格式保持一致（含日期）
    const time = `${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
      `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    this.appendTerminalLine(stream, type, key, message, time);
  }

  async sendBroadcast() {
    const input = document.getElementById('terminal-input');
    const message = input?.value.trim();
    if (!message) {
      this.showToast('请输入广播内容', 'error');
      return;
    }
    const server = this.terminalServer();
    if (!server) {
      this.showToast('请先选择目标服务器', 'error');
      return;
    }
    const color = document.getElementById('terminal-color')?.value || 'white';
    const btn = document.getElementById('terminal-broadcast');
    if (btn) btn.disabled = true;
    try {
      await this.apiPost(`server/${encodeURIComponent(server)}/broadcast`, { message, color });
      this.terminalLog('broadcast', server, message);
      if (input) input.value = '';
    } catch (e) {
      this.terminalLog('error', server, `广播失败: ${e.message}`);
      this.showToast('广播失败: ' + e.message, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async runCommand() {
    const input = document.getElementById('terminal-input');
    const command = input?.value.trim();
    if (!command) {
      this.showToast('请输入指令内容', 'error');
      return;
    }
    const server = this.terminalServer();
    if (!server) {
      this.showToast('请先选择目标服务器', 'error');
      return;
    }
    const btn = document.getElementById('terminal-cmd');
    this.terminalLog('cmd', server, command);
    if (btn) btn.disabled = true;
    try {
      const res = await this.apiPost(`server/${encodeURIComponent(server)}/command`, { command });
      this.terminalLog('out', server, `[${res.channel || 'cmd'}] ${res.output || '(无回显)'}`);
      if (input) input.value = '';
    } catch (e) {
      this.terminalLog('error', server, `指令执行失败: ${e.message}`);
      this.showToast('指令执行失败: ' + e.message, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ---- 性能监控面板（TPS / 延迟） ----

  // 服务器卡片上的监控摘要行：仅启用监控的服务器渲染；最新值来自
  // get_servers 返回的 server.monitor.latest，跟随 10s 自动刷新
  buildMonitorBadgesHtml(server) {
    const m = server.monitor || {};
    if (!m.enabled) return '';
    const latest = m.latest || null;

    let tpsHtml, latHtml, metaHtml, detailBtn;
    if (latest) {
      const tps1 = (typeof latest.tps1 === 'number') ? latest.tps1 : null;
      const lat = (typeof latest.latency_ms === 'number') ? latest.latency_ms : null;
      tpsHtml = tps1 != null
        ? `<span class="monitor-mini-badge ${this.tpsValueClass(tps1)}">⚡ TPS ${tps1.toFixed(1)}</span>`
        : '<span class="monitor-mini-badge">⚡ TPS 不可用</span>';
      latHtml = lat != null
        ? `<span class="monitor-mini-badge">📡 延迟 ${Math.round(lat)}ms</span>`
        : '<span class="monitor-mini-badge">📡 延迟 --</span>';
      metaHtml = `<span class="monitor-mini-meta">${m.sample_count ?? 0} 采样 · ${this.formatClock(latest.ts)}</span>`;
    } else {
      tpsHtml = '<span class="monitor-mini-badge">⚡ 采集中…</span>';
      // 无采样数据（未连接/首次等待）时延迟徽章同样占位，保持摘要行结构稳定
      latHtml = '<span class="monitor-mini-badge">📡 延迟 --</span>';
      metaHtml = m.last_error
        ? `<span class="monitor-mini-meta monitor-warning">⚠ ${escapeHtml(m.last_error)}</span>`
        : '<span class="monitor-mini-meta">等待首次采样…</span>';
    }
    detailBtn = `<button class="monitor-mini-btn" data-server="${escapeHtml(server.server_name)}" title="查看趋势图与统计摘要">图表</button>`;

    return `
      <div class="monitor-mini-row">
        <span class="monitor-mini-title">📈 性能监控</span>
        ${tpsHtml}${latHtml}
        <span class="monitor-mini-spacer"></span>
        ${metaHtml}
        ${detailBtn}
      </div>`;
  }

  renderMonitorPanel() {
    const panel = document.getElementById('monitor-panel');
    const server = this.activeServerObject();
    // 面板可见性只跟随视图（全局/图床视图隐藏）；监控禁用不隐藏面板——
    // 否则面板内的「⚙ 设置」入口一并消失，无法再重新启用
    const isAll = this.activeServerTab === 'all' || this.isImageBedView() || this.isConfigView();
    if (panel) panel.classList.toggle('hidden', isAll);
    // 全局视图下主布局退化为单列全宽，服务器卡片不再被挤在左半列
    const layoutMain = document.querySelector('.layout-main');
    if (layoutMain) layoutMain.classList.toggle('monitor-hidden', isAll);
    if (!server || isAll) {
      // 全局视图：无目标服务器，实时模式一并停止
      this._defaultTabServer = null;
      this.stopRealtime();
      return;
    }

    const enabled = !!(server.monitor && server.monitor.enabled);
    // 监控停用：面板与图表**完整保留**（继续渲染历史数据），仅状态行提示
    if (!enabled) {
      this._defaultTabServer = null;
      this.stopRealtime();
      const statusLine = document.getElementById('monitor-status-line');
      if (statusLine) {
        statusLine.innerHTML =
          '<span class="monitor-dot off"></span> 监控已停用 —— ' +
          '点击右上角「⚙ 设置」可重新启用';
      }
    }

    // 默认展示项来自后端设置（default_tab）：切换服务器时套用该服默认子页面
    if (this._defaultTabServer !== server.server_name) {
      const defTab = (server.monitor && server.monitor.default_tab) || 'tps';
      this.monitorTab = defTab === 'latency' ? 'latency' : 'tps';
      this._defaultTabServer = server.server_name;
    }

    // 打开页面时按「默认展示项」恢复子页面（HTML 初始为 TPS）
    this.setMonitorTab(this.monitorTab);

    if (this.realtimeActive) this._renderRealtimeStatus(server);
    else if (enabled) this.updateMonitorStatusLine(server);
    // 监控面板高度双向等高：与左侧服务器面板同高（服务器面板不被动拉伸）
    this.syncMonitorPanelHeight();
    if (this.monitorSeriesCache.has(server.server_name)) {
      this.renderMonitorCharts(
        server.server_name,
        this.monitorSeriesCache.get(server.server_name)
      );
    } else {
      // 进入视图首次：拉取时间序列（含摘要，含停用期间的历史数据）
      this.loadMonitorSeries(server.server_name);
    }
  }

  updateMonitorStatusLine(server) {
    const line = document.getElementById('monitor-status-line');
    if (!line) return;
    const m = server.monitor || {};
    const parts = [];
    parts.push(`<span class="monitor-dot ${m.running ? 'on' : 'off'}"></span> 采集${m.running ? '中' : '未运行'}`);
    parts.push(`间隔 ${m.interval || '-'}s`);
    parts.push(`保留 ${m.retention_days ?? '-'} 天`);
    const tpsPref = (m.tps_command || 'auto').trim().toLowerCase();
    if (tpsPref === '' || tpsPref === 'auto') {
      const resolved = m.tps_command_resolved || m.tps_command || '-';
      parts.push(`TPS 指令 <code>${escapeHtml(resolved)}</code>（按服务端自动）`);
    } else {
      parts.push(`TPS 指令 <code>${escapeHtml(m.tps_command)}</code>`);
    }
    parts.push(`已采样 ${m.sample_count ?? 0} 条`);
    const pingTarget = m.ping_target || '';
    if (pingTarget) {
      const pingLabel = (m.ping_host || '').trim()
        ? `延迟探测 <code>${escapeHtml(pingTarget)}</code>（域名）`
        : `延迟探测 <code>${escapeHtml(pingTarget)}</code>`;
      parts.push(pingLabel);
    } else {
      parts.push('延迟探测 <span class="monitor-err">未配置</span>（⚙ 设置里填公网域名/端口）');
    }
    if (m.last_ts) parts.push(`最近采样 ${this.formatClock(m.last_ts)}`);
    if (m.last_error) {
      const err = m.last_error;
      const short = err.length > 28 ? err.slice(0, 28) + '…' : err;
      line.innerHTML = parts.join(' · ') +
        ` &nbsp;<span class="monitor-err" title="${escapeHtml(err)}">⚠ ${escapeHtml(short)}</span>`;
      return;
    }
    line.innerHTML = parts.join(' · ');
  }

  formatClock(ts) {
    const d = new Date(ts * 1000);
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  // 按子页面渲染统计卡：kind='tps' 或 'latency'，写入对应容器
  renderMonitorSummary(payload, kind) {
    const boxId = kind === 'latency' ? 'monitor-summary-latency' : 'monitor-summary-tps';
    const box = document.getElementById(boxId);
    if (!box) return;
    const s = payload.series || {};
    const fmt = (v, suffix = '') => (v == null ? '--' : `${v}${suffix}`);
    let cards = [];
    if (kind === 'latency') {
      const lat = (s.latency || {}).summary || {};
      cards = [
        { label: '平均延迟', value: fmt(lat.avg, 'ms') },
        { label: '最大延迟', value: fmt(lat.max, 'ms') },
        { label: 'P95 延迟', value: fmt(lat.p95, 'ms') },
        { label: '采样数', value: fmt(lat.count) },
      ];
    } else {
      const tps = (s.tps || {}).summary || {};
      cards = [
        { label: '平均 TPS', value: fmt(tps.avg), cls: this.tpsValueClass(tps.avg) },
        { label: '最低 TPS', value: fmt(tps.min), cls: this.tpsValueClass(tps.min) },
        { label: '采样数', value: fmt(tps.count) },
      ];
    }
    box.innerHTML = cards.map(c => `
      <div class="monitor-stat-card">
        <span class="monitor-stat-label">${c.label}</span>
        <span class="monitor-stat-value ${c.cls || ''}">${c.value}</span>
      </div>`).join('');
  }

  tpsValueClass(v) {
    if (v == null) return '';
    if (v < 15) return 'monitor-danger';
    if (v < 19) return 'monitor-warning';
    return 'monitor-good';
  }

  async loadMonitorSeries(serverName) {
    if (this.isMonitorLoading) return;
    this.isMonitorLoading = true;
    try {
      // 实时模式：窗口 60 秒，桶宽跟随设置的采样频率（realtime_interval，
      // 1~30 秒）——1s 频率 → 1s 桶 → 60 秒窗口 60 个点，曲线逐点滚动；
      // 此前桶宽写死 10s，1s 采样被聚合进 10s 桶，曲线 10 秒才动一次
      const isRealtime = this.monitorRange === 'realtime';
      // 请求带超时保护：series 拉取挂起时不得卡死实时 tick 链（apiGet 的
      // fetch 无超时，若不限制，个别慢响应会令实时模式停在某一轮）
      const payload = await Promise.race([
        this.apiGet(
          `monitor/${encodeURIComponent(serverName)}/series`,
          isRealtime
            ? { range: '1m', bucket: `${Math.max(1, Math.min(30, this.realtimeInterval || 5))}s` }
            : { range: `${this.monitorRange}h` }
        ),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('监控数据请求超时')), 8000)
        ),
      ]);
      this.monitorSeriesCache.set(serverName, payload);
      // 拉取期间用户已切换视图，丢弃过期结果
      if (this.activeServerTab !== serverName) return;
      this.renderMonitorCharts(serverName, payload);
    } catch (e) {
      console.warn('拉取监控数据失败:', e);
      const line = document.getElementById('monitor-status-line');
      if (line && this.activeServerTab === serverName) {
        line.innerHTML =
          `<span class="monitor-err">⚠ 监控数据加载失败: ${escapeHtml(e.message || '网络错误')}</span>`;
      }
    } finally {
      this.isMonitorLoading = false;
    }
  }

  renderMonitorCharts(serverName, payload) {
    // 两个子页面各自的统计卡
    this.renderMonitorSummary(payload, 'tps');
    this.renderMonitorSummary(payload, 'latency');
    const series = payload.series || {};
    // 实时模式：x 轴窗口直接取**数据实际范围**（t0/t1 = 最小/最大桶）——
    // 数据桶每秒 1 个、同秒合并后 59~60 桶，固定 60 格窗口永远比数据宽：
    // 右端被「当前未完成秒」的桶顶死在右缘、左端空出起始秒（曲线整体
    // 右移、最新点贴/冲出边缘）。数据范围窗口让曲线**铺满绘图区**，
    // 左贴右贴无留白；数据每秒滚动时窗口同步跟随，等效实时滚动
    if (this.monitorTab !== 'latency') {
      const tpsCanvas = document.getElementById('monitor-chart-tps');
      if (tpsCanvas) {
        this.drawTimeSeries(tpsCanvas, {
          lines: [
            { name: '1m', color: '#4ade80', points: (series.tps || {}).points || [] },
            { name: '5m', color: '#fbbf24', points: (series.tps5m || {}).points || [] },
            { name: '15m', color: '#f472b6', points: (series.tps15m || {}).points || [] },
          ],
          rangeHours: payload.range_hours || 24,
          legend: true,
          yMin: 0,
          yMax: 20,
          yTicks: 4,
          decimals: 1,
        });
      }
    } else {
      const latCanvas = document.getElementById('monitor-chart-latency');
      if (latCanvas) {
        this.drawTimeSeries(latCanvas, {
          lines: [
            { name: '延迟', color: '#60a5fa', points: (series.latency || {}).points || [] },
          ],
          rangeHours: payload.range_hours || 24,
          legend: false,
          yMin: 0,
          dynamicMax: true,
          yTicks: 4,
          decimals: 0,
        });
      }
    }
  }

  redrawMonitorCharts() {
    const server = this.activeServerObject();
    if (!server) return;
    const payload = this.monitorSeriesCache.get(server.server_name);
    if (!payload) return;
    this.renderMonitorCharts(server.server_name, payload);
  }

  formatTsLabel(ts, rangeHours) {
    const d = new Date(ts * 1000);
    const pad = n => String(n).padStart(2, '0');
    // 短窗口（< 1 小时，实时模式 60 秒）：秒级刻度才跟得上逐秒滚动
    if (rangeHours < 1) {
      return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }
    if (rangeHours > 48) return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  drawTimeSeries(canvas, opts) {
    const wrap = canvas.parentElement;
    const rect = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const W = Math.max(80, rect.width);
    const H = Math.max(80, rect.height);
    canvas.width = Math.floor(W * dpr);
    canvas.height = Math.floor(H * dpr);
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    const css = getComputedStyle(document.documentElement);
    const gridColor = css.getPropertyValue('--chart-grid').trim() || 'rgba(148,163,184,0.15)';
    const textColor = css.getPropertyValue('--text-muted').trim() || '#94a3b8';

    const pad = { top: 16, right: 12, bottom: 24, left: 48 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    const lines = opts.lines.filter(l => l.points && l.points.length > 0);
    if (!lines.length) {
      ctx.fillStyle = textColor;
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('该时间窗内暂无采样数据', W / 2, H / 2 - 2);
      this.chartState = null;
      return;
    }

    // 值域：固定 yMin/yMax 优先；dynamicMax 时按数据上浮取整
    let yMin = opts.yMin != null ? opts.yMin : Infinity;
    let yMax = opts.yMax != null ? opts.yMax : -Infinity;
    if (opts.yMin == null || opts.yMax == null) {
      for (const line of lines) {
        for (const p of line.points) {
          if (opts.yMin == null) yMin = Math.min(yMin, p.min);
          if (opts.yMax == null) yMax = Math.max(yMax, p.max);
        }
      }
    }
    if (opts.dynamicMax) {
      yMin = 0;
      yMax = Math.max(Math.ceil(yMax * 1.15), 1);
    }
    if (yMin === yMax) yMax = yMin + 1;

    // 时间范围（跨所有线）；fixedWindow 时 x 轴固定为该窗口（实时模式
    // 滚动），窗口外的点坐标超出画布由 canvas 自动裁剪
    let t0 = Infinity, t1 = -Infinity;
    if (opts.fixedWindow) {
      [t0, t1] = opts.fixedWindow;
    } else {
      for (const line of lines) {
        t0 = Math.min(t0, line.points[0].ts);
        t1 = Math.max(t1, line.points[line.points.length - 1].ts);
      }
    }
    if (t1 <= t0) t1 = t0 + 1;
    const xAt = ts => pad.left + (ts - t0) / (t1 - t0) * plotW;
    const yAt = v => pad.top + (1 - (v - yMin) / (yMax - yMin)) * plotH;

    // 横网格 + y 轴刻度
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    const yTicks = opts.yTicks || 4;
    for (let i = 0; i <= yTicks; i++) {
      const v = yMin + (yMax - yMin) * i / yTicks;
      const yy = yAt(v);
      ctx.strokeStyle = gridColor;
      ctx.beginPath();
      ctx.moveTo(pad.left, yy);
      ctx.lineTo(W - pad.right, yy);
      ctx.stroke();
      ctx.fillStyle = textColor;
      ctx.fillText(v.toFixed(opts.decimals != null ? opts.decimals : 0), pad.left - 6, yy);
    }

    // 纵网格 + x 轴时间标签
    ctx.textAlign = 'center';
    ctx.textBaseline = 'alphabetic';
    const xTicks = 5;
    for (let i = 0; i <= xTicks; i++) {
      const ts = t0 + (t1 - t0) * i / xTicks;
      const xx = xAt(ts);
      ctx.strokeStyle = gridColor;
      ctx.beginPath();
      ctx.moveTo(xx, pad.top);
      ctx.lineTo(xx, H - pad.bottom);
      ctx.stroke();
      const label = this.formatTsLabel(ts, opts.rangeHours || 24);
      ctx.fillStyle = textColor;
      // 标签防裁剪：居中绘制，但左右边缘的标签（如最新时刻贴右缘）文本
      // 超出画布会被切半——整体平移钳制到画布内
      const labelW = ctx.measureText(label).width;
      let lxx = xx;
      if (lxx + labelW / 2 > W - 4) lxx = W - 4 - labelW / 2;
      if (lxx - labelW / 2 < 2) lxx = 2 + labelW / 2;
      ctx.fillText(label, lxx, H - 8);
    }

    // 各线：min~max 半透明带 + avg 折线 + 末端点
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    for (const line of lines) {
      const pts = line.points;
      ctx.beginPath();
      pts.forEach((p, idx) => {
        const xx = xAt(p.ts);
        if (idx === 0) ctx.moveTo(xx, yAt(p.max));
        else ctx.lineTo(xx, yAt(p.max));
      });
      for (let i = pts.length - 1; i >= 0; i--) ctx.lineTo(xAt(pts[i].ts), yAt(pts[i].min));
      ctx.closePath();
      ctx.globalAlpha = 0.13;
      ctx.fillStyle = line.color;
      ctx.fill();
      ctx.globalAlpha = 1;

      ctx.beginPath();
      pts.forEach((p, idx) => {
        const xx = xAt(p.ts);
        if (idx === 0) ctx.moveTo(xx, yAt(p.avg));
        else ctx.lineTo(xx, yAt(p.avg));
      });
      ctx.strokeStyle = line.color;
      ctx.lineWidth = 1.6;
      ctx.stroke();

      const last = pts[pts.length - 1];
      ctx.beginPath();
      ctx.arc(xAt(last.ts), yAt(last.avg), 2.4, 0, Math.PI * 2);
      ctx.fillStyle = line.color;
      ctx.fill();
    }

    // 图例（线名色块）画在绘图区左上角
    if (opts.legend) {
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.font = '10px sans-serif';
      let lx = pad.left;
      for (const line of lines) {
        const label = line.name;
        ctx.fillStyle = line.color;
        ctx.fillRect(lx, pad.top - 11, 10, 3);
        ctx.fillStyle = textColor;
        ctx.fillText(label, lx + 14, pad.top - 9.5);
        lx += 14 + ctx.measureText(label).width + 18;
      }
    }

    // 记录命中数据供 hover tooltip / resize 重绘
    this.chartState = {
      wrap,
      opts: { ...opts, lines, yMin, yMax, t0, t1, xAt, yAt },
    };
  }

  onChartHover(e) {
    const state = this.chartState;
    if (!state) return;
    const rect = state.wrap.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const { t0, t1, xAt } = state.opts;
    const hoverTs = t0 + (mx - 48) / (rect.width - 48 - 12) * (t1 - t0);
    let best = null;
    let bestDist = Infinity;
    for (const line of state.opts.lines) {
      for (const p of line.points) {
        const dist = Math.abs(p.ts - hoverTs);
        if (dist < bestDist) {
          bestDist = dist;
          best = { line, p };
        }
      }
    }
    if (!best || typeof best.p.avg !== 'number') return;
    const span = t1 - t0;
    if (bestDist > span * 0.5) return;
    const xx = xAt(best.p.ts);
    const yy = state.opts.yAt(best.p.avg);
    let html = `<div class="monitor-tip-time">${this.formatTsLabel(best.p.ts, state.opts.rangeHours || 24)}</div>`;
    html += `<div><span class="monitor-tip-swatch" style="background:${best.line.color}"></span>` +
      `${escapeHtml(best.line.name)}: <b>${best.p.avg}</b></div>`;
    html += `<div class="monitor-tip-sub">min ${best.p.min} / max ${best.p.max} / 样本 ${best.p.count}</div>`;
    this.showChartTooltip(state.wrap, html, xx, yy);
  }

  showChartTooltip(wrap, html, x, y) {
    let tip = wrap.querySelector('.monitor-tooltip');
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'monitor-tooltip';
      wrap.appendChild(tip);
    }
    tip.innerHTML = html;
    const wrapRect = wrap.getBoundingClientRect();
    const tipW = tip.offsetWidth || 150;
    const left = Math.min(Math.max(4, x - tipW / 2), wrapRect.width - tipW - 4);
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(2, y - 34)}px`;
    tip.style.display = 'block';
  }

  hideChartTooltip() {
    document.querySelectorAll('.monitor-tooltip').forEach(t => {
      t.style.display = 'none';
    });
  }

  // 性能监控子页面：'tps' | 'latency'（手动切换仅本次浏览有效，
  // 默认展示项由设置里的「默认展示」保存到后端，刷新/重开按默认恢复）
  setMonitorTab(tab) {
    if (tab !== 'tps' && tab !== 'latency') return;
    // 幂等：当前 tab 与 DOM 状态一致时跳过（避免面板每次刷新都触发重绘）
    const activeBtn = document.querySelector('.monitor-tab.active');
    if (this.monitorTab === tab && activeBtn && activeBtn.dataset.tab === tab) return;
    this.monitorTab = tab;
    document.querySelectorAll('.monitor-tab').forEach(b =>
      b.classList.toggle('active', b.dataset.tab === tab));
    document.getElementById('monitor-page-tps')?.classList.toggle('hidden', tab !== 'tps');
    document.getElementById('monitor-page-latency')?.classList.toggle('hidden', tab !== 'latency');
    // 目标 canvas 刚从 hidden 容器恢复尺寸，立即重绘
    const server = this.activeServerObject();
    if (server && this.monitorSeriesCache.has(server.server_name)) {
      this.renderMonitorCharts(server.server_name,
        this.monitorSeriesCache.get(server.server_name));
    }
  }

  bindMonitorActions() {
    const rangeSel = document.getElementById('monitor-range');
    rangeSel?.addEventListener('change', () => {
      if (rangeSel.value === 'realtime') {
        this.startRealtime();
        return;
      }
      this.stopRealtime();
      this.monitorRange = rangeSel.value;
      const server = this.activeServerObject();
      if (!server) return;
      this.monitorSeriesCache.delete(server.server_name);
      this.loadMonitorSeries(server.server_name);
    });
    document.getElementById('monitor-refresh')?.addEventListener('click', () => {
      const server = this.activeServerObject();
      if (!server) return;
      this.monitorSeriesCache.delete(server.server_name);
      this.loadMonitorSeries(server.server_name);
    });
    document.getElementById('monitor-sample-btn')?.addEventListener('click', () => this.sampleMonitorNow());
    // 子页面切换（TPS / 延迟）：统一走 setMonitorTab（会持久化默认展示项）
    document.querySelectorAll('.monitor-tab').forEach(btn => {
      btn.addEventListener('click', () => this.setMonitorTab(btn.dataset.tab));
    });
    // 设置弹窗：监控参数仅在此维护（不走插件 WebUI 配置）
    document.getElementById('monitor-settings-btn')?.addEventListener('click', () => this.openMonitorSettings());
    document.getElementById('ms-close')?.addEventListener('click', () => this.closeMonitorSettings());
    document.getElementById('ms-cancel')?.addEventListener('click', () => this.closeMonitorSettings());
    document.getElementById('ms-save')?.addEventListener('click', () => this.saveMonitorSettings());
    document.getElementById('ms-clear-data')?.addEventListener('click', () => this.clearMonitorData());
    const overlay = document.getElementById('monitor-settings-modal');
    overlay?.addEventListener('click', (e) => {
      if (e.target === overlay) this.closeMonitorSettings();
    });
    // 通用二次确认弹窗：✕ / 取消 / 点击遮罩均视为取消
    const confirmOverlay = document.getElementById('confirm-modal');
    confirmOverlay?.addEventListener('click', (e) => {
      if (e.target === confirmOverlay) this.confirmDialogDismiss(false);
    });
    document.getElementById('cf-close')?.addEventListener('click', () => this.confirmDialogDismiss(false));
    document.getElementById('cf-cancel')?.addEventListener('click', () => this.confirmDialogDismiss(false));
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      // 确认弹窗叠在设置弹窗之上，Esc 优先关闭确认弹窗
      if (this._confirmWaiter) this.confirmDialogDismiss(false);
      else if (this.isMonitorSettingsOpen()) this.closeMonitorSettings();
    });
    // hover 提示与窗口缩放重绘
    document.querySelectorAll('.monitor-chart-wrap').forEach(wrap => {
      wrap.addEventListener('mousemove', (e) => this.onChartHover(e));
      wrap.addEventListener('mouseleave', () => this.hideChartTooltip());
    });
    window.addEventListener('resize', () => {
      this.syncMonitorPanelHeight();
      this.redrawMonitorCharts();
      this.hideChartTooltip();
    });
    // 高度随时跟随：任一面板尺寸变化（玩家列表/图表渲染/服务器卡增减）
    // 都自动重新做监控面板等高钳制，避免异步渲染后只因一次同步就失效
    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(() => this.syncMonitorPanelHeight());
      const sp = document.querySelector('.servers-panel');
      const mp = document.getElementById('monitor-panel');
      if (sp) ro.observe(sp);
      if (mp) ro.observe(mp);
      this._panelResizeObserver = ro;
    }
    // 玩家进出/卡片 innerHTML 重建等 DOM 变更即时触发跟随：MutationObserver
    // 比尺寸变化更早感知（玩家 tag 增删可能发生在 ResizeObserver 结算前），
    // 用 rAF 合并并等布局结算后读取真实高度
    if (typeof MutationObserver !== 'undefined') {
      const mo = new MutationObserver(() => {
        if (this._panelSyncFrame) return;
        this._panelSyncFrame = requestAnimationFrame(() => {
          this._panelSyncFrame = 0;
          this.syncMonitorPanelHeight();
        });
      });
      const sc = document.getElementById('servers-container');
      if (sc) mo.observe(sc, { childList: true, subtree: true });
      this._panelMutationObserver = mo;
    }
  }

  // 监控面板高度双向等高：面板高度跟随左侧服务器面板（服务器面板保持
  // 内容自然高度；监控面板与之等高、底部对齐）。flex 列布局下图表区
  // 吃掉剩余空间，监控内容超出时图表自动压缩，仍溢出则面板内滚动。
  // 固定 height（而非 min-height）确保等高成立。
  syncMonitorPanelHeight() {
    const panel = document.getElementById('monitor-panel');
    const serversPanel = document.querySelector('.servers-panel');
    if (!panel || !serversPanel) return;
    if (window.innerWidth <= 900) {
      // 单列布局：各面板自然高度，无需钳制
      panel.style.minHeight = '';
      panel.style.height = '';
      return;
    }
    if (panel.classList.contains('hidden')) {
      panel.style.minHeight = '';
      panel.style.height = '';
      return;
    }
    // 双向等高：以左侧服务器面板高度为准（监控面板不再高于它）
    const h = serversPanel.offsetHeight;
    if (h > 0 && panel.style.height !== h + 'px') {
      panel.style.minHeight = '';
      panel.style.height = h + 'px';
    }
  }

  // ---------- 「功能设置」折叠面板（AI 对话 / 面板偏好） ----------
  // 折叠状态由后端 panel_prefs.json 记忆（换设备 / 刷新后保持）
  setSettingsCollapsed(collapsed, { persist = true } = {}) {
    const panel = document.getElementById('settings-panel');
    if (!panel) return;
    const on = !!collapsed;
    this.settingsCollapsed = on;
    panel.classList.toggle('collapsed', on);
    const caret = document.getElementById('settings-caret');
    if (caret) caret.textContent = on ? '▸' : '▾';
    const toggle = document.getElementById('settings-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', on ? 'false' : 'true');
    if (!persist) return;
    // 后端为权威；写失败只记日志，不阻塞交互（下次加载以后端为准）
    this.apiPost('panel/prefs', { settings_collapsed: on }).catch((e) => {
      console.warn('保存面板折叠状态失败:', e);
    });
  }

  // 填充设置面板：AI 组按当前服务器（来自 conf 条目，回落服务器摘要），
  // 全局视图下无目标服务器时整组禁用；偏好组为全局值
  renderSettingsPanel() {
    const panel = document.getElementById('settings-panel');
    if (!panel) return;
    const server = this.activeServerObject();
    // 全部服务器视图：整块隐藏。AI 开关与互通终端天数都需落在具体服务器上，
    // 全局视图不展示也不可保存（自动刷新间隔已迁至右上角「⚙ 设置」弹窗）
    if (!server) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    if (typeof this.settingsCollapsed === 'boolean') {
      panel.classList.toggle('collapsed', this.settingsCollapsed);
      const caret = document.getElementById('settings-caret');
      if (caret) caret.textContent = this.settingsCollapsed ? '▸' : '▾';
      const toggle = document.getElementById('settings-toggle');
      if (toggle) {
        toggle.setAttribute('aria-expanded', this.settingsCollapsed ? 'false' : 'true');
      }
    }
    const aiGroup = document.getElementById('settings-group-ai');
    const enabledBox = document.getElementById('st-ai-enabled');
    const prefixBox = document.getElementById('st-ai-prefix');
    const saveBtn = document.getElementById('settings-save');
    const status = document.getElementById('settings-status');
    const confItem = (this.configServers || [])
      .find((s) => s.server_name === server.server_name) || null;
    if (enabledBox && prefixBox) {
      enabledBox.checked = confItem && typeof confItem.enable_ai_chat === 'boolean'
        ? confItem.enable_ai_chat
        : server.enable_ai_chat !== false;
      prefixBox.value = confItem && typeof confItem.ai_chat_prefix === 'string'
        ? confItem.ai_chat_prefix
        : (server.ai_chat_prefix || '');
      enabledBox.disabled = false;
      prefixBox.disabled = false;
      if (aiGroup) aiGroup.classList.remove('disabled');
      if (saveBtn) saveBtn.disabled = false;
      if (status) status.textContent = '';
    }
    // 互通终端天数（每台服务器独立，conf 条目顶层；缺省 2）：
    // 正在编辑的输入框不回写，避免打断输入
    const daysBox = document.getElementById('st-terminal-days');
    if (daysBox && document.activeElement !== daysBox) {
      const daysVal = confItem && Number.isFinite(confItem.terminal_days)
        ? confItem.terminal_days
        : 2;
      daysBox.value = String(Math.max(0, Math.min(30, daysVal)));
    }
    // 消息转发配置（conf 的 message 子对象，缺省回落后端 _message_view 默认）：
    // 任一转发控件正被编辑时整组不回写，避免打断输入
    const fwdBoxes = {
      chat: document.getElementById('st-fwd-chat'),
      format: document.getElementById('st-fwd-chat-format'),
      join: document.getElementById('st-fwd-joinleave'),
      death: document.getElementById('st-fwd-death'),
      ach: document.getElementById('st-fwd-achievement'),
      image: document.getElementById('st-fwd-image'),
      imageToMc: document.getElementById('st-fwd-image-to-mc'),
      imageFromMc: document.getElementById('st-fwd-image-from-mc'),
      prefix: document.getElementById('st-fwd-prefix'),
      sessions: document.getElementById('st-fwd-sessions'),
    };
    const fwdFocused = Object.values(fwdBoxes)
      .some((el) => el && document.activeElement === el);
    if (!fwdFocused) {
      const msg = (confItem && confItem.message) || {};
      if (fwdBoxes.chat) fwdBoxes.chat.checked = msg.forward_chat_to_astrbot !== false;
      if (fwdBoxes.format) {
        fwdBoxes.format.value = typeof msg.forward_chat_format === 'string'
          ? msg.forward_chat_format
          : '';
      }
      if (fwdBoxes.join) fwdBoxes.join.checked = !!msg.forward_join_leave_to_astrbot;
      if (fwdBoxes.death) fwdBoxes.death.checked = !!msg.forward_death_to_astrbot;
      if (fwdBoxes.ach) fwdBoxes.ach.checked = !!msg.forward_achievement_to_astrbot;
      // 图片转发：两个方向分别回显；总开关 = 两个方向都开启才勾选
      if (fwdBoxes.imageToMc) fwdBoxes.imageToMc.checked = !!msg.forward_image_to_mc;
      if (fwdBoxes.imageFromMc) fwdBoxes.imageFromMc.checked = !!msg.forward_image_from_mc;
      if (fwdBoxes.image) {
        fwdBoxes.image.checked = !!(msg.forward_image_to_mc && msg.forward_image_from_mc);
      }
      if (fwdBoxes.prefix) {
        fwdBoxes.prefix.value = typeof msg.auto_forward_prefix === 'string'
          ? msg.auto_forward_prefix
          : '';
      }
      if (fwdBoxes.sessions) {
        const sessions = Array.isArray(confItem && confItem.target_sessions)
          ? confItem.target_sessions
          : [];
        fwdBoxes.sessions.value = sessions.join('\n');
      }
    }
  }

  async saveSettingsPanel() {
    const server = this.activeServerObject();
    // 全局视图（全部服务器）下面板已隐藏，防御性直接返回
    if (!server) return;
    const saveBtn = document.getElementById('settings-save');
    const status = document.getElementById('settings-status');
    const daysBox = document.getElementById('st-terminal-days');
    const daysVal = parseInt(daysBox ? daysBox.value : '', 10);
    // 后端会防御式钳制，这里提前提示常见误配
    if (!Number.isFinite(daysVal) || daysVal < 0 || daysVal > 30) {
      this.showToast('互通终端加载天数需在 0-30 之间', 'error');
      return;
    }
    const enabledBox = document.getElementById('st-ai-enabled');
    const prefixBox = document.getElementById('st-ai-prefix');
    const aiEnabled = !!(enabledBox && enabledBox.checked);
    const aiPrefix = prefixBox ? prefixBox.value.trim() : '';
    const confItem = server
      ? (this.configServers || []).find((s) => s.server_name === server.server_name) || null
      : null;
    // 前缀冲突预检：AI 前缀与自动转发前缀互相包含时，同一条消息会命中两条
    // 路径（启动时后端也会告警），这里提前拦截
    const fwdMsg = (confItem && confItem.message) || {};
    const forwardPrefix = (typeof fwdMsg.auto_forward_prefix === 'string' && fwdMsg.auto_forward_prefix)
      || (confItem && confItem.auto_forward_prefix)
      || (server && server.auto_forward_prefix) || '';
    if (server && aiEnabled && aiPrefix && forwardPrefix &&
        (aiPrefix.startsWith(forwardPrefix) || forwardPrefix.startsWith(aiPrefix))) {
      this.showToast('AI 触发前缀与自动转发前缀互相包含，请改成互不包含的前缀', 'error');
      return;
    }
    if (saveBtn) saveBtn.disabled = true;
    if (status) status.textContent = '保存中…';
    try {
      // 互通终端天数 + AI/消息转发：全部写插件 conf（每台服务器独立）。
      // 后端对「只改软开关」的保存走落盘 + 就地生效，不重建连接（reloaded=false）；
      // 一旦带上连接类字段才热重载
      let reloaded = false;
      let daysChanged = false;
      {
        const payload = { enable_ai_chat: aiEnabled, ai_chat_prefix: aiPrefix };
        // 互通终端加载天数（单服生效，0~30；后端会再钳制一次）
        daysChanged = daysVal !== this.terminalDaysFor(server.server_name);
        payload.terminal_days = daysVal;
        // 消息转发：显式提交全部值（面板展示的即当前生效值，覆盖语义）
        const msg = {};
        const fwdChat = document.getElementById('st-fwd-chat');
        const fwdFormat = document.getElementById('st-fwd-chat-format');
        const fwdJoin = document.getElementById('st-fwd-joinleave');
        const fwdDeath = document.getElementById('st-fwd-death');
        const fwdAch = document.getElementById('st-fwd-achievement');
        const fwdImage = document.getElementById('st-fwd-image');
        const fwdImageToMc = document.getElementById('st-fwd-image-to-mc');
        const fwdImageFromMc = document.getElementById('st-fwd-image-from-mc');
        const fwdPrefix = document.getElementById('st-fwd-prefix');
        const fwdSessions = document.getElementById('st-fwd-sessions');
        if (fwdChat && fwdFormat && fwdJoin && fwdDeath && fwdAch && fwdImage && fwdPrefix && fwdSessions) {
          msg.forward_chat_to_astrbot = !!fwdChat.checked;
          msg.forward_chat_format = fwdFormat.value.trim();
          msg.forward_join_leave_to_astrbot = !!fwdJoin.checked;
          msg.forward_death_to_astrbot = !!fwdDeath.checked;
          msg.forward_achievement_to_astrbot = !!fwdAch.checked;
          // 图片转发：按两个方向的实际勾选分别保存（总开关只做快捷全开/全关联动）
          msg.forward_image_to_mc = !!(fwdImageToMc && fwdImageToMc.checked);
          msg.forward_image_from_mc = !!(fwdImageFromMc && fwdImageFromMc.checked);
          msg.auto_forward_prefix = fwdPrefix.value.trim();
          payload.message = msg;
          // 目标会话：每行一个 UMO（同服务器表单解析规则）
          payload.target_sessions = fwdSessions.value
            .split('\n').map((s) => s.trim()).filter(Boolean);
        }
        if (confItem && Number.isFinite(confItem.index)) {
          payload.index = confItem.index;
        } else {
          payload.server_name = server.server_name;
        }
        const resp = await this.apiPost('config/server/update', payload);
        if (resp && Array.isArray(resp.servers)) this.configServers = resp.servers;
        reloaded = !!(resp && resp.reloaded);
        if (daysChanged) {
          // 展示窗口变化：清空当前终端流，下一次渲染按新窗口重拉
          const curKey = this.activeServerTab;
          if (curKey && curKey !== 'all') {
            const stream = this.ensureTerminalStream(curKey);
            if (stream) {
              stream.innerHTML = '';
              stream.dataset.rendered = '0';
              stream.dataset.lastDate = '';
            }
          }
        }
      }
      if (status) status.textContent = '已保存';
      this.showToast(
        reloaded
          ? '功能设置已保存（连接配置变更，已重连）'
          : '功能设置已保存并即时生效（未重连）',
        'success'
      );
      await this.refreshAll(true);
    } catch (e) {
      if (status) status.textContent = '';
      this.showToast('保存功能设置失败: ' + (e.message || '网络错误'), 'error');
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  bindSettingsActions() {
    document.getElementById('settings-toggle')?.addEventListener('click', () => {
      this.setSettingsCollapsed(!this.settingsCollapsed);
    });
    document.getElementById('settings-save')?.addEventListener('click', () => {
      this.saveSettingsPanel();
    });
    // 右上角「⚙ 设置」：总设置弹窗（自动刷新间隔等全局偏好）
    document.getElementById('btn-config-link')?.addEventListener('click', () => {
      this.openSettingsModal();
    });
    document.getElementById('gs-close')?.addEventListener('click', () => {
      this.closeSettingsModal();
    });
    document.getElementById('gs-cancel')?.addEventListener('click', () => {
      this.closeSettingsModal();
    });
    document.getElementById('gs-save')?.addEventListener('click', () => {
      this.saveSettingsModal();
    });
    // 点击遮罩空白处关闭（与监控设置弹窗行为一致）
    document.getElementById('settings-modal')?.addEventListener('click', (e) => {
      if (e.target === e.currentTarget) this.closeSettingsModal();
    });
    // 图片转发折叠框：总开关快捷全开/全关，子开关分别控制，展开/收起子区
    const fwdImageTotal = document.getElementById('st-fwd-image');
    const fwdImageToMc = document.getElementById('st-fwd-image-to-mc');
    const fwdImageFromMc = document.getElementById('st-fwd-image-from-mc');
    fwdImageTotal?.addEventListener('change', () => {
      if (fwdImageToMc) fwdImageToMc.checked = !!fwdImageTotal.checked;
      if (fwdImageFromMc) fwdImageFromMc.checked = !!fwdImageTotal.checked;
    });
    [fwdImageToMc, fwdImageFromMc].forEach((box) => {
      box?.addEventListener('change', () => {
        // 总开关只反映「两个方向都已开启」；任一方向被单独关闭则不勾选
        if (fwdImageTotal) {
          fwdImageTotal.checked = !!(fwdImageToMc && fwdImageToMc.checked
            && fwdImageFromMc && fwdImageFromMc.checked);
        }
      });
    });
    const fwdImageToggleBtn = document.getElementById('st-fwd-image-toggle');
    fwdImageToggleBtn?.addEventListener('click', () => {
      const subgroup = document.getElementById('st-fwd-image-subgroup');
      if (!subgroup) return;
      const collapsed = subgroup.classList.toggle('hidden');
      fwdImageToggleBtn.textContent = collapsed ? '展开 ⯈' : '收起 ⯆';
      fwdImageToggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    });
  }

  // 打开右上角总设置弹窗：回写当前生效的自动刷新间隔
  openSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (!modal) return;
    const refreshBox = document.getElementById('st-auto-refresh');
    if (refreshBox) {
      refreshBox.value = String(
        Number.isFinite(this.autoRefreshIntervalPref)
          ? this.autoRefreshIntervalPref
          : (this.autoRefreshInterval || 10));
    }
    modal.classList.remove('hidden');
  }

  closeSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.add('hidden');
  }

  // 保存总设置：自动刷新间隔写 panel_prefs.json，保存后即时生效（不重连）
  async saveSettingsModal() {
    const refreshBox = document.getElementById('st-auto-refresh');
    const refreshVal = parseInt(refreshBox ? refreshBox.value : '', 10);
    if (!Number.isFinite(refreshVal) || refreshVal < 10 || refreshVal > 3600) {
      this.showToast('自动刷新间隔需在 10-3600 秒之间', 'error');
      return;
    }
    const saveBtn = document.getElementById('gs-save');
    if (saveBtn) saveBtn.disabled = true;
    try {
      await this.apiPost('panel/prefs', {
        auto_refresh_interval: refreshVal,
      });
      this.autoRefreshIntervalPref = refreshVal;
      this.autoRefreshInterval = refreshVal;
      this.syncAutoRefreshLabel();
      this.setupAutoRefresh(
        document.getElementById('auto-refresh-toggle')?.checked || false
      );
      this.showToast('总设置已保存并即时生效', 'success');
      this.closeSettingsModal();
    } catch (e) {
      this.showToast('保存总设置失败: ' + (e.message || '网络错误'), 'error');
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  bindTerminalActions() {
    const input = document.getElementById('terminal-input');
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.isComposing) {
          e.preventDefault();
          const v = input.value.trim();
          if (v.startsWith('/')) {
            this.runCommand();
          } else {
            this.sendBroadcast();
          }
        }
      });
    }
    document.getElementById('terminal-broadcast')?.addEventListener('click', () => this.sendBroadcast());
    document.getElementById('terminal-cmd')?.addEventListener('click', () => this.runCommand());
    // 自动滚动开关：开启时新消息自动滚到底部，关闭时停在当前位置阅读历史。
    // 关闭后仅当手动滚到**真正底部**（误差 ≤1px）才自动恢复；中途上滚
    // 不会误触发
    document.getElementById('terminal-autoscroll')?.addEventListener('click', () => {
      this.terminalAutoscroll = !this.terminalAutoscroll;
      this.syncAutoscrollButton();
      if (this.terminalAutoscroll) this.scrollTerminalToBottom();
    });
    // 暂停状态下滚到真正底部 → 自动恢复自动滚动
    const terminalBody = document.getElementById('terminal-body');
    if (terminalBody) {
      terminalBody.addEventListener('scroll', () => {
        if (this.terminalAutoscroll) return;
        const atBottom =
          terminalBody.scrollHeight - terminalBody.scrollTop - terminalBody.clientHeight <= 1;
        if (atBottom) {
          this.terminalAutoscroll = true;
          this.syncAutoscrollButton();
        }
      });
    }
    document.getElementById('terminal-refresh')?.addEventListener('click', async () => {
      const key = this.activeServerTab;
      if (!key || key === 'all') return;
      await this.loadTerminalLogs(key, this.ensureTerminalStream(key));
    });
    document.getElementById('terminal-clear')?.addEventListener('click', async () => {
      const key = this.activeServerTab;
      if (!key || key === 'all') return;
      const stream = this.ensureTerminalStream(key);
      stream.innerHTML = '';
      stream.dataset.rendered = '0';
      stream.dataset.lastDate = '';
      try {
        // 同步清除后端持久化日志，仅此操作会删除历史
        await this.apiPost('terminal_logs/clear', { server: key });
      } catch (e) {
        console.warn('清除后端终端日志失败:', e);
      }
      this.terminalLog('system', key, '终端已清空');
    });
  }

  // ---- 性能监控设置（弹窗，仅此维护监控参数） ----

  isMonitorSettingsOpen() {
    const overlay = document.getElementById('monitor-settings-modal');
    return !!(overlay && !overlay.classList.contains('hidden'));
  }

  openMonitorSettings() {
    const server = this.activeServerObject();
    if (!server) {
      this.showToast('请先切换到具体服务器视图', 'error');
      return;
    }
    const m = server.monitor || {};
    document.getElementById('ms-server-label').textContent =
      `正在配置：${server.server_label || server.server_name}`;
    document.getElementById('ms-enabled').checked = !!m.enabled;
    document.getElementById('ms-interval').value = m.interval ?? 60;
    document.getElementById('ms-retention').value = m.retention_days ?? 7;
    document.getElementById('ms-tps-command').value = (m.tps_command || 'auto').trim() || 'auto';
    document.getElementById('ms-ping-host').value = m.ping_host || '';
    document.getElementById('ms-ping-port').value = m.ping_port ?? 25565;
    // 默认展示项由后端持久化（刷新/重开后仍生效）
    document.getElementById('ms-default-tab').value =
      (m.default_tab === 'latency') ? 'latency' : 'tps';
    // 实时采集频率（秒）：随设置持久化，1~60
    document.getElementById('ms-realtime-interval').value =
      (m.realtime_interval >= 1 && m.realtime_interval <= 60) ? m.realtime_interval : 5;
    // 自动刷新间隔与互通终端加载天数属面板偏好（非监控参数），已迁至
    // 「功能设置」面板维护，这里不再填充
    // 清除按钮提示当前已采集条数，明确删除范围
    const clearBtn = document.getElementById('ms-clear-data');
    if (clearBtn) {
      clearBtn.title =
        `删除「${server.server_label || server.server_name}」已采集的 ${m.sample_count ?? 0} 条监控数据（不可恢复）`;
    }
    document.getElementById('monitor-settings-modal').classList.remove('hidden');
  }

  // 通用二次确认弹窗：页面运行在受限 iframe，window.confirm 会被浏览器静默
  // 拦截返回 false（无 modals 权限），二次确认必须页面内自绘。返回 Promise；
  // 同一时刻只允许一个待决确认，重复调用复用已打开的弹窗。
  confirmDialog(title, message, confirmText = '确定') {
    if (this._confirmWaiter) return this._confirmWaiter.promise;
    // 不能在 new Promise 的 executor 内引用 promise 变量：此刻它处于暂时性
    // 死区，求值即抛 ReferenceError。而 Promise 构造函数会捕获 executor 的
    // 异常并把 promise 置为 rejected（不向外抛出），于是 _confirmWaiter 永远
    // 保持 undefined —— 弹窗能显示，但点确定/取消时 confirmDialogDismiss 的
    // 守卫 `if (!_confirmWaiter) return` 直接返回，按钮就成了死按钮。
    let resolveFn;
    const promise = new Promise((resolve) => { resolveFn = resolve; });
    this._confirmWaiter = { promise, resolve: resolveFn };
    document.getElementById('cf-title').textContent = title;
    document.getElementById('cf-message').textContent = message;
    const okBtn = document.getElementById('cf-ok');
    okBtn.textContent = confirmText;
    okBtn.onclick = () => this.confirmDialogDismiss(true);
    document.getElementById('confirm-modal').classList.remove('hidden');
    return promise;
  }

  confirmDialogDismiss(result) {
    if (!this._confirmWaiter) return;
    document.getElementById('confirm-modal').classList.add('hidden');
    this._confirmWaiter.resolve(result);
    this._confirmWaiter = null;
  }

  // 清除当前服务器已采集的全部监控数据（设置弹窗「🗑 清除采集数据」）。
  // 删除不可恢复：前端二次确认 + 后端返回删除条数，成功后整体刷新
  async clearMonitorData() {
    const server = this.activeServerObject();
    if (!server) {
      this.showToast('请先切换到具体服务器视图', 'error');
      return;
    }
    const m = server.monitor || {};
    const count = m.sample_count || 0;
    const label = server.server_label || server.server_name;
    if (!(await this.confirmDialog(
      '🗑 清除监控数据',
      `确定清除「${label}」已采集的全部 ${count} 条监控数据？\n` +
      '此操作不可恢复（历史 TPS / 延迟曲线与统计将清空）；\n' +
      '监控设置保留，采样任务会从零重新开始。',
      '清除'
    ))) return;
    try {
      const resp = await this.apiPost(
        `monitor/${encodeURIComponent(server.server_name)}/clear`, {});
      if (resp && resp.success) {
        this.showToast(`已清除「${label}」${resp.removed ?? count} 条监控数据`, 'success');
        this.monitorSeriesCache.delete(server.server_name);
        // 关闭设置弹窗并整体刷新：卡片摘要 / 监控面板计数与曲线立即归零
        this.closeMonitorSettings();
        await this.refreshAll(true);
      } else {
        this.showToast('清除失败: ' + ((resp && resp.error) || '未知错误'), 'error');
      }
    } catch (e) {
      this.showToast('清除失败: ' + (e.message || '网络错误'), 'error');
    }
  }

  closeMonitorSettings() {
    document.getElementById('monitor-settings-modal').classList.add('hidden');
  }

  async saveMonitorSettings() {
    const server = this.activeServerObject();
    if (!server) return;
    const enabled = document.getElementById('ms-enabled').checked;
    const interval = parseInt(document.getElementById('ms-interval').value, 10);
    const retentionDays = parseInt(document.getElementById('ms-retention').value, 10);
    const rawTps = document.getElementById('ms-tps-command').value.trim();
    // 空 / auto → auto（按服务端类型自动选择）；否则使用显式指令
    const tpsCommand = (rawTps === '' || rawTps.toLowerCase() === 'auto') ? 'auto' : rawTps;
    const pingHost = document.getElementById('ms-ping-host').value.trim();
    const pingPort = parseInt(document.getElementById('ms-ping-port').value, 10);
    // 实时采集频率（秒）：1~60，越界时按当前值提交（后端会防御钳制）
    const realtimeInterval = parseInt(
      document.getElementById('ms-realtime-interval').value, 10);
    // 自动刷新间隔与互通终端加载天数属面板偏好（非监控参数），
    // 已迁至「功能设置」面板维护，这里不再读取
    // 默认展示项：提交后端持久化（存 settings.json），不依赖浏览器存储；
    // 立即切到所选子页面，刷新/重开面板后按该默认恢复
    const defaultTab = document.getElementById('ms-default-tab').value === 'latency' ? 'latency' : 'tps';
    this.monitorTab = defaultTab;
    this._defaultTabServer = server.server_name;

    // 后端会做防御式钳制，这里提前提示常见误配
    if (!Number.isFinite(interval) || interval < 10) {
      this.showToast('采集间隔最小 10 秒', 'error');
      return;
    }
    if (!Number.isFinite(retentionDays) || retentionDays < 1) {
      this.showToast('保留天数至少 1 天', 'error');
      return;
    }
    if (!Number.isFinite(pingPort) || pingPort < 1 || pingPort > 65535) {
      this.showToast('延迟探测端口需在 1-65535 之间', 'error');
      return;
    }

    const saveBtn = document.getElementById('ms-save');
    saveBtn.disabled = true;
    try {
      const resp = await this.apiPost('monitor/settings', {
        server_name: server.server_name,
        enabled,
        interval,
        retention_days: retentionDays,
        tps_command: tpsCommand,
        ping_host: pingHost,
        ping_port: pingPort,
        default_tab: defaultTab,
        realtime_interval: realtimeInterval,
      });
      // 保存后立即用新频率（若正在实时模式，下一轮按新频率排期）
      if (Number.isFinite(realtimeInterval) &&
          realtimeInterval >= 1 && realtimeInterval <= 60) {
        this.realtimeInterval = realtimeInterval;
      }
      // 自动刷新间隔 / 实时频率后端已持久化，无需 localStorage——刷新/换设备
      // 都以后端为准（自动刷新间隔现由「功能设置」面板维护）
      this.syncAutoRefreshLabel();
      this.closeMonitorSettings();
      this.showToast(`监控设置已保存：${enabled ? '已启用' : '已停用'}（间隔 ${resp?.settings?.interval ?? interval}s）`, 'success');
      // 设置变更后重拉服务器摘要（含最新开关/采样），面板与卡片同步刷新
      this.monitorSeriesCache.delete(server.server_name);
      await this.refreshAll(true);
    } catch (e) {
      this.showToast('保存监控设置失败: ' + (e.message || '网络错误'), 'error');
    } finally {
      saveBtn.disabled = false;
    }
  }

  async sampleMonitorNow() {
    const server = this.activeServerObject();
    if (!server) return;
    const btn = document.getElementById('monitor-sample-btn');
    if (btn) btn.disabled = true;
    try {
      await this.apiPost(`monitor/${encodeURIComponent(server.server_name)}/sample`, {});
      this.monitorSeriesCache.delete(server.server_name);
      await this.refreshAll(true);
      this.showToast('已采集一次（TPS + 延迟）', 'success');
    } catch (e) {
      this.showToast('立即采集失败: ' + (e.message || '网络错误'), 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // 实时模式：采样循环由**后端常驻任务**驱动（与正常周期同架构，间隔取
  // realtime_interval，1~60 秒——后端任务保证连续性，不依赖浏览器）。
  // 前端只负责按同一频率拉取最近 60 秒 series 并重绘曲线；setInterval
  // 周期刷新（拉取挂起时 loadMonitorSeries 自带 8s 超时与防重入锁，
  // 下一轮照常执行，不堆积）
  startRealtime() {
    // 代次递增：旧刷新链（若 await 挂起中）完成后因 round 不匹配自然退出，
    // 新链从本轮开始——重切实时按钮永远能重启，避免哑火
    this._realtimeRound = (this._realtimeRound || 0) + 1;
    const round = this._realtimeRound;
    // 刷新频率与后端采样频率一致（realtime_interval，1~60 秒）
    const server = this.activeServerObject();
    const ri = server && server.monitor && server.monitor.realtime_interval;
    if (Number.isFinite(ri) && ri >= 1 && ri <= 60) {
      this.realtimeInterval = ri;
    }
    this.realtimeActive = true;
    this.monitorRange = 'realtime';
    this.realtimeRefresh(round); // 立即刷一轮
    this.realtimeTimer = setInterval(
      () => this.realtimeRefresh(round),
      Math.max(500, this.realtimeInterval * 1000)
    );
  }

  stopRealtime() {
    this.realtimeActive = false;
    this._realtimeRound = (this._realtimeRound || 0) + 1; // 作废进行中的刷新链
    if (this.realtimeTimer) {
      clearInterval(this.realtimeTimer);
      this.realtimeTimer = null;
    }
    // 恢复普通状态行（renderMonitorPanel 也会重刷，这里兜底切换 range 的场景）
    const server = this.activeServerObject();
    if (server) this.updateMonitorStatusLine(server);
  }

  async realtimeRefresh(round = this._realtimeRound) {
    if (round !== this._realtimeRound) return; // 已被 stop/重启，退出旧链
    const server = this.activeServerObject();
    if (!server || !(server.monitor && server.monitor.enabled)) {
      // 当前无可刷新的服务器（全局视图/监控关闭）：停止实时展示
      if (this.realtimeActive) this.stopRealtime();
      return;
    }
    this.monitorSeriesCache.delete(server.server_name);
    await this.loadMonitorSeries(server.server_name); // 内部自带超时与 catch
    if (round === this._realtimeRound) this._renderRealtimeStatus(server);
  }

  // 实时模式状态行：🔴 指示 + 采样频率 + 最近采样时间（采样由后端任务
  // 驱动，时间从最近一次 series 的最后点推断）
  _renderRealtimeStatus(server) {
    const line = document.getElementById('monitor-status-line');
    if (!line) return;
    const parts = [];
    const freq = Math.max(1, Math.min(60, this.realtimeInterval || 5));
    parts.push(`<span class="monitor-dot on"></span> 实时采集（后端驱动）每 ${freq} 秒一次`);
    if (server) {
      const payload = this.monitorSeriesCache.get(server.server_name);
      let lastTs = 0;
      if (payload && payload.series) {
        for (const key of Object.keys(payload.series)) {
          const pts = (payload.series[key] && payload.series[key].points) || [];
          if (pts.length && pts[pts.length - 1].ts > lastTs) {
            lastTs = pts[pts.length - 1].ts;
          }
        }
      }
      if (lastTs) parts.push(`最近采样 ${this.formatClock(lastTs)}`);
    }
    line.innerHTML = parts.join(' · ');
  }

  showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
}

// 页面加载启动
document.addEventListener('DOMContentLoaded', () => {
  const app = new DashboardApp();
  app.init();
});
