import React, { useMemo } from 'react';
import {
  ComposedChart, Area, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceArea, Legend,
} from 'recharts';
import { Activity, Lock, ListChecks, Layers, Lightbulb, ShieldCheck, CloudRain } from 'lucide-react';
import { COLORS, tooltipStyle, fmt, eur, Card, SectionHeader, Stat, Badge, peakBands, STRATEGY } from '../components/ui.jsx';
import AppliancePlanner from '../components/AppliancePlanner.jsx';

export default function DispatchView({ data, horizon, restWindow, setRestWindow, pvCapacity, planMode, setPlanMode, manualRuns, setManualRuns, planBusy }) {
  const opt = data.optimization;
  const fc = data.forecast;
  const series = opt.series;
  const bands = useMemo(() => peakBands(series), [series]);
  const tick = horizon === '24h' ? 2 : horizon === '3d' ? 5 : 11;
  const compKwh = Object.fromEntries(fc.components.map((c) => [c.component, c.kwh]));
  const byCat = (cat) => opt.load_classes.filter((c) => c.category === cat);
  const prio = { high: 'rose', medium: 'amber', low: 'grey' };

  return (
    <div className="space-y-4">
      <SectionHeader title="Load Shifting & Dispatch Optimisation" right={`${pvCapacity} kWp PV • horizon ${horizon} • ${opt.shifted_count} cycle(s) shifted`} />

      <AppliancePlanner planner={opt.planner} mode={planMode} setMode={setPlanMode}
        runs={manualRuns} setRuns={setManualRuns} busy={planBusy} />

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Stat label="Cost before" value={eur(opt.before.cost_eur)} hint="unmanaged habits, with PV" />
        <Stat label="Cost after" value={eur(opt.after.cost_eur)} accent="text-[#00d68f]" hint="optimised schedule" />
        <Stat label="Saving" value={eur(opt.savings.cost_eur)} accent="text-[#00d68f]" hint={`over ${horizon}`} />
        <Stat label="Grid import" value={`${fmt(opt.before.grid_import_kwh, 1)} → ${fmt(opt.after.grid_import_kwh, 1)}`} hint={`−${fmt(opt.savings.grid_import_kwh, 2)} kWh`} />
        <Stat label="PV self-consumption" value={`${fmt(opt.before.self_consumption_pct, 0)}% → ${fmt(opt.after.self_consumption_pct, 0)}%`} accent="text-amber-400" hint={`+${fmt(opt.savings.self_consumption_pts, 1)} pts`} />
        <Stat label="€0.40 peak energy" value={`${fmt(opt.before.peak_tariff_kwh, 1)} → ${fmt(opt.after.peak_tariff_kwh, 1)}`} accent="text-rose-400" hint="kWh in 17:00–22:00" />
      </div>

      <Card title="Household Demand & Dispatch vs Solar Generation • Lisbon Tariff Matrix" icon={Activity} iconColor="text-[#00d68f]"
        subtitle="Unmanaged forecast vs smart-shifted demand. Flexible cycles are moved as contiguous blocks; essential loads never move."
        right={
          <button onClick={() => setRestWindow(!restWindow)}
            className={`px-3 py-1 rounded text-[13px] font-semibold border flex items-center gap-1.5 ${restWindow ? 'bg-[#1c2d27] border-[#00d68f]/40 text-[#00d68f]' : 'bg-[#22272e] border-[#373e47] text-[#9ca3af]'}`}>
            <Lock className="w-3.5 h-3.5" /><span>Rest Window (22h–07h): {restWindow ? 'ENFORCED' : 'OFF'}</span>
          </button>
        }>
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={series} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
              <defs>
                <linearGradient id="solarGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={COLORS.amber} stopOpacity={0.4} /><stop offset="95%" stopColor={COLORS.amber} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="optGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={COLORS.blue} stopOpacity={0.5} /><stop offset="95%" stopColor={COLORS.blue} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#262b32" vertical={false} />
              <XAxis dataKey="label" stroke="#6b7280" fontSize={12} interval={tick} />
              <YAxis stroke="#6b7280" fontSize={12} unit=" kWh" />
              <Tooltip {...tooltipStyle} formatter={(v, n) => [`${v} kWh`, n]} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {bands.map((b, i) => <ReferenceArea key={`band-${i}`} x1={b.x1} x2={b.x2} fill="#ff0000" fillOpacity={0.08} />)}
              <Area type="monotone" dataKey="pv_kwh" name="Solar PV yield" stroke={COLORS.amber} strokeWidth={2} fill="url(#solarGrad)" isAnimationActive={false} />
              <Line type="monotone" dataKey="unmanaged_kwh" name="Unmanaged baseline" stroke="#9ca3af" strokeWidth={1.5} strokeDasharray="3 3" dot={false} isAnimationActive={false} />
              <Area type="monotone" dataKey="optimized_kwh" name="Smart shifted demand" stroke={COLORS.blue} strokeWidth={2.5} fill="url(#optGrad)" isAnimationActive={false} />
              <Bar dataKey="shifted_in_kwh" name="Shifted-in cycles" fill={COLORS.green} barSize={6} isAnimationActive={false} />
              <Line type="stepAfter" dataKey="essential_kwh" name="Essential (fixed)" stroke={COLORS.green} strokeWidth={1} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-[#262b32] text-[13px] font-mono text-[#9ca3af]">
          <span className="text-rose-400">■ Peak tariff (€0.40)</span>
          {opt.bad_weather_days.length > 0 && <Badge tone="blue"><CloudRain className="w-3 h-3" /> zero-PV fallback: {opt.bad_weather_days.join(', ')}</Badge>}
          <span className="ml-auto">Single-Phase Cap: <strong className="text-white">6.9 kW</strong> • peak hour {fmt(opt.before.max_hour_kwh)} → {fmt(opt.after.max_hour_kwh)} kWh</span>
        </div>
      </Card>

      <Card title="Recommended Appliance Schedule" icon={ListChecks} subtitle="Contiguous, non-interruptible cycles. A move is recommended only when it lowers cost.">
        {opt.schedule.length === 0 ? (
          <p className="text-[13px] text-[#9ca3af]">{planMode === 'manual' ? 'No runs in your manual plan for this horizon — add one in the Appliance Planner above.' : 'No flexible cycles are planned in this horizon (e.g. residents travelling) — nothing to shift. Essential loads keep running for the dog.'}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-[#6b7280] border-b border-[#262b32]">
                  <th className="py-1.5 pr-2">Date</th><th className="pr-2">Appliance</th><th className="pr-2">Energy</th>
                  <th className="pr-2">Usual time</th><th className="pr-2">Recommended</th><th className="pr-2">Strategy</th>
                  <th className="pr-2 text-right">Saving</th><th className="pl-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {opt.schedule.map((s, i) => (
                  <tr key={i} className="border-b border-[#1f242b] align-top">
                    <td className="py-1.5 pr-2 font-mono text-[#9ca3af] whitespace-nowrap">{s.date?.slice(5)}</td>
                    <td className="pr-2 text-white whitespace-nowrap">{s.label}{s.noisy && <span className="text-[#6b7280]"> (noisy)</span>}{s.manual && <span className="ml-1"><Badge tone="green">YOUR PLAN</Badge></span>}</td>
                    <td className="pr-2 font-mono">{fmt(s.energy_kwh, 2)} kWh</td>
                    <td className="pr-2 font-mono text-[#9ca3af] whitespace-nowrap">{s.original_window}</td>
                    <td className={`pr-2 font-mono whitespace-nowrap ${s.shifted ? 'text-[#00d68f] font-bold' : 'text-[#9ca3af]'}`}>{s.recommended_window}</td>
                    <td className="pr-2"><Badge tone={STRATEGY[s.strategy]?.tone}>{STRATEGY[s.strategy]?.label}</Badge></td>
                    <td className="pr-2 text-right font-mono text-[#00d68f]">{eur(s.saving_eur)}</td>
                    <td className="pl-2 text-[#9ca3af]">{s.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card title="Essential vs Flexible Loads" icon={Layers} subtitle={`Energy in the ${horizon} forecast by class`}>
          {[['essential', 'Essential — never shifted', COLORS.green], ['flexible', 'Flexible — shiftable', COLORS.blue], ['comfort', 'Comfort / activity — kept for residents', COLORS.rose]].map(([cat, title, color]) => (
            <div key={cat} className="mb-3">
              <div className="flex justify-between text-[13px] font-bold" style={{ color }}>
                <span>{title}</span><span className="font-mono">{fmt(fc.summary[`${cat}_kwh`], 2)} kWh</span>
              </div>
              <div className="mt-1 space-y-0.5 text-[13px]">
                {byCat(cat).map((c) => (
                  <div key={c.component} className="flex justify-between text-[#9ca3af]">
                    <span>{c.label}</span><span className="font-mono">{fmt(compKwh[c.component], 2)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </Card>

        <Card title="Actionable Recommendations" icon={Lightbulb} iconColor="text-amber-400" className="lg:col-span-2" subtitle="Q3 — habit changes that improve renewable use and reduce grid cost, without affecting the dog's comfort and safety.">
          <div className="space-y-2">
            {opt.recommendations.map((r, i) => (
              <div key={i} className="p-2 rounded bg-[#13161a] border border-[#262b32] text-[13px]">
                <div className="flex justify-between items-center gap-2">
                  <span className="text-white font-semibold">{r.title}</span>
                  <span className="flex gap-1 shrink-0">
                    <Badge tone={prio[r.priority]}>{r.priority}</Badge>
                    {r.saving_eur !== null && r.saving_eur !== undefined && <Badge tone="green">≈{eur(r.saving_eur)}</Badge>}
                  </span>
                </div>
                <div className="text-[#9ca3af] mt-0.5">{r.detail}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Optimiser Rules" icon={ShieldCheck} iconColor="text-[#00d68f]">
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-2 text-[13px]">
          {[
            ['Never shift', 'Fridge, Wi-Fi, ventilation, standby, pet camera/feeder, pet-safety HVAC'],
            ['Contiguous cycles', 'Dishwasher & washing machine run as uninterrupted blocks'],
            ['Primary window', `Solar ${opt.rules.solar_window}`],
            ['Zero-PV fallback', `${opt.rules.offpeak_fallback} when ${opt.rules.bad_weather_threshold}`],
            ['Rest window', `${opt.rules.rest_window} — ${opt.rules.rest_window_enforced ? 'ENFORCED' : 'disabled by user'}`],
            ['Connection limit', `≤ ${opt.rules.max_power_kw} kW every hour`],
          ].map(([k, v]) => (
            <div key={k} className="p-2 rounded bg-[#13161a] border border-[#262b32]"><strong className="text-white block">{k}</strong><span className="text-[#9ca3af]">{v}</span></div>
          ))}
        </div>
      </Card>
    </div>
  );
}
