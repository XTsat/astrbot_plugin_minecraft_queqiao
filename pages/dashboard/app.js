/**
 * Minecraft QueQiao Plugin - Dashboard Logic
 */

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

class DashboardApp {
  constructor() {
    this.bridge = window.AstrBotPluginPage || null;
    this.servers = [];
    this.stats = null;
    this.refreshInterval = null;
    this.isRefreshing = false;
    this.activeServerTab = 'all'; // 当前激活的服务器视图标签（'all' 或 server_name）
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
    // 互通终端加载天数（面板级偏好）：0=全部保留分片，1~30=最近 N 天；
    // 默认 2（今天+昨天）。权威数据在后端 panel_prefs.json（长期存储），
    // 此处 localStorage 仅作首屏启动缓存，init 会异步拉取后端值覆盖。
    // 插件页面运行在受限 iframe，localStorage 可能被沙箱禁止，
    // 一律 try/catch 兜底，失败时退回默认值，绝不阻断页面启动
    let savedDays = 2;
    try {
      savedDays = parseInt(localStorage.getItem('queqiao_terminal_days') || '2', 10);
    } catch (e) {
      savedDays = 2;
    }
    this.terminalDays = (Number.isFinite(savedDays) && savedDays >= 0 && savedDays <= 30)
      ? savedDays : 2;
  }

  async init() {
    this.initThemeSync();
    this.initDefaultIcon();
    this.bindEvents();
    this.bindTerminalActions();
    this.bindMonitorActions();

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
    // 自动刷新默认关闭（防止对鹊桥持续轮询刷屏）；是否开启以开关为准
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
    document.getElementById('btn-refresh')?.addEventListener('click', () => {
      // 手动刷新强制重新探测一次 RCON（自动轮询不强制，避免向未开启
      // RCON 的鹊桥端反复发 send_rcon_command、在 MC 控制台刷报错）
      this.refreshAll(false, true);
    });

    const autoToggle = document.getElementById('auto-refresh-toggle');
    autoToggle?.addEventListener('change', (e) => {
      this.setupAutoRefresh(e.target.checked);
    });
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
      this.renderOverview();
      this.renderServers();
      await this.renderTerminal();
      this.renderMonitorPanel();
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
    if (m && Number.isFinite(m.auto_refresh_interval)) {
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
      if (Number.isFinite(prefs.terminal_days) &&
          prefs.terminal_days >= 0 && prefs.terminal_days <= 30) {
        this.terminalDays = prefs.terminal_days;
        // 已进入单服视图时按新天数重拉终端（内部已捕获异常）
        const curKey = this.activeServerTab;
        if (curKey && curKey !== 'all') {
          const stream = this.ensureTerminalStream(curKey);
          if (stream) {
            stream.innerHTML = '';
            stream.dataset.rendered = '0';
            stream.dataset.lastDate = '';
            this.loadTerminalLogs(curKey, stream);
          }
        }
      }
    } catch (e) {
      console.warn('拉取面板偏好失败:', e);
    }
  }

