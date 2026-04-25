// =============================================================================
// app.js — AI Sysadmin Agent Web UI v3.0
// WebSocket chat, panel lateral, confirmaciones y notificaciones
// =============================================================================

'use strict';

// ── Configuración ─────────────────────────────────────────────
const WS_CHAT_URL   = `ws://${location.host}/ws/chat`;
const WS_EVENTS_URL = `ws://${location.host}/ws/events`;
const SYSTEM_POLL_MS = 15000;

// ── Estado ────────────────────────────────────────────────────
let chatWs        = null;
let eventsWs      = null;
let isConnected   = false;
let isBusy        = false;
let pendingConfirm = null;     // { confirm_id, resolve }
let currentTypingEl = null;    // elemento de texto activo (streaming)
let currentAgentMsg = null;    // mensaje del agente activo

// ── DOM ───────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const els = {
  chatMessages:    $('chat-messages'),
  chatInput:       $('chat-input'),
  btnSend:         $('btn-send'),
  btnTask:         $('btn-task'),
  btnMode:         $('btn-mode'),
  modeLabel:       $('mode-label'),
  connectionDot:   $('connection-dot'),
  motorSelect:     $('motor-select'),
  appVersion:      $('app-version'),
  // System
  cpuBar:    $('cpu-bar'),   cpuValue:  $('cpu-value'),
  ramBar:    $('ram-bar'),   ramValue:  $('ram-value'),
  diskBar:   $('disk-bar'),  diskValue: $('disk-value'),
  uptimeLoad: $('uptime-load'),
  btnRefreshSystem: $('btn-refresh-system'),
  // Sentinel
  sentinelBadge:   $('sentinel-status-badge'),
  sentinelSummary: $('sentinel-summary'),
  sentinelLast:    $('sentinel-last-update'),
  btnSentinelStart: $('btn-sentinel-start'),
  btnSentinelStop:  $('btn-sentinel-stop'),
  btnSentinelLog:   $('btn-sentinel-log'),
  // Memory
  memBadge:      $('memory-status-badge'),
  memStats:      $('memory-stats-text'),
  memSearchInput: $('memory-search-input'),
  btnMemSearch:  $('btn-memory-search'),
  memResults:    $('memory-search-results'),
  btnMemPurge:   $('btn-memory-purge'),
  // Modals
  confirmModal:  $('confirm-modal'),
  confirmCmd:    $('confirm-command'),
  confirmTitle:  $('confirm-title'),
  btnConfirmYes: $('btn-confirm-yes'),
  btnConfirmNo:  $('btn-confirm-no'),
  logModal:      $('log-modal'),
  logContent:    $('log-content'),
  btnLogClose:   $('btn-log-close'),
  toastContainer: $('toast-container'),
};

// =============================================================================
// WebSocket — Chat
// =============================================================================

function connectChat() {
  setConnectionState('connecting');
  chatWs = new WebSocket(WS_CHAT_URL);

  chatWs.onopen = () => {
    setConnectionState('connected');
    addSystemMessage('Conectado al agente.', 'info');
  };

  chatWs.onclose = () => {
    setConnectionState('disconnected');
    isConnected = false;
    isBusy = false;
    updateSendBtn();
    setTimeout(connectChat, 3000);
  };

  chatWs.onerror = () => setConnectionState('disconnected');

  chatWs.onmessage = e => {
    let evt;
    try { evt = JSON.parse(e.data); } catch { return; }
    handleChatEvent(evt);
  };
}

function connectEvents() {
  eventsWs = new WebSocket(WS_EVENTS_URL);
  eventsWs.onmessage = e => {
    let evt;
    try { evt = JSON.parse(e.data); } catch { return; }
    if (evt.type === 'sentinel_alert') {
      showToast(`🔍 Centinela: ${evt.resumen}`, evt.nivel === 'ok' ? 'info' : 'alert');
    }
    if (evt.type === 'status_update') applyStatus(evt.status);
    if (evt.type === 'ping') eventsWs.send('pong');
  };
  eventsWs.onclose = () => setTimeout(connectEvents, 5000);
}

// =============================================================================
// Manejo de eventos del agente
// =============================================================================

