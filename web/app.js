// =============================================================================
// app.js — AI Sysadmin Agent Web UI v4.0
// WebSocket chat, panel lateral, confirmaciones y notificaciones
// =============================================================================

'use strict';

// ── Configuración ─────────────────────────────────────────────
const WS_CHAT_URL   = `ws://${location.host}/ws/chat`;
const WS_EVENTS_URL = `ws://${location.host}/ws/events`;
const SYSTEM_POLL_MS = 15000;
const SENTINEL_POLL_MS = 30000;

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
  btnCancel:       $('btn-cancel'),
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
  // Model card
  modelCurrent:     $('model-current'),
  modelList:        $('model-list'),
  btnRefreshModels: $('btn-refresh-models'),
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

// Modo de permisos actual
let currentMode = 'smart'; // smart | safe | auto


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
    if (evt.type === 'sentinel_status_update') {
      updateSentinelBadge(evt.corriendo);
      updateSentinelPanel(evt);
    }
    if (evt.type === 'memory_consolidated') {
      showToast(`🧠 Memoria auto-consolidada: ${evt.guardados} fragmento(s)`, 'success', 3000);
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
      addSystemMessage(markdownToHtml(evt.text), 'error');
      finishAgentMessage();
      isBusy = false;
      updateSendBtn();
      break;

    case 'mode_change':
      applyModeChange(evt.mode || (evt.seguro ? 'safe' : 'auto'));
      addSystemMessage(evt.text, 'success');
      break;

    case 'motor_change':
      addSystemMessage(`Motor: ${evt.text}`, 'success');
      break;

    case 'model_change':
      addSystemMessage(`🧠 ${evt.text}`, 'success');
      // Refrescar lista de modelos para marcar el nuevo activo
      fetchLMStudioModels();
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
      hideTypingIndicator();
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
  showTypingIndicator();
  chatWs.send(JSON.stringify({ type: 'message', text }));
}

function handleSend() {
  const text = els.chatInput.value.trim();
  if (!text) return;
  els.chatInput.value = '';
  autoResize(els.chatInput);

  if (pendingConfirm) {
    const t = text.toLowerCase();
    if (['y', 'yes', 'ok', 's', 'si', 'sí'].includes(t)) {
      addUserMessage(text);
      resolveConfirm(true);
      showToast('Comando aprobado ✅', 'success', 2000);
      return;
    }
    if (['n', 'no', 'cancelar', 'cancel'].includes(t)) {
      addUserMessage(text);
      resolveConfirm(false);
      showToast('Comando cancelado ❌', 'info', 2000);
      return;
    }
  }

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
  // Mostrar feedback inmediato en el chat
  const msg = approved ? '✅ Comando aprobado — ejecutando...' : '❌ Ejecución cancelada por el usuario.';
  addSystemMessage(msg, approved ? 'success' : 'info');
  if (approved) showTypingIndicator();
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
  // Modo de permisos
  const mode = status.permission_mode || (status.require_confirmation ? 'safe' : 'auto');
  applyModeChange(mode);
  currentMode = mode;
  // Memoria
  const mem = status.memoria || {};
  updateMemoryPanel(mem.stats || {});
  els.memBadge.textContent = mem.activa ? 'Activa' : 'Inactiva';
  els.memBadge.className = `status-badge ${mem.activa ? 'running' : 'stopped'}`;
  // Sentinel
  updateSentinelBadge(status.sentinel?.corriendo);
}

