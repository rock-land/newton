const statusEl = document.getElementById('api-status');
const dbEl = document.getElementById('db-status');
const uptimeEl = document.getElementById('uptime');
const generatedAtEl = document.getElementById('generated-at');
const dataSourceOverallEl = document.getElementById('data-source-overall');
const brokersBody = document.getElementById('brokers-body');
const instrumentsBody = document.getElementById('instruments-body');

const instrumentTabsEl = document.getElementById('instrument-tabs');
const selectedInstrumentEl = document.getElementById('selected-instrument');
const candlesBody = document.getElementById('candles-body');
const indicatorsBody = document.getElementById('indicators-body');
const candleSourceEl = document.getElementById('candles-source');
const indicatorSourceEl = document.getElementById('indicators-source');

const INSTRUMENTS = [
  { id: 'EUR_USD', label: 'EUR/USD' },
  { id: 'BTC_USD', label: 'BTC/USD' },
];

const state = {
  selectedInstrument: INSTRUMENTS[0].id,
  candlesByInstrument: {},
  indicatorsByInstrument: {},
};

const API_BASE = window.location.port === '4173' ? 'http://127.0.0.1:8000' : '';

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function statusPill(value) {
  if (value === true || value === 'healthy') return '<span class="pill pill-ok">OK</span>';
  if (value === 'degraded') return '<span class="pill pill-warn">DEGRADED</span>';
  return '<span class="pill pill-bad">DOWN</span>';
}

