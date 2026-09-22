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
  }

  async init() {
    this.initThemeSync();
    this.bindEvents();
    this.bindTerminalActions();

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

    await this.refreshAll();
    this.setupAutoRefresh(true);
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
      this.refreshAll();
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
      this.refreshInterval = setInterval(() => {
        this.refreshAll(true);
      }, 10000);
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

  async refreshAll(silent = false) {
    if (this.isRefreshing) return;
    this.isRefreshing = true;

    const refreshBtn = document.getElementById('btn-refresh');
    if (refreshBtn && !silent) {
      refreshBtn.classList.add('loading');
      refreshBtn.disabled = true;
    }

    try {
      // 1. 获取服务器列表（包含附带的实时 status 与 players）
      const serversData = await this.apiGet('servers');
      this.servers = serversData?.servers || [];

      // 2. 获取统计数据
      try {
        this.stats = await this.apiGet('stats');
      } catch (e) {
        console.warn('Failed to fetch stats:', e);
      }

      // 3. 渲染界面（输入框与终端输出独立于服务器卡片区，不会被重建打断）
      this.renderServerTabs();
      this.renderOverview();
      this.renderServers();
      await this.renderTerminal();
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
  }

  buildServerCardHtml(server) {
    const status = server.status || null;
    const players = server.players || null;
    const isConnected = server.connected;

    // 服务器图标：仅当服务端返回合法的 data:image 图标时才使用（标准 SLP
    // favicon 即 base64 data URL）。鹊桥有时会回传需鉴权的代理 URL 或错误
    // JSON（如 {"status":"error","message":"未授权"}），这类无法作为 <img> 源，
    // 一律回退默认图标。
    const faviconRaw = status && status.favicon;
    const faviconSrc = (typeof faviconRaw === 'string' && faviconRaw.startsWith('data:image/'))
      ? faviconRaw
      : './default-server-icon.png';

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

    return `
      <div class="server-card ${isConnected ? 'connected' : 'disconnected'}" id="server-card-${escapeHtml(server.server_name)}">
        <div class="server-card-header">
          <div class="server-title-group">
            <img class="server-favicon" src="${escapeHtml(faviconSrc)}" alt="" onerror="this.onerror=null;this.src='./default-server-icon.png';">
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
    }
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

  // 渲染互通终端：全局视图整体隐藏；单服务器视图显示该服务器的日志流，
  // 首次进入时从后端拉取持久化历史（网页未打开期间的事件也已记录）
  async renderTerminal() {
    const panel = document.getElementById('terminal-panel');
    const key = this.activeServerTab;
    const isAll = key === 'all';

    if (panel) panel.classList.toggle('hidden', isAll);
    // 输入区可用性始终同步（全局视图无目标服务器，禁用输入）
    this.updateTerminalInputState();
    if (isAll) return;

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
    // 仅首次进入（流为空）时从后端拉取历史日志
    if (stream.children.length === 0) {
      await this.loadTerminalLogs(key, stream);
    }
    // 无任何历史时给出操作提示
    if (stream.children.length === 0) {
      this.terminalLog('system', key, '互通终端就绪 — 输入内容回车=广播，以 / 开头回车=执行指令');
    }
    this.updateTerminalInputState();
  }

  // 从后端拉取某台服务器的持久化日志并渲染到流
  async loadTerminalLogs(key, stream) {
    try {
      const res = await this.apiGet('terminal_logs', { server: key });
      // 拉取期间用户已切换视图，丢弃过期结果
      if (this.activeServerTab !== key) return;
      const logs = res?.logs || [];
      for (const entry of logs) {
        this.appendTerminalLine(
          stream,
          entry.type || 'system',
          key,
          entry.message || '',
          entry.time || '--:--:--'
        );
      }
    } catch (e) {
      console.warn('拉取终端日志失败:', e);
    }
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

  // 向指定日志流追加一行并滚动到底部（纯 DOM 操作）
  appendTerminalLine(stream, type, key, message, time) {
    const tagMap = {
      broadcast: '📢', cmd: '⚡', out: '↳', error: '✖', system: 'ℹ',
      chat: '💬', join: '🟢', quit: '🔴', death: '💀',
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
    stream.scrollTop = stream.scrollHeight;
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

  bindTerminalActions() {
    const input = document.getElementById('terminal-input');
    if (input) {
      // 回车智能识别：/ 开头 = 执行指令，否则 = 广播
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
    document.getElementById('terminal-clear')?.addEventListener('click', async () => {
      const key = this.activeServerTab;
      if (!key || key === 'all') return;
      const stream = this.ensureTerminalStream(key);
      stream.innerHTML = '';
      try {
        // 同步清除后端持久化日志，仅此操作会删除历史
        await this.apiPost('terminal_logs/clear', { server: key });
      } catch (e) {
        console.warn('清除后端终端日志失败:', e);
      }
      this.terminalLog('system', key, '终端已清空');
    });
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