function handleChatEvent(evt) {
  switch (evt.type) {
    case 'connected':
      isConnected = true;
      applyStatus(evt.status);
      break;

    case 'thinking':
      ensureAgentMessage();
      appendThinking(evt.text);
      break;

    case 'tool_call':
      ensureAgentMessage();
      appendToolCall(evt.tool, evt.display, evt.args);
      break;

    case 'tool_confirm':
      showConfirmModal(evt.confirm_id, evt.tool, evt.display);
      break;

    case 'tool_result':
      updateToolResult(evt.tool, evt.result, evt.cancelled);
      break;

    case 'text':
      ensureAgentMessage();
      appendFinalText(evt.text);
      finishAgentMessage();
      break;

    case 'text_chunk':
      ensureAgentMessage();
      appendTextChunk(evt.text);
      break;

    case 'task_start':
      ensureAgentMessage();
      appendTaskHeader(evt.tarea);
      break;

    case 'task_result':
      ensureAgentMessage();
      appendFinalText(evt.result);
      finishAgentMessage();
      break;

    case 'info':
      addSystemMessage(markdownToHtml(evt.text), 'info');
      break;

    case 'error':
      addSystemMessage(escapeHtml(evt.text), 'error');
      finishAgentMessage();
      break;

    case 'mode_change':
      applyModeChange(evt.seguro);
      addSystemMessage(`Modo: ${evt.text}`, evt.seguro ? 'success' : 'info');
      break;

    case 'motor_change':
      addSystemMessage(`Motor: ${evt.text}`, 'success');
      break;

    case 'sentinel_update':
      updateSentinelBadge(evt.corriendo);
      addSystemMessage(evt.text, evt.corriendo ? 'success' : 'info');
      break;

    case 'sentinel_status': {
      const txt = `Centinela: ${evt.corriendo ? '🟢 corriendo' : '🔴 detenido'} | ${evt.nivel} | ${evt.resumen}`;
      addSystemMessage(txt, 'info');
      updateSentinelPanel(evt);
      break;
    }

    case 'memory_stats':
      updateMemoryPanel(evt.stats);
      break;

    case 'web_result':
      ensureAgentMessage();
      appendFinalText(`**Búsqueda:** ${evt.query}\n\n${evt.result}`);
      finishAgentMessage();
      break;

    case 'engines': {
      const names = Object.entries(evt.motores)
        .map(([k, v]) => `${k === evt.activo ? '✓ ' : ''}${v.nombre}`)
        .join('\n');
      addSystemMessage(`Motores disponibles:\n${names}`, 'info');
      break;
    }

    case 'done':
      isBusy = false;
      updateSendBtn();
      scrollToBottom();
      break;
  }
}

// =============================================================================
// Construcción de mensajes en el DOM
// =============================================================================

function addUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'msg user';
  div.innerHTML = `
    <div class="msg-avatar">👤</div>
    <div class="msg-body">
      <div class="msg-role">Tú</div>
      <div class="msg-text">${escapeHtml(text).replace(/\n/g, '<br>')}</div>
    </div>`;
  els.chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

function ensureAgentMessage() {
  if (!currentAgentMsg) {
    currentAgentMsg = document.createElement('div');
    currentAgentMsg.className = 'msg agent';
    currentAgentMsg.innerHTML = `
      <div class="msg-avatar">🤖</div>
      <div class="msg-body">
        <div class="msg-role">Agente</div>
        <div class="msg-text agent-content"></div>
      </div>`;
    els.chatMessages.appendChild(currentAgentMsg);
  }
}

function getAgentContent() {
  return currentAgentMsg?.querySelector('.agent-content');
}

function appendThinking(text) {
  const c = getAgentContent(); if (!c) return;
  const p = document.createElement('p');
  p.className = 'thinking-text';
  p.style.cssText = 'color:var(--text-muted);font-style:italic;font-size:13px';
  p.textContent = `💭 ${text}`;
  c.appendChild(p);
  scrollToBottom();
}

function appendTaskHeader(tarea) {
  const c = getAgentContent(); if (!c) return;
  const d = document.createElement('div');
  d.className = 'task-header';
  d.innerHTML = `<span>🎯</span> Tarea autónoma: ${escapeHtml(tarea)}`;
  c.appendChild(d);
  scrollToBottom();
}

function appendToolCall(tool, display, args) {
  const c = getAgentContent(); if (!c) return;
  const id = `tc-${Date.now()}-${Math.random().toString(36).slice(2,6)}`;
  const icon = toolIcon(tool);
  const card = document.createElement('div');
  card.className = 'tool-card'; card.id = id;
  card.innerHTML = `
    <div class="tool-header" onclick="toggleToolResult('${id}')">
      <span class="tool-icon">${icon}</span>
      <span class="tool-name">${escapeHtml(tool)}</span>
      <span class="tool-display" title="${escapeHtml(display)}">${escapeHtml(display)}</span>
      <span class="tool-status running" id="${id}-status">⏳</span>
    </div>
    <div class="tool-result hidden" id="${id}-result"></div>`;
  card.dataset.tool = tool;
  c.appendChild(card);
  scrollToBottom();
}

