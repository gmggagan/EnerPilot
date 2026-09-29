import React from 'react';
import { CalendarClock, Plus, Trash2, RotateCcw, Lock, Shuffle, AlertTriangle, Eraser } from 'lucide-react';
import { Card, Segmented, Badge, fmt } from './ui.jsx';

// Start hours on a given day where the whole cycle fits inside the forecast horizon
const validStarts = (day, duration) => {
  if (!day) return [];
  const set = new Set(day.hours);
  return day.hours.filter((h) => h + duration <= 24 && Array.from({ length: duration }, (_, k) => h + k).every((x) => set.has(x)));
};

const selectCls = 'bg-[#1c2127] border border-[#2d333b] text-white text-[13px] rounded px-1.5 py-1 outline-none focus:border-[#0072f5]';

export default function AppliancePlanner({ planner, mode, setMode, runs, setRuns, busy }) {
  const days = planner?.days || [];
  const apps = planner?.appliances || {};
  const routine = planner?.routine_jobs || [];

  const update = (i, patch) => setRuns(runs.map((r, k) => {
    if (k !== i) return r;
    const next = { ...r, ...patch };
    // keep the start hour valid when the appliance or day changes
    const starts = validStarts(days.find((d) => d.date === next.date), apps[next.appliance]?.duration_h || 1);
    if (starts.length && !starts.includes(next.start)) next.start = starts.reduce((b, h) => (Math.abs(h - 19) < Math.abs(b - 19) ? h : b), starts[0]);
    return next;
  }));

  const addRun = () => {
    const day = days.find((d) => validStarts(d, 2).includes(19)) || days.find((d) => validStarts(d, 2).length) || days[0];
    if (!day) return;
    const starts = validStarts(day, 2);
    setRuns([...runs, { appliance: 'dishwasher', date: day.date, start: starts.includes(19) ? 19 : starts[0] ?? day.hours[0], flexible: true }]);
  };

  const customise = () => { setRuns(routine.map((r) => ({ ...r }))); setMode('manual'); };
  const totalKwh = runs.reduce((s, r) => s + (apps[r.appliance]?.energy_kwh || 0), 0);

  return (
    <Card title="Appliance Planner" icon={CalendarClock} iconColor="text-[#00d68f]"
      subtitle={mode === 'auto'
        ? 'AUTO — appliance runs come from Ola & Tomek’s typical routine. Switch to MANUAL to plan your own runs.'
        : 'MANUAL — plan your own runs. Flexible runs may be moved by EnerPilot to cheaper/solar hours; fixed runs stay at your time.'}
      right={
        <div className="flex items-center gap-2">
          {busy && <span className="text-xs text-[#9ca3af] font-mono">optimising…</span>}
          <Segmented small value={mode} onChange={(m) => (m === 'manual' && runs.length === 0 ? customise() : setMode(m))}
            options={[{ value: 'auto', label: 'AUTO' }, { value: 'manual', label: 'MANUAL' }]} />
        </div>
      }>
      {mode === 'auto' ? (
        <div className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
          <div className="flex flex-wrap gap-1">
            {routine.length === 0 && <span className="text-[#9ca3af]">No appliance runs in the routine for this horizon.</span>}
            {routine.map((r, i) => (
              <Badge key={i} tone="grey">{r.date.slice(5)} {String(r.start).padStart(2, '0')}:00 {apps[r.appliance]?.label}</Badge>
            ))}
          </div>
          <button onClick={customise}
            className="px-2.5 py-1 rounded border border-[#00d68f]/40 bg-[#1c2d27] text-[#00d68f] font-semibold flex items-center gap-1.5">
            <CalendarClock className="w-3.5 h-3.5" />Customise these runs
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {runs.length === 0 && <p className="text-[13px] text-[#9ca3af]">No runs planned — only essential and comfort loads remain. Add a run below.</p>}
          {runs.map((r, i) => {
            const spec = apps[r.appliance] || {};
            const day = days.find((d) => d.date === r.date);
            const starts = validStarts(day, spec.duration_h || 1);
            return (
              <div key={i} className="flex flex-wrap items-center gap-2 p-2 rounded bg-[#13161a] border border-[#262b32] text-[13px]">
                <span className="text-[#6b7280] font-mono w-5">#{i + 1}</span>
                <select className={selectCls} value={r.appliance} onChange={(e) => update(i, { appliance: e.target.value })} aria-label="Appliance">
                  {Object.entries(apps).map(([k, a]) => <option key={k} value={k}>{a.label}</option>)}
                </select>
                <select className={selectCls} value={r.date} onChange={(e) => update(i, { date: e.target.value })} aria-label="Day">
                  {!day && <option value={r.date}>{r.date} (outside horizon)</option>}
                  {days.map((d) => <option key={d.date} value={d.date}>{d.label}</option>)}
                </select>
                <select className={selectCls} value={r.start} onChange={(e) => update(i, { start: parseInt(e.target.value, 10) })} aria-label="Start time">
                  {!starts.includes(r.start) && <option value={r.start}>{String(r.start).padStart(2, '0')}:00 (not available)</option>}
                  {starts.map((h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
                </select>
                <span className="text-[#6b7280] font-mono">{fmt(spec.energy_kwh, 2)} kWh • {spec.duration_h} h{spec.noisy ? ' • noisy' : ''}</span>
                <button onClick={() => update(i, { flexible: !r.flexible })}
                  title={r.flexible ? 'EnerPilot may move this run' : 'This run stays at your chosen time'}
                  className={`ml-auto px-2 py-0.5 rounded border font-semibold flex items-center gap-1 ${r.flexible
                    ? 'bg-[#0f1f38] border-[#0072f5]/50 text-[#60a5fa]' : 'bg-[#162a22] border-[#00d68f]/40 text-[#00d68f]'}`}>
                  {r.flexible ? <><Shuffle className="w-3 h-3" />FLEXIBLE</> : <><Lock className="w-3 h-3" />FIXED</>}
                </button>
                <button onClick={() => setRuns(runs.filter((_, k) => k !== i))} title="Remove run"
                  className="p-1 rounded text-[#9ca3af] hover:text-rose-400 hover:bg-[#262b32]"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            );
          })}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button onClick={addRun} className="px-2.5 py-1 rounded border border-[#0072f5]/50 bg-[#0f1f38] text-[#60a5fa] text-[13px] font-semibold flex items-center gap-1.5">
              <Plus className="w-3.5 h-3.5" />Add run
            </button>
            <button onClick={customise} className="px-2.5 py-1 rounded border border-[#2d333b] text-[#9ca3af] hover:text-white text-[13px] flex items-center gap-1.5">
              <RotateCcw className="w-3.5 h-3.5" />Reset to routine
            </button>
            <button onClick={() => setRuns([])} className="px-2.5 py-1 rounded border border-[#2d333b] text-[#9ca3af] hover:text-white text-[13px] flex items-center gap-1.5">
              <Eraser className="w-3.5 h-3.5" />Clear all
            </button>
            <span className="ml-auto text-xs text-[#6b7280] font-mono">
              {runs.length} run(s) • {fmt(totalKwh, 2)} kWh • {runs.filter((r) => !r.flexible).length} fixed
            </span>
          </div>
          {planner?.warnings?.length > 0 && (
            <div className="space-y-1">
              {planner.warnings.map((w, i) => (
                <div key={i} className="flex gap-1.5 items-start text-[13px] text-amber-300 bg-amber-950/20 border border-amber-500/30 rounded px-2 py-1">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />{w}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