function applyModeChange(mode) {
  // Soporte para llamadas legacy (bool) y nuevas (string)
  if (typeof mode === 'boolean') mode = mode ? 'safe' : 'auto';
  currentMode = mode;
  const configs = {
    smart: { cls: 'smart', label: '🧠 Inteligente', title: 'Modo Inteligente: confirma solo comandos destructivos' },
    safe:  { cls: 'safe',  label: '🛡 Seguro',       title: 'Modo Seguro: confirma todos los comandos' },
    auto:  { cls: 'auto',  label: '⚡ Autónomo',     title: 'Modo Autónomo: ejecuta sin confirmación' },
  };
  const cfg = configs[mode] || configs.smart;
  els.btnMode.className = `mode-btn ${cfg.cls}`;
  els.modeLabel.textContent = cfg.label;
  els.btnMode.title = cfg.title;
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
// Selector de modelos LM Studio
// =============================================================================

let _currentModelId = null;
let _pendingModelId = null;  // Modelo elegido por el usuario, pendiente de confirmación
let _allModels = [];         // Lista unificada (LM Studio live + guardados)

async function fetchLMStudioModels() {
  try {
    // Consultar en paralelo: modelos live de LM Studio + lista guardada
    const [liveResp, savedResp] = await Promise.all([
      fetch('/api/lmstudio/models').then(r => r.json()).catch(() => ({ ok: false, chat_models: [] })),
      fetch('/api/models').then(r => r.json()).catch(() => ({ models: [] })),
    ]);

    const liveModels  = liveResp.chat_models || [];
    const savedModels = savedResp.models || [];

    // Unificar: live primero, luego guardados que no estén ya en la lista live
    const liveSet  = new Set(liveModels);
    const combined = [...liveModels, ...savedModels.filter(m => !liveSet.has(m))];
    _allModels = combined;

    // Si el backend reporta un modelo activo, sincronizar
    const reportedCurrent = liveResp.current;
    renderModelList({ current: reportedCurrent, chat_models: combined, live_models: liveModels });
  } catch {
    if (els.modelList) els.modelList.innerHTML = '<div style="font-size:11px;color:var(--text-muted)">LM Studio no disponible</div>';
  }
}

function renderModelList(data) {
  if (!els.modelList) return;

  const reported = data.current;
  // Si el pending ya fue confirmado por LM Studio, limpiarlo
  if (_pendingModelId && reported && reported === _pendingModelId) {
    _pendingModelId = null;
  }
  // Modelo efectivo: pending > reported > null
  const effectiveCurrent = _pendingModelId || reported || _currentModelId;
  _currentModelId = effectiveCurrent;

  // Label del modelo activo
  if (els.modelCurrent) {
    if (_pendingModelId) {
      els.modelCurrent.textContent = `⏳ ${_pendingModelId.split('/').pop()} (cargando...)`;
    } else if (effectiveCurrent) {
      const short = effectiveCurrent.split('/').pop();
      els.modelCurrent.textContent = `✓ ${short}`;
    } else {
      els.modelCurrent.textContent = 'Autodetectar';
    }
  }

  const models  = data.chat_models || [];
  const liveSet = new Set(data.live_models || models);
  els.modelList.innerHTML = '';

  if (!models.length) {
    els.modelList.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:4px">Sin modelos disponibles</div>';
    return;
  }

  for (const modelId of models) {
    const isPending = modelId === _pendingModelId;
    const isCurrent = modelId === effectiveCurrent;
    const isLive    = liveSet.has(modelId);
    const item = document.createElement('div');
    item.className = `model-item${isCurrent ? ' active' : ''}${isPending ? ' loading' : ''}`;
    item.title = `${modelId}${isLive ? ' (en LM Studio)' : ' (guardado)'}`;
    item.style.cursor = 'pointer';

    const badge    = isPending  ? '<span class="model-loading-badge" title="Cargando en VRAM…">⏳</span>' : '';
    const liveDot  = isLive     ? '<span class="model-live-dot" title="Disponible en LM Studio"></span>' : '<span class="model-saved-dot" title="Guardado localmente"></span>';

    item.innerHTML = `
      <div class="model-item-inner">
        ${liveDot}
        <span class="model-name">${modelId}</span>
        ${badge}
        <button class="model-del-btn" title="Eliminar de lista guardada" data-model="${modelId}">x</button>
      </div>`;

    // Click en todo el item (excepto el botón eliminar) cambia el modelo
    item.addEventListener('click', (e) => {
      if (e.target.closest('.model-del-btn')) return;
      switchModel(modelId);
    });
    item.querySelector('.model-del-btn').addEventListener('click', async (e) => {
      e.stopPropagation();
      await deleteSavedModel(modelId);
    });

    els.modelList.appendChild(item);
  }
}

async function switchModel(modelId) {
  if (modelId === _pendingModelId) {
    showToast(`Ya está cargando ${modelId.split('/').pop()}…`, 'info', 2000);
    return;
  }
  _pendingModelId = modelId;
  // Re-renderizar inmediatamente con el pending
  renderModelList({ current: _currentModelId, chat_models: _allModels, live_models: _allModels });
  showToast(`⏳ Cambiando a ${modelId.split('/').pop()}… (puede tardar si carga desde disco)`, 'info', 5000);
  try {
    const r = await safeFetch('/api/lmstudio/model', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ model_id: modelId }),
    });
    const d = await r.json();
    if (d.ok) {
      _currentModelId = modelId;
      _pendingModelId = null;
      showToast(`✅ ${d.text}  — el historial se mantiene`, 'success');
      fetchLMStudioModels();
    } else {
      _pendingModelId = null;
      showToast(`❌ ${d.text}`, 'alert');
      fetchLMStudioModels();
    }
  } catch {
    _pendingModelId = null;
    showToast('Error al cambiar modelo', 'alert');
    fetchLMStudioModels();
  }
}