function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h}h ${m}m ${s}s`;
}

function renderRows(tbody, rows) {
  tbody.innerHTML = rows.join('');
}

function formatNumber(value, decimals = 5) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return Number(value).toFixed(decimals);
}

function formatMaybeNumber(value, decimals = 2) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return Number(value).toFixed(decimals);
}

function relativeTimeIso(stepsBack, minutesPerStep) {
  const dt = new Date(Date.now() - stepsBack * minutesPerStep * 60000);
  return dt.toISOString();
}

function buildMockCandles(instrumentId) {
  const base = instrumentId === 'EUR_USD' ? 1.0835 : 52000;
  const volatility = instrumentId === 'EUR_USD' ? 0.0012 : 180;
  return Array.from({ length: 8 }).map((_, index) => {
    const drift = (index - 4) * volatility * 0.15;
    const open = base + drift;
    const close = open + (Math.sin(index) * volatility * 0.2);
    const high = Math.max(open, close) + volatility * 0.25;
    const low = Math.min(open, close) - volatility * 0.25;
    return {
      time: relativeTimeIso(8 - index, 60),
      open,
      high,
      low,
      close,
      volume: instrumentId === 'EUR_USD' ? 1000 + index * 130 : 14 + index * 2.3,
      interval: '1h',
    };
  });
}

function buildMockIndicators(instrumentId) {
  const rsiBase = instrumentId === 'EUR_USD' ? 52 : 58;
  return [
    { interval: '1m', rsi: rsiBase - 6, ema20: instrumentId === 'EUR_USD' ? 1.0831 : 51920, sma50: instrumentId === 'EUR_USD' ? 1.0828 : 51880, macd: 0.12 },
    { interval: '5m', rsi: rsiBase - 2, ema20: instrumentId === 'EUR_USD' ? 1.0834 : 52040, sma50: instrumentId === 'EUR_USD' ? 1.0830 : 51990, macd: 0.21 },
    { interval: '1h', rsi: rsiBase + 3, ema20: instrumentId === 'EUR_USD' ? 1.0838 : 52170, sma50: instrumentId === 'EUR_USD' ? 1.0833 : 52100, macd: 0.34 },
  ];
}

async function tryFetchJson(urls) {
  for (const url of urls) {
    try {
      const res = await fetch(apiUrl(url), { cache: 'no-store' });
      if (!res.ok) continue;
      return await res.json();
    } catch (_error) {
      // Try next candidate endpoint.
    }
  }
  return null;
}

function normalizeCandles(payload) {
  const rows = Array.isArray(payload) ? payload : payload?.data || payload?.candles || payload?.items || [];
  return rows.map((row) => ({
    time: row.time || row.ts || row.timestamp,
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
    volume: row.volume,
    interval: row.interval || row.tf || '1h',
  }));
}

function normalizeIndicators(payload) {
  const rows = Array.isArray(payload) ? payload : payload?.data || payload?.indicators || payload?.items || [];
  if (!rows.length) return [];

  const grouped = new Map();
  for (const row of rows) {
    const key = `${row.interval || '1h'}|${row.time}`;
    if (!grouped.has(key)) {
      grouped.set(key, {
        interval: row.interval || '1h',
        time: row.time,
        rsi: null,
        ema20: null,
        sma50: null,
        macd: null,
      });
    }
    const target = grouped.get(key);
    const featureKey = row.feature_key || '';
    const value = row.value;

    if (featureKey.startsWith('rsi:')) target.rsi = value;
    if (featureKey.includes('macd:') && featureKey.endsWith(':line')) target.macd = value;
    if (featureKey.includes('ema:period=20')) target.ema20 = value;
    if (featureKey.includes('sma:period=50')) target.sma50 = value;
  }

  const sorted = Array.from(grouped.values()).sort((a, b) => new Date(b.time) - new Date(a.time));
  return sorted.slice(0, 8);
}

async function loadDataForInstrument(instrumentId) {
  const start = encodeURIComponent(relativeTimeIso(24 * 30, 60)); // 30-day lookback
  const candlesPayload = await tryFetchJson([
    `/api/v1/ohlcv/${instrumentId}?interval=1h&start=${start}&limit=8`,
  ]);

  const featuresPayload = await tryFetchJson([
    `/api/v1/features/${instrumentId}?interval=1h&start=${start}&limit=200`,
  ]);

  const apiCandles = candlesPayload ? normalizeCandles(candlesPayload) : [];
  const apiIndicators = featuresPayload ? normalizeIndicators(featuresPayload) : [];

  const useApiCandles = apiCandles.length > 0;
  const useApiIndicators = apiIndicators.length > 0;

  const candles = useApiCandles ? apiCandles : buildMockCandles(instrumentId);
  const indicators = useApiIndicators ? apiIndicators : buildMockIndicators(instrumentId);

  state.candlesByInstrument[instrumentId] = {
    source: useApiCandles ? 'API' : (candlesPayload ? 'Mock (API empty)' : 'Mock'),
    rows: candles,
  };
  state.indicatorsByInstrument[instrumentId] = {
    source: useApiIndicators ? 'API' : (featuresPayload ? 'Mock (API empty)' : 'Mock'),
    rows: indicators,
  };
}

function renderInstrumentTabs() {
  instrumentTabsEl.innerHTML = INSTRUMENTS.map((instrument) => {
    const activeClass = instrument.id === state.selectedInstrument ? 'tab-btn active' : 'tab-btn';
    return `<button class="${activeClass}" data-instrument="${instrument.id}">${instrument.label}</button>`;
  }).join('');

  instrumentTabsEl.querySelectorAll('button[data-instrument]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.selectedInstrument = btn.dataset.instrument;
      renderInstrumentTabs();
      renderDataViewer();
    });
  });
}

function renderDataViewer() {
  const selected = INSTRUMENTS.find((x) => x.id === state.selectedInstrument) || INSTRUMENTS[0];
  selectedInstrumentEl.textContent = selected.label;

  const candleData = state.candlesByInstrument[selected.id] || { source: '-', rows: [] };
  const indicatorData = state.indicatorsByInstrument[selected.id] || { source: '-', rows: [] };

  candleSourceEl.textContent = candleData.source;
  indicatorSourceEl.textContent = indicatorData.source;

  const allCandleSources = INSTRUMENTS.map((i) => state.candlesByInstrument[i.id]?.source).filter(Boolean);
  const allIndicatorSources = INSTRUMENTS.map((i) => state.indicatorsByInstrument[i.id]?.source).filter(Boolean);
  const allSources = [...allCandleSources, ...allIndicatorSources];
  if (!allSources.length) {
    dataSourceOverallEl.textContent = '-';
  } else if (allSources.every((s) => s === 'API')) {
    dataSourceOverallEl.innerHTML = '<span class="pill pill-ok">API</span>';
  } else if (allSources.every((s) => s === 'Mock')) {
    dataSourceOverallEl.innerHTML = '<span class="pill pill-bad">MOCK</span>';
  } else {
    dataSourceOverallEl.innerHTML = '<span class="pill pill-warn">MIXED</span>';
  }

  const candleRows = candleData.rows.map((row) => (
    `<tr>
      <td>${new Date(row.time).toLocaleString()}</td>
      <td>${formatNumber(row.open, selected.id === 'EUR_USD' ? 5 : 2)}</td>
      <td>${formatNumber(row.high, selected.id === 'EUR_USD' ? 5 : 2)}</td>
      <td>${formatNumber(row.low, selected.id === 'EUR_USD' ? 5 : 2)}</td>
      <td>${formatNumber(row.close, selected.id === 'EUR_USD' ? 5 : 2)}</td>
      <td>${formatMaybeNumber(row.volume, 2)}</td>
    </tr>`
  ));

  const indicatorRows = indicatorData.rows.map((row) => (
    `<tr>
      <td>${row.interval}</td>
      <td>${formatMaybeNumber(row.rsi, 2)}</td>
      <td>${formatNumber(row.ema20, selected.id === 'EUR_USD' ? 5 : 2)}</td>
      <td>${formatNumber(row.sma50, selected.id === 'EUR_USD' ? 5 : 2)}</td>
      <td>${formatMaybeNumber(row.macd, 2)}</td>
    </tr>`
  ));

  renderRows(candlesBody, candleRows);
  renderRows(indicatorsBody, indicatorRows);
}

async function refresh() {
  try {
    const start = performance.now();
    const response = await fetch(apiUrl('/api/v1/health'), { cache: 'no-store' });
    const latency = Math.round(performance.now() - start);
    if (!response.ok) {
      throw new Error(`Health request failed: ${response.status}`);
    }

    const health = await response.json();

    statusEl.innerHTML = `${statusPill(health.status)} <span class="muted">(${latency}ms)</span>`;
    dbEl.innerHTML = statusPill(health.db);
    uptimeEl.textContent = formatDuration(health.uptime_seconds || 0);
    generatedAtEl.textContent = new Date(health.generated_at).toLocaleString();

    const brokerRows = Object.entries(health.brokers).map(([name, info]) => {
      const responseMs = info.last_response_ms == null ? '-' : String(info.last_response_ms);
      return `<tr><td>${name}</td><td>${statusPill(info.connected)}</td><td>${responseMs}</td></tr>`;
    });

    const instrumentRows = Object.entries(health.instruments).map(([name, info]) => {
      const age = info.last_candle_age_seconds == null ? 'n/a' : String(info.last_candle_age_seconds);
      const reconciled = info.reconciled;
      const reconciledCell = reconciled == null ? '-' : statusPill(reconciled);
      return `<tr><td>${name}</td><td>${age}</td><td>${reconciledCell}</td></tr>`;
    });

    renderRows(brokersBody, brokerRows);
    renderRows(instrumentsBody, instrumentRows);
  } catch (error) {
    statusEl.innerHTML = '<span class="pill pill-bad">ERROR</span>';
    dbEl.textContent = '-';
    uptimeEl.textContent = '-';
    generatedAtEl.textContent = String(error);
  }

  await Promise.all(INSTRUMENTS.map((instrument) => loadDataForInstrument(instrument.id)));
  renderDataViewer();
}

renderInstrumentTabs();
refresh();
setInterval(refresh, 15000);
