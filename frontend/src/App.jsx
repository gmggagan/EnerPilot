import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Dog, Home, RefreshCw, Sun, CloudRain, SunMedium, Radio, Users, Wifi, WifiOff } from 'lucide-react';
import { api } from './api.js';
import { ErrorBanner, Loading, Segmented, fmt } from './components/ui.jsx';
import MetricsView from './views/MetricsView.jsx';
import DispatchView from './views/DispatchView.jsx';
import PVView from './views/PVView.jsx';
import ComplianceView from './views/ComplianceView.jsx';

const TABS = [
  { id: 'metrics', label: 'Metrics' },
  { id: 'dispatch', label: 'Dispatch' },
  { id: 'pv', label: 'PV Sizing' },
  { id: 'compliance', label: 'Compliance' },
];

const WEATHER_ICON = { live: Radio, sunny_summer: Sun, cloudy_winter: CloudRain, mild_spring: SunMedium };

// Brand watermark: one faint logo per tab, placed where it suits that page.
// Fixed + pointer-events-none, so it stays in view while scrolling and never blocks clicks.
const WATERMARK = {
  metrics: { top: '50%', left: '50%', size: 'min(62vh, 520px)', transform: 'translate(-50%, -45%)', opacity: 0.07 },
  dispatch: { top: '100%', left: '100%', size: 'min(50vh, 400px)', transform: 'translate(-88%, -92%) rotate(-10deg)', opacity: 0.08 },
  pv: { top: '0%', left: '100%', size: 'min(46vh, 360px)', transform: 'translate(-92%, 18%) rotate(8deg)', opacity: 0.08 },
  compliance: { top: '100%', left: '0%', size: 'min(46vh, 360px)', transform: 'translate(8%, -95%) rotate(-6deg)', opacity: 0.08 },
};

function Watermark({ tab }) {
  const w = WATERMARK[tab] || WATERMARK.metrics;
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 lg:left-64 z-20 overflow-hidden">
      <img src="/logo-watermark.png" alt="" draggable="false"
        className="absolute max-w-none select-none transition-all duration-700 ease-out"
        style={{ top: w.top, left: w.left, width: w.size, height: w.size, transform: w.transform, opacity: w.opacity }} />
    </div>
  );
}