  // 当前服务器视图对应的服务器对象；全局视图返回 null
  activeServerObject() {
    if (this.activeServerTab === 'all') return null;
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

    if (!this.servers.length) {
      container.innerHTML = `
        <div class="empty-box">
          <p>⚠️ 暂未配置或加载到任何 Minecraft 服务器</p>
          <p style="margin-top: 8px; font-size: 12px;">请在插件配置中添加 MC 服务器并确保 enabled 为 true</p>
        </div>`;
      return;
    }

    // 单服务器视图只展示该服务器卡片；全局视图展示全部
    const list = activeServer ? [activeServer] : this.servers;
    container.innerHTML = list.map(server => this.buildServerCardHtml(server)).join('');
    this.bindServerCardActions();
    // 玩家进出/卡片高度变化后立即同步右侧监控面板高度（等一帧布局结算，
    // 避免 innerHTML 重建后读到旧高度）
    requestAnimationFrame(() => this.syncMonitorPanelHeight());
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

    // 内存进度条
    let memoryHtml = '<span class="detail-val">--</span>';
    if (status && status.memory_total > 0) {
      const percent = Math.min(100, Math.max(0, status.memory_percentage || 0));
      let stateClass = 'normal';
      if (percent > 85) stateClass = 'danger';
      else if (percent > 65) stateClass = 'warning';

      memoryHtml = `
        <div class="progress-wrap">
          <div class="progress-header">
            <span class="detail-val">${status.memory_usage_text || '--'}</span>
          </div>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill ${stateClass}" style="width: ${percent}%;"></div>
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
            <span class="badge ${isConnected ? 'badge-online' : 'badge-offline'}">
              <span class="pulse-dot"></span>
              ${isConnected ? '在线' : '未连接'}
            </span>
            <span class="badge badge-mode">${server.is_reverse ? '反向监听' : '正向连接'}</span>
            <span class="badge ${rconBadgeClass}">${rconBadgeText}</span>
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
            <span class="detail-val">${status?.cpu_cores ? `${status.cpu_cores} 核 (负载 ${status.system_load.toFixed(2)})` : '--'}</span>
          </div>
          <div class="detail-item" style="grid-column: span 2;">
            <span class="detail-label">内存占用</span>
            ${memoryHtml}
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

    // 原激活视图已不存在（服务器被移除）则回退全局视图
    const valid = this.activeServerTab === 'all' ||
      this.servers.some(s => s.server_name === this.activeServerTab);
    if (!valid) this.activeServerTab = 'all';

    // 仅同步高亮，实际渲染交由 refreshAll 统一执行
    this.activateServerTab(this.activeServerTab, { render: false });
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

  // 切换服务器视图：统计卡片、服务器面板与终端一并跟随
  activateServerTab(key, { render = true } = {}) {
    this.activeServerTab = key;
    document.querySelectorAll('#server-tabs .server-tab').forEach(b => {
      b.classList.toggle('active', b.dataset.view === key);
    });

    if (render) {
      this.renderOverview();
      this.renderServers();
      // 异步拉取后端历史日志；内部已捕获异常，无需等待
      this.renderTerminal();
      this.renderMonitorPanel();
    }
    // 自动刷新间隔/实时频率为每台服务器独立持久化的设置：切换视图后
    // 重读该服（或回落第一台）的后端值，顶部按钮与状态行实时跟随
    this.syncMonitorFreqFromBackend();
  }

  // 全局视图下对某台服务器执行操作时，切到该服视图以展示终端反馈
  focusServer(serverName) {
    if (serverName && this.activeServerTab === 'all') {
      this.activateServerTab(serverName);
    }
  }

  // ---- 互通终端 ----

  // 当前终端目标服务器：全局视图返回 null（终端整体隐藏）
  terminalServer() {
    return this.activeServerTab === 'all' ? null : this.activeServerTab;
  }

  // server_name → 显示名称（便于终端日志可读）
  terminalServerLabel(name) {
    const s = this.servers.find(item => item.server_name === name);
    return s ? (s.server_label || s.server_name) : name;
  }

  // 渲染互通终端：全局视图整体隐藏；单服务器视图显示该服务器的日志流。
  // 每次进入都做增量拉取并启动 4 秒轮询，新日志自动追加、实时可见
  async renderTerminal() {
    const panel = document.getElementById('terminal-panel');
    const key = this.activeServerTab;
    const isAll = key === 'all';

    if (panel) panel.classList.toggle('hidden', isAll);
    // 输入区可用性始终同步（全局视图无目标服务器，禁用输入）
    this.updateTerminalInputState();
    if (isAll) {
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

  // 从后端拉取某台服务器的持久化日志，只追加尚未渲染的新条目。
  // 请求带 5 秒超时保护：桥通道异常时降级跳过本次拉取，避免拖死整页刷新
  async loadTerminalLogs(key, stream) {
    try {
      const res = await Promise.race([
        this.apiGet('terminal_logs', { server: key, days: this.terminalDays }),
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

  // 终端仅在单服务器视图可用；全局视图隐藏面板并禁用输入
  updateTerminalInputState() {
    const isAll = this.activeServerTab === 'all';
    const input = document.getElementById('terminal-input');
    const bBtn = document.getElementById('terminal-broadcast');
    const cBtn = document.getElementById('terminal-cmd');
    if (input) {
      input.disabled = isAll;
      input.placeholder = '输入内容回车 = 广播；以 / 开头回车 = 执行指令 (如 /list)';
    }
    if (bBtn) bBtn.disabled = isAll;
    if (cBtn) cBtn.disabled = isAll;
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
      achievement: '🏆', command: '⌨',
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
    // 面板可见性只跟随视图（全局视图隐藏）；监控禁用不隐藏面板——
    // 否则面板内的「⚙ 设置」入口一并消失，无法再重新启用
    const isAll = this.activeServerTab === 'all';
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
    // 自动刷新间隔（秒）：随设置持久化，10~3600
    document.getElementById('ms-auto-refresh').value =
      (m.auto_refresh_interval >= 10 && m.auto_refresh_interval <= 3600)
        ? m.auto_refresh_interval : 10;
    // 互通终端加载天数：面板级偏好（后端 panel_prefs 长期存储 + localStorage 缓存），0=全部保留分片
    document.getElementById('ms-terminal-days').value = this.terminalDays;
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
    // 自动刷新间隔（秒）：10~3600，越界时按当前值提交（后端会防御钳制）
    const autoRefresh = parseInt(
      document.getElementById('ms-auto-refresh').value, 10);
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
        auto_refresh_interval: autoRefresh,
      });
      // 保存后立即用新频率（若正在实时模式，下一轮按新频率排期）
      if (Number.isFinite(realtimeInterval) &&
          realtimeInterval >= 1 && realtimeInterval <= 60) {
        this.realtimeInterval = realtimeInterval;
      }
      // 自动刷新间隔即时应用：若正在自动刷新，用新间隔重启定时器
      if (Number.isFinite(autoRefresh) &&
          autoRefresh >= 10 && autoRefresh <= 3600) {
        this.autoRefreshInterval = autoRefresh;
        this.setupAutoRefresh(
          document.getElementById('auto-refresh-toggle')?.checked || false
        );
      }
      // 自动刷新间隔 / 实时频率后端已按服务器持久化（settings.json），
      // 无需 localStorage——刷新/换设备都以后端为准
      this.syncAutoRefreshLabel();
      // 互通终端加载天数：0=全部保留分片，1~30=最近 N 天；保存后立即重拉当前终端
      const terminalDays = parseInt(
        document.getElementById('ms-terminal-days').value, 10);
      if (Number.isFinite(terminalDays) && terminalDays >= 0 && terminalDays <= 30) {
        this.terminalDays = terminalDays;
        // 长期存储在后端 panel_prefs.json（权威）；localStorage 仅作启动缓存
        try {
          localStorage.setItem('queqiao_terminal_days', String(terminalDays));
        } catch (e) {
          // 受限 iframe 下 localStorage 不可用时忽略（仅本次会话生效）
        }
        try {
          await this.apiPost('panel/prefs', { terminal_days: terminalDays });
        } catch (e) {
          console.warn('保存面板偏好失败:', e);
        }
        const curKey = this.activeServerTab;
        if (curKey && curKey !== 'all') {
          const stream = this.ensureTerminalStream(curKey);
          stream.innerHTML = '';
          stream.dataset.rendered = '0';
          stream.dataset.lastDate = '';
          await this.loadTerminalLogs(curKey, stream);
        }
      }
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