async function addSavedModel() {
  const input = document.getElementById('model-add-input');
  const modelId = input ? input.value.trim() : '';
  if (!modelId) { showToast('Ingresá un identificador de modelo', 'info', 2000); return; }
  try {
    const r = await fetch('/api/models/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ model_id: modelId }),
    });
    const d = await r.json();
    if (d.ok) {
      showToast(`✅ ${d.text}`, 'success');
      if (input) input.value = '';
      fetchLMStudioModels();
    } else {
      showToast(`❌ ${d.text}`, 'alert');
    }
  } catch {
    showToast('Error al agregar modelo', 'alert');
  }
}

async function deleteSavedModel(modelId) {
  try {
    const r = await fetch(`/api/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' });
    const d = await r.json();
    if (d.ok) {
      showToast(`🗑 ${d.text}`, 'info');
      fetchLMStudioModels();
    } else {
      showToast(`❌ ${d.text}`, 'alert');
    }
  } catch {
    showToast('Error al eliminar modelo', 'alert');
  }
}



// =============================================================================
// Métricas del sistema
// =============================================================================

async function fetchSystemMetrics() {
  try {
    const r = await safeFetch('/api/system');
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
    const r = await safeFetch(`/api/memory/search?q=${encodeURIComponent(q)}&top_k=5`);
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
    const r = await safeFetch('/api/sentinel/log?lines=100');
    const d = await r.json();
    els.logContent.textContent = (d.lines || []).join('\n') || 'Log vacío.';
    els.logModal.classList.remove('hidden');
  } catch {
    showToast('Error al cargar el log', 'alert');
  }
}

// =============================================================================
// Sentinel — Status polling & direct API control
// =============================================================================

async function fetchSentinelStatus() {
  try {
    const r = await safeFetch('/api/sentinel/status');
    if (!r.ok) return;
    const d = await r.json();
    updateSentinelBadge(d.corriendo);
    updateSentinelPanel(d);
  } catch {}
}

async function sentinelAction(accion) {
  try {
    const r = await safeFetch('/api/sentinel', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ accion }),
    });
    const d = await r.json();
    if (d.ok !== undefined) {
      showToast(d.text || `Centinela: ${accion}`, d.ok ? 'success' : 'alert');
    }
    // Refresh status immediately
    fetchSentinelStatus();
  } catch {
    showToast(`Error al ${accion} centinela`, 'alert');
  }
}

// =============================================================================
// Memory — Save/Consolidate
// =============================================================================

async function saveMemory() {
  try {
    showToast('⏳ Consolidando memoria...', 'info', 2000);
    const r = await safeFetch('/api/memory/consolidate', { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      showToast(`✅ ${d.text}`, 'success');
    } else {
      showToast(`❌ ${d.error || 'Error al consolidar'}`, 'alert');
    }
  } catch {
    showToast('Error al guardar memoria', 'alert');
  }
}

// =============================================================================
// safeFetch — Wrapper global para manejar errores HTTP con toast
// =============================================================================

async function safeFetch(url, options = {}) {
  try {
    const response = await fetch(url, options);
    if (!response.ok && response.status >= 400) {
      // Solo mostrar toast para errores de servidor, no para 404 silenciosos
      if (response.status >= 500) {
        showToast(`⚠️ Error del servidor (${response.status})`, 'alert', 4000);
      } else if (response.status === 422) {
        showToast('⚠️ Error de datos: revise la consola', 'alert', 4000);
        console.warn(`safeFetch ${url}: 422 Unprocessable Entity`);
      }
    }
    return response;
  } catch (err) {
    showToast(`🔌 Error de conexión con el servidor`, 'alert', 4000);
    throw err;
  }
}

// =============================================================================
// Collapsible panels
// =============================================================================

function initCollapsiblePanels() {
  const headers = document.querySelectorAll('.card-header.collapsible');
  const saved = JSON.parse(localStorage.getItem('panelState') || '{}');

  headers.forEach(header => {
    const panelKey = header.dataset.panel;
    const body = document.querySelector(`[data-panel-body="${panelKey}"]`);
    if (!body) return;

    // Restore saved state
    if (saved[panelKey] === false) {
      body.classList.add('collapsed');
      header.classList.add('collapsed-header');
    }

    header.addEventListener('click', (e) => {
      // Don't toggle if clicking a button inside the header
      if (e.target.closest('.icon-btn') || e.target.closest('.status-badge')) return;

      const isCollapsed = body.classList.toggle('collapsed');
      header.classList.toggle('collapsed-header', isCollapsed);

      // Save state
      const state = JSON.parse(localStorage.getItem('panelState') || '{}');
      state[panelKey] = !isCollapsed;
      localStorage.setItem('panelState', JSON.stringify(state));
    });
  });
}

// =============================================================================
// Typing indicator
// =============================================================================

let _typingIndicatorEl = null;

function showTypingIndicator() {
  hideTypingIndicator();
  _typingIndicatorEl = document.createElement('div');
  _typingIndicatorEl.className = 'msg agent typing-indicator-wrapper';
  _typingIndicatorEl.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div class="msg-body">
      <div class="msg-role">Agente</div>
      <div class="typing-dots"><span></span><span></span><span></span></div>
    </div>`;
  els.chatMessages.appendChild(_typingIndicatorEl);
  scrollToBottom();
}

function hideTypingIndicator() {
  if (_typingIndicatorEl) {
    _typingIndicatorEl.remove();
    _typingIndicatorEl = null;
  }
}

// Ocultar el indicador tan pronto como el agente empiece a emitir contenido real
const _origEnsureAgentMessage = ensureAgentMessage;
// Override para ocultar el indicador al crear el primer mensaje del agente
function ensureAgentMessage() {
  hideTypingIndicator();
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
  // Mostrar/ocultar botón cancelar
  if (els.btnCancel) {
    if (isBusy) {
      els.btnCancel.classList.remove('hidden');
    } else {
      els.btnCancel.classList.add('hidden');
    }
  }
}

function cancelCurrentRequest() {
  if (!isBusy) return;
  // Interrumpir reconectando el WebSocket — corta el streaming actual
  showToast('Cancelando respuesta…', 'info', 2000);
  addSystemMessage('❌ Respuesta cancelada por el usuario.', 'info');
  hideTypingIndicator();
  finishAgentMessage();
  isBusy = false;
  updateSendBtn();
  // Cerrar WS actual (se reconectará automáticamente vía onclose)
  if (chatWs) {
    chatWs.close();
    chatWs = null;
  }
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
if (els.btnCancel) els.btnCancel.addEventListener('click', cancelCurrentRequest);

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

els.btnMode.addEventListener('click', () => {
  // Ciclar modo via API REST (smart → safe → auto → smart)
  const next = { smart: 'safe', safe: 'auto', auto: 'smart' };
  const newMode = next[currentMode] || 'smart';
  fetch('/api/mode', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ mode: newMode }),
  })
  .then(r => r.json())
  .then(d => {
    if (d.ok) {
      applyModeChange(newMode);
      showToast(d.text, 'success');
    } else {
      showToast(d.text || 'Error', 'alert');
    }
  })
  .catch(() => showToast('Error al cambiar modo', 'alert'));
});

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
els.btnRefreshModels.addEventListener('click', fetchLMStudioModels);