// --- MAIN ENERPILOT NETDATA-THEMED APPLICATION ---
export default function App() {
  const [occupancy, setOccupancy] = useState('auto');
  const [dogMode, setDogMode] = useState('auto');
  const [weatherKey, setWeatherKey] = useState('live');
  const [horizon, setHorizon] = useState('24h');
  const [pvCapacity, setPvCapacity] = useState(4);
  const [enforceRestWindow, setEnforceRestWindow] = useState(true);
  const [activeNav, setActiveNav] = useState('metrics');
  const [selIdx, setSelIdx] = useState(0);
  const [histDays, setHistDays] = useState(30);
  const [refreshKey, setRefreshKey] = useState(0);

  const [data, setData] = useState(null);
  const [pv, setPv] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [hist, setHist] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pvLoading, setPvLoading] = useState(false);
  const [error, setError] = useState(null);
  const reqId = useRef(0);
  const pvReqId = useRef(0);

  // Forecast + peaks + explanations + optimisation
  const loadDashboard = useCallback(async () => {
    const id = ++reqId.current;
    setLoading(true);
    try {
      const d = await api.dashboard({
        horizon, occupancy_mode: occupancy, dog_mode: dogMode, weather_scenario: weatherKey,
        pv_kwp: pvCapacity, enforce_rest_window: enforceRestWindow,
      });
      if (id === reqId.current) { setData(d); setError(null); }
    } catch (e) {
      if (id === reqId.current) setError(`Backend unavailable (${e.message}). Start it with: uvicorn main:app --port 8000`);
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, [horizon, occupancy, dogMode, weatherKey, pvCapacity, enforceRestWindow]);

  useEffect(() => { loadDashboard(); }, [loadDashboard, refreshKey]);

  // auto-retry while the backend is booting / training
  useEffect(() => {
    if (!error) return undefined;
    const t = setTimeout(() => setRefreshKey((k) => k + 1), 4000);
    return () => clearTimeout(t);
  }, [error]);

  // Annual PV simulation (Scenario A vs B)
  useEffect(() => {
    if (!data) return;
    const id = ++pvReqId.current;
    setPvLoading(true);
    api.pvSimulate({ capacity_kwp: pvCapacity, enforce_rest_window: enforceRestWindow })
      .then((r) => { if (id === pvReqId.current) setPv(r); })
      .catch(() => {})
      .finally(() => { if (id === pvReqId.current) setPvLoading(false); });
  }, [pvCapacity, enforceRestWindow, refreshKey, !!data]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!data) return;
    api.metrics().then(setMetrics).catch(() => {});
  }, [refreshKey, !!data]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!data) return;
    setHist(null);
    api.historical(histDays).then(setHist).catch(() => {});
  }, [histDays, refreshKey, !!data]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setSelIdx(0); }, [horizon]);

  // Appliance planner: AUTO (household routine) or MANUAL (user's own runs, remembered in this browser)
  const [planMode, setPlanMode] = useState(() => { try { return localStorage.getItem('ep.planMode') || 'auto'; } catch { return 'auto'; } });
  const [manualRuns, setManualRuns] = useState(() => { try { return JSON.parse(localStorage.getItem('ep.manualRuns') || '[]'); } catch { return []; } });
  const [manualOpt, setManualOpt] = useState(null);
  const [planBusy, setPlanBusy] = useState(false);
  const planReqId = useRef(0);
  useEffect(() => {
    try { localStorage.setItem('ep.planMode', planMode); localStorage.setItem('ep.manualRuns', JSON.stringify(manualRuns)); } catch { /* storage unavailable */ }
  }, [planMode, manualRuns]);
  useEffect(() => {
    const id = ++planReqId.current; // also invalidates any in-flight manual response
    if (planMode !== 'manual' || !data) { setManualOpt(null); setPlanBusy(false); return undefined; }
    setPlanBusy(true);
    const t = setTimeout(() => {
      api.planOptimize({
        horizon, occupancy_mode: occupancy, dog_mode: dogMode, weather_scenario: weatherKey,
        pv_kwp: pvCapacity, enforce_rest_window: enforceRestWindow, runs: manualRuns,
      })
        .then((r) => { if (id === planReqId.current) setManualOpt(r); })
        .catch((e) => { if (id === planReqId.current) setError(`Plan could not be optimised (${e.message})`); })
        .finally(() => { if (id === planReqId.current) setPlanBusy(false); });
    }, 350); // debounce while the user edits
    return () => clearTimeout(t);
  }, [planMode, manualRuns, data, horizon, occupancy, dogMode, weatherKey, pvCapacity, enforceRestWindow]);

  // every view sees the optimisation of the active plan
  const view = data && planMode === 'manual' && manualOpt ? { ...data, optimization: manualOpt } : data;

  const records = data?.forecast?.records || [];
  const sel = records[Math.min(selIdx, Math.max(records.length - 1, 0))];
  const schedule = view?.optimization?.schedule || [];
  const nextJob = (app) => schedule.find((s) => s.appliance === app);
  const jobVal = (app) => { const j = nextJob(app); return j ? `${j.shifted ? '→' : '@'} ${j.recommended_window.slice(0, 5)}` : 'not planned'; };
  const health = data?.health;
  const online = health && health.weather.source.startsWith('open-meteo');

  return (
    <div className="min-h-screen bg-[#0f1215] text-[#d1d5db] font-sans flex flex-col lg:flex-row antialiased selection:bg-[#0072f5]">

      {/* 1. LEFT NAVIGATION RAIL */}
      <aside className="w-full lg:w-64 bg-[#13161a] border-b lg:border-b-0 lg:border-r border-[#21262d] flex flex-col justify-between shrink-0 select-none lg:h-screen lg:sticky lg:top-0 lg:overflow-y-auto">
        <div>
          {/* Brand Header */}
          <div className="h-[72px] border-b border-[#21262d] px-3 flex items-center justify-between">
            <div className="flex items-center gap-2.5 min-w-0">
              <img src="/logo-mark.png" alt="EnerPilot Logo" className="w-12 h-12 object-contain shrink-0 drop-shadow-[0_0_10px_rgba(139,92,246,0.35)]" />
              <div className="min-w-0">
                <div className="font-bold text-white text-base tracking-tight leading-tight">ENERPILOT</div>
                <div className="text-[11px] text-[#6b7280] leading-tight whitespace-nowrap">Predict · Optimize · Save</div>
              </div>
            </div>
            <span className="text-xs bg-[#1e2329] text-[#9ca3af] px-1.5 py-0.5 rounded border border-[#2d333b] shrink-0">6.9kW</span>
          </div>

          {/* Quick Context Toggles */}
          <div className="p-3 border-b border-[#21262d] space-y-2.5">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-[#6b7280] block mb-1">Household Profile</span>
              <select value={occupancy} onChange={(e) => setOccupancy(e.target.value)}
                className="w-full bg-[#1c2127] border border-[#2d333b] text-white text-[13px] rounded px-2 py-1 outline-none focus:border-[#0072f5]">
                <option value="auto">Auto — typical hybrid week</option>
                <option value="both_wfh">Both Residents WFH</option>
                <option value="one_wfh">One Resident WFH</option>
                <option value="both_away">Both Away (Office)</option>
                <option value="weekend_travel">Travel Mode (nobody home)</option>
              </select>
            </div>

            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-[#6b7280] block mb-1">Climate Condition</span>
              <select value={weatherKey} onChange={(e) => setWeatherKey(e.target.value)}
                className="w-full bg-[#1c2127] border border-[#2d333b] text-white text-[13px] rounded px-2 py-1 outline-none focus:border-[#0072f5]">
                <option value="live">Live Lisbon Forecast (Open-Meteo)</option>
                <option value="sunny_summer">Sunny Summer (Peak PV)</option>
                <option value="cloudy_winter">Cloudy Winter (Zero-PV Fallback)</option>
                <option value="mild_spring">Mild Spring</option>
              </select>
            </div>

            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-[#6b7280] mb-1 flex items-center gap-1.5"><Dog className="w-3.5 h-3.5" /> Pet Logic — Dog Location</span>
              <Segmented small value={dogMode} onChange={setDogMode} options={[
                { value: 'auto', label: 'AUTO', title: 'Dog joins some weekend trips' },
                { value: 'home', label: 'HOME', title: 'Dog stays home — pet loads essential' },
                { value: 'away', label: 'AWAY', title: 'Dog travels — pet loads off' },
              ]} />
            </div>

            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-[#6b7280] block mb-1">Rooftop PV (kWp)</span>
              <Segmented small value={pvCapacity} onChange={setPvCapacity} options={[2, 4, 6, 8, 10, 12].map((c) => ({ value: c, label: String(c) }))} />
            </div>
          </div>

          {/* Monitored subsystems at the selected hour */}
          <div className="p-3">
            <span className="text-xs font-bold uppercase tracking-wider text-[#6b7280] block mb-2">
              Monitored Subsystems {sel && <span className="normal-case font-mono text-[#9ca3af]">@ {sel.label}</span>}
            </span>
            <div className="space-y-1 text-[13px]">
              {[
                { name: 'Lisbon Grid Incomer', val: sel ? `${fmt(Math.max(0, sel.predicted_kwh - sel.pv_kwh), 2)} kWh` : '—', on: true },
                { name: 'Rooftop PV Inverter', val: sel ? `${fmt(sel.pv_kwh, 2)} kWh` : `${pvCapacity} kWp`, on: sel?.pv_kwh > 0 },
                { name: 'Ventilation Baseline', val: '20 W', on: true },
                { name: 'Continuous Refrigerator', val: '~42 W', on: true },
                { name: 'Wi-Fi & Pet Monitoring', val: sel ? (sel.dog_home ? '22 W' : '12 W') : '—', on: true },
                { name: 'Shiftable Dishwasher', val: jobVal('dishwasher'), on: !!nextJob('dishwasher') },
                { name: 'Shiftable Washer', val: jobVal('washing'), on: !!nextJob('washing') },
                { name: 'Residents at Home', val: sel ? `${sel.people_home} / 2` : '—', on: sel?.people_home > 0 },
              ].map((node) => (
                <div key={node.name} className="flex items-center justify-between py-1 px-1.5 rounded text-[#9ca3af]">
                  <span className="truncate pr-2 flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${node.on ? 'bg-[#00d68f]' : 'bg-[#374151]'}`} />{node.name}
                  </span>
                  <span className="font-mono text-xs text-[#6b7280] shrink-0">{node.val}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer info */}
        <div className="p-3 border-t border-[#21262d] text-xs text-[#6b7280] space-y-1">
          <div>Lisbon 38.72° N, 9.14° W</div>
          <div>Seed 42 Enforced • HistGradientBoosting</div>
          <div className="flex items-center gap-1">
            {online ? <Wifi className="w-3 h-3 text-[#00d68f]" /> : <WifiOff className="w-3 h-3 text-amber-400" />}
            {health ? `${health.weather.source} • PV ${health.pv.source}` : 'connecting…'}
          </div>
        </div>
      </aside>

      {/* 2. MAIN WORKSPACE */}
      <Watermark tab={activeNav} />
      <div className="flex-1 flex flex-col min-w-0 lg:h-screen lg:overflow-y-auto">
        <header className="min-h-12 bg-[#13161a] border-b border-[#21262d] px-4 py-2 flex flex-wrap gap-2 items-center justify-between shrink-0 sticky top-0 z-30">
          <div className="flex items-center gap-4 text-[13px] flex-wrap">
            <div className="flex items-center gap-1.5 font-semibold text-white">
              <Home className="w-4 h-4 text-[#00d68f]" />
              <span>Lisbon Household</span>
              <span className="text-[#6b7280] font-normal flex items-center gap-1"><Users className="w-3.5 h-3.5" />Ola, Tomek & dog</span>
            </div>
            <nav className="flex items-center gap-1 pl-4 border-l border-[#21262d]">
              {TABS.map((tab) => (
                <button key={tab.id} onClick={() => setActiveNav(tab.id)}
                  className={`px-3 py-1 rounded text-[13px] font-medium transition-colors ${activeNav === tab.id ? 'bg-[#1f242c] text-white font-bold' : 'text-[#9ca3af] hover:text-white'}`}>
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3 text-[13px] flex-wrap">
            <div className="flex items-center gap-1.5 bg-[#162a22] border border-[#00d68f]/40 px-2 py-0.5 rounded text-[#00d68f] text-[13px] font-mono">
              <span className="w-2 h-2 rounded-full bg-[#00d68f] animate-pulse" /><span>FEED-IN €0.08</span>
            </div>
            <Segmented value={horizon} onChange={setHorizon} options={['24h', '3d', '7d'].map((h) => ({ value: h, label: h.toUpperCase() }))} />
            <div className="bg-[#1c2127] border border-[#2d333b] px-2.5 py-1 rounded text-[13px] text-[#9ca3af] font-mono">
              Tariff: <strong className="text-amber-400">€0.18 - €0.40/kWh</strong>
            </div>
            <button onClick={() => setRefreshKey((k) => k + 1)} title="Refresh data"
              className="p-1.5 rounded border border-[#2d333b] bg-[#1c2127] text-[#9ca3af] hover:text-white">
              <RefreshCw className={`w-3.5 h-3.5 ${loading || pvLoading ? 'animate-spin text-[#0072f5]' : ''}`} />
            </button>
          </div>
        </header>

        <main className="p-4 space-y-4">
          {weatherKey !== 'live' && data && (() => {
            const Icon = WEATHER_ICON[weatherKey];
            return (
              <div className="bg-amber-950/20 border border-amber-500/30 rounded-lg px-3 py-2 text-[13px] text-amber-300 flex items-center gap-2">
                <Icon className="w-4 h-4" /> What-if weather scenario active — forecast weather replaced by the “{health.weather_scenarios[weatherKey]}” preset. Switch Climate Condition to “Live” for the real Open-Meteo forecast.
              </div>
            );
          })()}
          {error && <ErrorBanner error={error} onRetry={() => setRefreshKey((k) => k + 1)} />}
          {!data ? (
            <div className="bg-[#181b1f] border border-[#262b32] rounded-lg">
              <Loading label="Starting ENERPILOT — fetching Lisbon weather & PVGIS data and training the forecast model. This takes 20 s locally, or 1–3 min if the online server was asleep…" />
            </div>
          ) : (
            <div className={loading ? 'opacity-70 transition-opacity' : 'transition-opacity'}>
              {activeNav === 'metrics' && <MetricsView data={view} pv={pv} selIdx={Math.min(selIdx, records.length - 1)} setSelIdx={setSelIdx} horizon={horizon} />}
              {activeNav === 'dispatch' && <DispatchView data={view} horizon={horizon} restWindow={enforceRestWindow} setRestWindow={setEnforceRestWindow} pvCapacity={pvCapacity}
                planMode={planMode} setPlanMode={setPlanMode} manualRuns={manualRuns} setManualRuns={setManualRuns} planBusy={planBusy} />}
              {activeNav === 'pv' && <PVView pv={pv} pvCapacity={pvCapacity} setPvCapacity={setPvCapacity} restWindow={enforceRestWindow} setRestWindow={setEnforceRestWindow} loading={pvLoading} />}
              {activeNav === 'compliance' && <ComplianceView data={view} pv={pv} metrics={metrics} hist={hist} histDays={histDays} setHistDays={setHistDays} horizon={horizon} />}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