function updateToolResult(tool, result, cancelled) {
  // Buscar la última tool card de esta herramienta sin resultado aún
  const cards = els.chatMessages.querySelectorAll(`.tool-card[data-tool="${tool}"]`);
  let card = null;
  for (const c of [...cards].reverse()) {
    const resEl = c.querySelector('.tool-result');
    if (resEl && resEl.classList.contains('hidden')) { card = c; break; }
  }
  if (!card) return;
  const id = card.id;
  const statusEl = $(`${id}-status`);
  const resultEl = $(`${id}-result`);
  if (statusEl) {
    statusEl.className = `tool-status ${cancelled ? 'error' : 'done'}`;
    statusEl.textContent = cancelled ? '✕' : '✓';
  }
  if (resultEl) {
    resultEl.textContent = result || '';
    resultEl.classList.remove('hidden');
  }
  scrollToBottom();
}

function appendFinalText(text) {
  const c = getAgentContent(); if (!c) return;
  // Eliminar indicador de typing si existe
  const typing = c.querySelector('.typing-indicator');
  if (typing) typing.remove();
  const div = document.createElement('div');
  div.innerHTML = markdownToHtml(text);
  c.appendChild(div);
  currentTypingEl = null;
  scrollToBottom();
}

function appendTextChunk(chunk) {
  const c = getAgentContent(); if (!c) return;
  if (!currentTypingEl) {
    currentTypingEl = document.createElement('span');
    c.appendChild(currentTypingEl);
  }
  currentTypingEl.textContent += chunk;
  scrollToBottom();
}

function finishAgentMessage() {
  if (currentTypingEl) {
    // Renderizar el texto acumulado como markdown
    const text = currentTypingEl.textContent;
    const div = document.createElement('div');
    div.innerHTML = markdownToHtml(text);
    currentTypingEl.replaceWith(div);
    currentTypingEl = null;
  }
  currentAgentMsg = null;
}

function addSystemMessage(html, type = 'info') {
  const div = document.createElement('div');
  div.className = `msg ${type}`;
  div.innerHTML = `
    <div class="msg-avatar">${type === 'error' ? '⚠' : type === 'success' ? '✓' : 'ℹ'}</div>
    <div class="msg-body">
      <div class="msg-text">${html}</div>
    </div>`;
  els.chatMessages.appendChild(div);
  scrollToBottom();
}

// =============================================================================
// Envío de mensajes
// =============================================================================

function sendMessage(text) {
  if (!text.trim() || !isConnected || isBusy) return;
  addUserMessage(text);
  isBusy = true;
  updateSendBtn();
  currentAgentMsg = null;
  currentTypingEl = null;
  chatWs.send(JSON.stringify({ type: 'message', text }));
}

function handleSend() {
  const text = els.chatInput.value.trim();
  if (!text) return;
  els.chatInput.value = '';
  autoResize(els.chatInput);
  sendMessage(text);
}

// =============================================================================
// Modal de confirmación
// =============================================================================

function showConfirmModal(confirmId, tool, display) {
  els.confirmTitle.textContent = `Confirmar: ${tool}`;
  els.confirmCmd.textContent   = display;
  els.confirmModal.classList.remove('hidden');

  pendingConfirm = { confirm_id: confirmId };

  els.btnConfirmYes.onclick = () => resolveConfirm(true);
  els.btnConfirmNo.onclick  = () => resolveConfirm(false);
  els.confirmModal.querySelector('.modal-backdrop').onclick = () => resolveConfirm(false);
}

function resolveConfirm(approved) {
  if (!pendingConfirm) return;
  chatWs.send(JSON.stringify({
    type: 'confirm_result',
    confirm_id: pendingConfirm.confirm_id,
    approved,
  }));
  els.confirmModal.classList.add('hidden');
  pendingConfirm = null;
}

// =============================================================================
// Panel de estado
// =============================================================================

function applyStatus(status) {
  if (!status) return;
  // Motor select
  const motores = status.motores_disponibles || {};
  els.motorSelect.innerHTML = '';
  for (const [key, meta] of Object.entries(motores)) {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = meta.nombre;
    if (key === status.motor_key) opt.selected = true;
    els.motorSelect.appendChild(opt);
  }
  // Modo
  applyModeChange(status.require_confirmation);
  // Memoria
  const mem = status.memoria || {};
  updateMemoryPanel(mem.stats || {});
  els.memBadge.textContent = mem.activa ? 'Activa' : 'Inactiva';
  els.memBadge.className = `status-badge ${mem.activa ? 'running' : 'stopped'}`;
  // Sentinel
  updateSentinelBadge(status.sentinel?.corriendo);
}