// Agregar modelo guardado
const _btnModelAdd = document.getElementById('btn-model-add');
const _modelAddInput = document.getElementById('model-add-input');
if (_btnModelAdd) _btnModelAdd.addEventListener('click', addSavedModel);
if (_modelAddInput) _modelAddInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') addSavedModel();
});

els.btnSentinelStart.addEventListener('click', (e) => {
  e.stopPropagation(); sentinelAction('start');
});
els.btnSentinelStop.addEventListener('click', (e) => {
  e.stopPropagation(); sentinelAction('stop');
});
els.btnSentinelLog.addEventListener('click', (e) => {
  e.stopPropagation(); showSentinelLog();
});

els.btnLogClose.addEventListener('click', () => els.logModal.classList.add('hidden'));
els.logModal.querySelector('.modal-backdrop').addEventListener('click', () =>
  els.logModal.classList.add('hidden'));

els.btnMemSearch.addEventListener('click', searchMemory);
els.memSearchInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') searchMemory();
});

els.btnMemPurge.addEventListener('click', async () => {
  const r = await safeFetch('/api/memory/purge', { method: 'POST' });
  const d = await r.json();
  showToast(`Purga: ${d.eliminadas ?? 0} entradas eliminadas`, 'success');
});

const _btnMemSave = document.getElementById('btn-memory-save');
if (_btnMemSave) _btnMemSave.addEventListener('click', saveMemory);

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
  // Cargar modelos LM Studio al iniciar (incluye lista guardada y live)
  await fetchLMStudioModels();
  // Refrescar modelos cada 60s
  setInterval(fetchLMStudioModels, 60000);

  // Sentinel status polling
  await fetchSentinelStatus();
  setInterval(fetchSentinelStatus, SENTINEL_POLL_MS);

  // Obtener status del agente: modo, motor, modelo activo
  try {
    const r = await safeFetch('/api/status');
    const s = await r.json();
    applyStatus(s);
    if (s.sentinel) updateSentinelPanel(s.sentinel);
    // Sincronizar el modelo activo desde el backend
    if (s.model_id && !_currentModelId) {
      _currentModelId = s.model_id;
      // Re-renderizar con el modelo correcto marcado
      fetchLMStudioModels();
    }
  } catch {}

  // Init collapsible panels
  initCollapsiblePanels();
})();