function applyModeChange(seguro) {
  els.btnMode.className = `mode-btn ${seguro ? 'safe' : 'auto'}`;
  els.modeLabel.textContent = seguro ? 'Seguro' : 'Autónomo';
}

function updateSentinelBadge(corriendo) {
  els.sentinelBadge.textContent = corriendo ? 'Corriendo' : 'Detenido';
  els.sentinelBadge.className = `status-badge ${corriendo ? 'running' : 'stopped'}`;
}

function updateSentinelPanel(data) {
  if (!data) return;
  updateSentinelBadge(data.corriendo);
  els.sentinelSummary.textContent = data.resumen || 'Sin datos.';
  if (data.ultima_actualizacion) {
    const d = new Date(data.ultima_actualizacion * 1000);
    els.sentinelLast.textContent = `Último ciclo: ${d.toLocaleTimeString()}`;
  }
}

function updateMemoryPanel(stats) {
  if (!stats || !stats.total && stats.total !== 0) return;
  const total = stats.total ?? '–';
  const max   = stats.max_entries ?? '–';
  const kb    = stats.db_size_kb ?? 0;
  const mb    = kb > 1024 ? `${(kb/1024).toFixed(1)} MB` : `${kb} KB`;
  els.memStats.textContent = `${total} / ${max} recuerdos · ${mb}`;
}

// =============================================================================
// Métricas del sistema
// =============================================================================

async function fetchSystemMetrics() {
  try {
    const r = await fetch('/api/system');
    if (!r.ok) return;
    const d = await r.json();
    applySystemMetrics(d);
  } catch {}
}

function applySystemMetrics(m) {
  setBar(els.cpuBar,  els.cpuValue,  m.cpu_percent,  '%');
  setBar(els.ramBar,  els.ramValue,  m.ram_percent,  '%',
    m.ram_used_mb && m.ram_total_mb
      ? `${Math.round(m.ram_used_mb)}/${Math.round(m.ram_total_mb)} MB`
      : null);
  setBar(els.diskBar, els.diskValue, m.disk_percent, '%',
    m.disk_used_gb && m.disk_total_gb
      ? `${m.disk_used_gb}/${m.disk_total_gb} GB`
      : null);

  let extra = '';
  if (m.uptime_seconds) extra += `Uptime: ${formatUptime(m.uptime_seconds)}`;
  if (m.load_avg && m.load_avg.length) extra += ` · Load: ${m.load_avg[0].toFixed(2)}`;
  els.uptimeLoad.textContent = extra;
}

function setBar(barEl, valEl, pct, suffix = '', labelOverride = null) {
  if (pct === null || pct === undefined) { valEl.textContent = '–'; return; }
  const p = Math.min(100, Math.max(0, pct));
  barEl.style.width = `${p}%`;
  barEl.className = `bar-fill ${barEl.className.split(' ')[0]} ${p >= 90 ? 'crit' : p >= 70 ? 'warn' : ''}`.trim();
  valEl.textContent = labelOverride || `${Math.round(p)}${suffix}`;
}

function formatUptime(secs) {
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

// =============================================================================
// Búsqueda de memoria
// =============================================================================

async function searchMemory() {
  const q = els.memSearchInput.value.trim();
  if (!q) return;
  try {
    const r = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}&top_k=5`);
    const d = await r.json();
    renderMemoryResults(d.results || []);
  } catch {
    showToast('Error al buscar en memoria', 'alert');
  }
}

function renderMemoryResults(results) {
  els.memResults.innerHTML = '';
  els.memResults.classList.remove('hidden');
  if (!results.length) {
    els.memResults.innerHTML = '<div class="memory-result-item">Sin resultados.</div>';
    return;
  }
  for (const r of results) {
    const item = document.createElement('div');
    item.className = 'memory-result-item';
    item.innerHTML = `
      <div>
        <span class="mem-sim">${(r.similitud*100).toFixed(0)}%</span>
        <span class="mem-tipo"> · ${r.tipo || '?'}</span>
      </div>
      <div class="mem-resumen">${escapeHtml(r.resumen_corto || r.contenido?.slice(0,80) || '–')}</div>`;
    item.onclick = () => {
      const cmd = `/memory search ${r.id}`;
      sendMessage(`memory_get_details: ID ${r.id}`);
    };
    els.memResults.appendChild(item);
  }
}

// =============================================================================
// Sentinel — Log
// =============================================================================

async function showSentinelLog() {
  try {
    const r = await fetch('/api/sentinel/log?lines=100');
    const d = await r.json();
    els.logContent.textContent = (d.lines || []).join('\n') || 'Log vacío.';
    els.logModal.classList.remove('hidden');
  } catch {
    showToast('Error al cargar el log', 'alert');
  }
}

// =============================================================================
// Toast notificaciones
// =============================================================================

function showToast(msg, type = 'info', durationMs = 4000) {
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  els.toastContainer.appendChild(t);
  setTimeout(() => t.remove(), durationMs);
}

// =============================================================================
// Helpers
// =============================================================================

function scrollToBottom() {
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function setConnectionState(state) {
  els.connectionDot.className = `connection-dot ${state}`;
  if (state === 'connected') isConnected = true;
  if (state === 'disconnected') isConnected = false;
  updateSendBtn();
}

function updateSendBtn() {
  els.btnSend.disabled = !isConnected || isBusy;
}

function autoResize(ta) {
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
}

function toolIcon(tool) {
  const icons = {
    execute_local_bash: '⚡',
    web_search:         '🔎',
    read_file:          '📂',
    write_file:         '✏️',
    execute_ssh:        '🔌',
    wake_on_lan:        '🌐',
    memory_search:      '🧠',
    memory_get_details: '🧠',
  };
  return icons[tool] || '🔧';
}

function toggleToolResult(id) {
  const el = $(`${id}-result`);
  if (el) el.classList.toggle('hidden');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function markdownToHtml(text) {
  if (!text) return '';
  let h = escapeHtml(text);
  // Code blocks
  h = h.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code>${code.trim()}</code></pre>`);
  // Inline code
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  h = h.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Italic
  h = h.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // Headers
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm,  '<h2>$1</h2>');
  h = h.replace(/^# (.+)$/gm,   '<h1>$1</h1>');
  // Lists
  h = h.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  h = h.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  // Numbered lists
  h = h.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Line breaks (double newline = paragraph)
  h = h.replace(/\n\n+/g, '</p><p>');
  h = h.replace(/\n/g, '<br>');
  if (!h.startsWith('<')) h = `<p>${h}</p>`;
  return h;
}

// =============================================================================
// Event listeners
// =============================================================================

els.btnSend.addEventListener('click', handleSend);

els.chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

els.chatInput.addEventListener('input', () => autoResize(els.chatInput));

els.btnTask.addEventListener('click', () => {
  const input = els.chatInput;
  if (!input.value.startsWith('/task ')) input.value = '/task ' + input.value;
  input.focus();
});

els.btnMode.addEventListener('click', () => sendMessage('/auto'));

els.motorSelect.addEventListener('change', e => {
  const motor = e.target.value;
  fetch('/api/switch', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ motor }),
  })
  .then(r => r.json())
  .then(d => showToast(d.text || `Motor: ${motor}`, 'success'))
  .catch(() => showToast('Error al cambiar motor', 'alert'));
});

els.btnRefreshSystem.addEventListener('click', fetchSystemMetrics);

els.btnSentinelStart.addEventListener('click', () => sendMessage('/sentinel start'));
els.btnSentinelStop.addEventListener('click',  () => sendMessage('/sentinel stop'));
els.btnSentinelLog.addEventListener('click',   showSentinelLog);

els.btnLogClose.addEventListener('click', () => els.logModal.classList.add('hidden'));
els.logModal.querySelector('.modal-backdrop').addEventListener('click', () =>
  els.logModal.classList.add('hidden'));

els.btnMemSearch.addEventListener('click', searchMemory);
els.memSearchInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') searchMemory();
});

els.btnMemPurge.addEventListener('click', async () => {
  const r = await fetch('/api/memory/purge', { method: 'POST' });
  const d = await r.json();
  showToast(`Purga: ${d.eliminadas ?? 0} entradas eliminadas`, 'success');
});

document.querySelectorAll('.quick-cmd').forEach(btn => {
  btn.addEventListener('click', () => {
    const cmd = btn.dataset.cmd;
    if (cmd) sendMessage(cmd);
  });
});

// =============================================================================
// Init
// =============================================================================

(async function init() {
  connectChat();
  connectEvents();
  await fetchSystemMetrics();
  setInterval(fetchSystemMetrics, SYSTEM_POLL_MS);

  // Actualizar status del sentinel al cargar
  try {
    const r = await fetch('/api/status');
    const s = await r.json();
    applyStatus(s);
    if (s.sentinel) updateSentinelPanel(s.sentinel);
  } catch {}
})();
