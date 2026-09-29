import React from 'react';
import {
  ComposedChart, BarChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { CheckCircle2, Cpu, Database, FileText, HelpCircle, History, Globe } from 'lucide-react';
import { COLORS, tooltipStyle, fmt, eur, Card, SectionHeader, Badge, Loading, Segmented } from '../components/ui.jsx';

const Check = ({ ok = true }) => <CheckCircle2 className={`w-4 h-4 shrink-0 ${ok ? 'text-[#00d68f]' : 'text-rose-400'}`} />;

export default function ComplianceView({ data, pv, metrics, hist, histDays, setHistDays, horizon }) {
  const h = data.health;
  const fc = data.forecast;
  const opt = data.optimization;
  const ex = data.explanations;
  const b = pv?.selected?.scenario_b;
  const a = pv?.selected?.scenario_a;
  const ev = metrics?.evaluation;

  const outcomes = [
    ['Historical hourly consumption profile ≥ 30 consecutive days', `${h.history_days} days hourly (seed 42, σ = 0.05 kWh noise) with real Open-Meteo weather`, h.history_days >= 30],
    ['Energy consumption forecasting model', metrics ? `HistGradientBoostingRegressor • day-ahead MAE ${ev.model_day_ahead.mae} kWh (${metrics.improvement_vs_naive_day_pct}% better than naive)` : 'loading…', !!metrics],
    ['Hourly forecast for the next 24 hours', '24 hourly values with 80% interval — Metrics tab, 24H', true],
    ['Forecasts for the next 3 and 7 days', '3D / 7D selector in the header (72 / 168 h recursive forecast)', true],
    ['Application presenting the results', 'This dashboard: forecast, peaks, explanations, dispatch, PV simulator', true],
    ['Identification of highest-demand hours', `Top-3: ${fc.peaks.top3.map((p) => `${p.day} ${String(p.hour).padStart(2, '0')}:00`).join(', ')}`, fc.peaks.top3.length === 3],
    ['Brief explanation of changes in consumption', ex.summary.slice(0, 140) + '…', true],
    ['Simulator of renewable investment impact', b ? `${pv.comparison.length} capacities, Scenario A vs B, payback ${a.payback_years} / ${b.payback_years} yrs @ ${pv.selected.capacity_kwp} kWp` : 'loading…', !!b],
    ['Real historical + forecast weather (outdoor temperature)', `${h.weather.provider} (${h.weather.source})`, h.weather.source.startsWith('open-meteo')],
    ['Official tariff 0.18 / 0.28 / 0.40 & PV €1,300/kWp, €0.08 export, 1% OPEX', 'Centralised in backend config; used by every engine', true],
  ];

  const questions = [
    ['Q1', 'What energy demand can be expected over the next 24 h, 3 days and 7 days?',
      `Next ${horizon}: ${fmt(fc.summary.total_kwh, 1)} kWh (${fmt(fc.summary.avg_kwh_per_day, 1)} kWh/day, ±${fmt(fc.summary.uncertainty_kwh, 1)} kWh). Switch 24H/3D/7D in the header.`],
    ['Q2', 'During which hours will energy demand be highest?',
      fc.peaks.top3.map((p) => `${p.day} ${String(p.hour).padStart(2, '0')}:00 (${fmt(p.kwh)} kWh)`).join(' • ') + ` — typically ${fc.peaks.peak_hours_of_day.map((x) => `${x}:00`).join(', ')}.`],
    ['Q3', 'What changes in habits could optimise renewable and grid use?',
      `${opt.shifted_count} appliance cycle(s) moved to the solar window / off-peak, saving ${eur(opt.savings.cost_eur)} and ${fmt(opt.savings.grid_import_kwh, 1)} kWh of grid import over ${horizon}; charge devices at midday; pre-cool/heat before 17:00; away mode when the dog travels.`],
    ['Q4', 'How does the PV investment affect grid purchases, costs and payback?',
      b ? `${pv.selected.capacity_kwp} kWp: grid purchases −${fmt(a.grid_reduction_kwh, 0)} kWh/yr (A) / −${fmt(b.grid_reduction_kwh, 0)} kWh/yr (B); net savings ${eur(a.net_annual_savings_eur, 0)} / ${eur(b.net_annual_savings_eur, 0)} per year; payback ${a.payback_years} / ${b.payback_years} years.` : 'loading…'],
  ];

  const evalRows = ev ? [
    ['HGB model — day-ahead recursive', ev.model_day_ahead, 'text-[#00d68f]'],
    ['HGB model — one-step', ev.model_one_step, 'text-white'],
    ['Naive: same hour previous day', ev.naive_same_hour_previous_day, 'text-[#9ca3af]'],
    ['Naive: same hour previous week', ev.naive_same_hour_previous_week, 'text-[#9ca3af]'],
  ] : [];

  return (
    <div className="space-y-4">
      <SectionHeader title="HackoWatt 2026 • Scenario 5 Compliance" right="Home Alone — But Not Really" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Required Outcomes (Scenario 5 §08)" icon={CheckCircle2} iconColor="text-[#00d68f]">
          <div className="space-y-1.5 text-[13px]">
            {outcomes.map(([k, v, ok], i) => (
              <div key={i} className="flex gap-2 p-1.5 rounded bg-[#13161a] border border-[#262b32]">
                <Check ok={ok} />
                <div><div className="text-white font-semibold">{k}</div><div className="text-[#9ca3af]">{v}</div></div>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Final Objective — Answers (Scenario 5 §09)" icon={HelpCircle}>
          <div className="space-y-2 text-[13px]">
            {questions.map(([q, t, ans]) => (
              <div key={q} className="p-2 rounded bg-[#13161a] border border-[#262b32]">
                <div className="flex gap-2 items-start"><Badge tone="blue">{q}</Badge><span className="text-white font-semibold">{t}</span></div>
                <div className="text-[#d1d5db] mt-1">{ans}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Forecast Model Validation" icon={Cpu} iconColor="text-[#0072f5]"
        subtitle={metrics ? `${metrics.model} • chronological split • train ${metrics.train_rows} h (${metrics.train_period[0].slice(0, 10)} → ${metrics.train_period[1].slice(0, 10)}) • test ${metrics.test_rows} h • trained in ${metrics.training_seconds}s` : ''}
        right={metrics && <Badge tone="green">R² {ev.model_day_ahead.r2} • MAE {ev.model_day_ahead.mae}</Badge>}>
        {!metrics ? <Loading label="Loading model metrics…" /> : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="space-y-3">
              <table className="w-full text-[13px]">
                <thead><tr className="text-xs uppercase text-[#6b7280] border-b border-[#262b32] text-right"><th className="text-left py-1">Model</th><th>MAE</th><th>RMSE</th><th>R²</th></tr></thead>
                <tbody>
                  {evalRows.map(([n, m, c]) => (
                    <tr key={n} className={`border-b border-[#1f242b] text-right font-mono ${c}`}>
                      <td className="text-left py-1 font-sans">{n}</td><td>{m.mae}</td><td>{m.rmse}</td><td>{m.r2}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="text-[13px] text-[#9ca3af]">
                Day-ahead MAE is <strong className="text-[#00d68f]">{metrics.improvement_vs_naive_day_pct}%</strong> lower than the previous-day baseline and <strong className="text-[#00d68f]">{metrics.improvement_vs_naive_week_pct}%</strong> lower than the previous-week baseline. Residual σ {metrics.residual_sigma_kwh} kWh drives the 80% interval.
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-[#6b7280] mb-1">Feature groups (permutation importance)</div>
                {Object.entries(metrics.feature_group_importance).map(([g, v]) => {
                  const max = Math.max(...Object.values(metrics.feature_group_importance));
                  return (
                    <div key={g} className="text-xs mb-1">
                      <div className="flex justify-between text-[#d1d5db]"><span>{g}</span><span className="font-mono">{v}</span></div>
                      <div className="h-1.5 bg-[#2a3038] rounded-full"><div className="h-full rounded-full bg-[#0072f5]" style={{ width: `${(v / max) * 100}%` }} /></div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="lg:col-span-2">
              <div className="text-xs uppercase tracking-wider text-[#6b7280] mb-1">Hold-out: actual vs day-ahead forecast (last 7 days of test period)</div>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={metrics.test_series.slice(-168)} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#262b32" vertical={false} />
                    <XAxis dataKey="time" stroke="#6b7280" fontSize={11} interval={23} tickFormatter={(t) => t.slice(5, 10)} />
                    <YAxis stroke="#6b7280" fontSize={12} unit=" kWh" />
                    <Tooltip {...tooltipStyle} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line dataKey="actual" name="Actual" stroke="#d1d5db" dot={false} strokeWidth={1.2} isAnimationActive={false} />
                    <Line dataKey="predicted" name="HGB day-ahead" stroke={COLORS.blue} dot={false} strokeWidth={1.5} isAnimationActive={false} />
                    <Line dataKey="naive_day" name="Naive previous day" stroke={COLORS.rose} dot={false} strokeDasharray="3 3" strokeWidth={1} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="flex flex-wrap gap-1 mt-2">
                {metrics.feature_importance.slice(0, 10).map((f) => <Badge key={f.feature}>{f.feature} {f.importance}</Badge>)}
              </div>
            </div>
          </div>
        )}
      </Card>

      <Card title="Historical Consumption Profile" icon={History} iconColor="text-[#00d68f]"
        subtitle="Synthetic appliance-level profile driven by real Lisbon weather, hybrid-work occupancy, weekend travel and pet loads."
        right={<Segmented small value={histDays} onChange={setHistDays} options={[{ value: 30, label: '30D' }, { value: 90, label: '90D' }, { value: 365, label: '365D' }]} />}>
        {!hist ? <Loading label="Loading history…" /> : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mb-3 text-[13px]">
              {[
                ['Total', `${fmt(hist.summary.total_kwh, 0)} kWh`], ['Avg / day', `${hist.summary.avg_kwh_per_day} kWh`],
                ['Min hour', `${hist.summary.min_hour_kwh} kWh`], ['Max hour', `${hist.summary.max_hour_kwh} kWh`],
                ['Absent hours avg', hist.summary.absent_avg_kwh ? `${hist.summary.absent_avg_kwh} kWh/h` : '—'],
                ['Travel / dog-away days', `${hist.summary.travel_days} / ${hist.summary.dog_away_days}`],
              ].map(([k, v]) => (
                <div key={k} className="p-2 rounded bg-[#13161a] border border-[#262b32]"><div className="text-xs text-[#6b7280] uppercase">{k}</div><div className="font-mono text-white">{v}</div></div>
              ))}
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={hist.daily} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#262b32" vertical={false} />
                  <XAxis dataKey="date" stroke="#6b7280" fontSize={11} tickFormatter={(d) => d.slice(5)} interval={Math.max(0, Math.floor(hist.daily.length / 15))} />
                  <YAxis yAxisId="e" stroke="#6b7280" fontSize={12} unit=" kWh" />
                  <YAxis yAxisId="t" orientation="right" stroke={COLORS.amber} fontSize={12} unit="°C" />
                  <Tooltip {...tooltipStyle} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar yAxisId="e" dataKey="essential_kwh" name="Essential" stackId="a" fill={COLORS.green} isAnimationActive={false} />
                  <Bar yAxisId="e" dataKey="flexible_kwh" name="Flexible" stackId="a" fill={COLORS.blue} isAnimationActive={false} />
                  <Bar yAxisId="e" dataKey="comfort_kwh" name="Comfort / activity" stackId="a" fill={COLORS.rose} isAnimationActive={false} />
                  <Line yAxisId="t" dataKey="temp_mean" name="Mean temp" stroke={COLORS.amber} dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {Object.entries(hist.summary.day_type_counts).map(([k, v]) => <Badge key={k} tone="blue">{k}: {v} d</Badge>)}
            </div>
          </>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Data Sources & Quality" icon={Database}>
          <div className="space-y-1.5 text-[13px]">
            {[
              ['Weather (history + forecast)', h.weather.provider, h.weather.source],
              ['PV production', h.pv.provider, h.pv.source],
              ['Location', `${h.location.city} (${h.location.lat}° N, ${Math.abs(h.location.lon)}° W)`, h.location.timezone],
              ['History window', `${h.weather.history_start} → ${h.weather.history_end}`, `${h.history_days} d`],
              ['Forecast window', `${h.weather.forecast_start} → ${h.weather.forecast_end}`, '168 h'],
              ['Data quality', `${h.weather.data_quality.gaps_filled} gaps filled, ${h.weather.data_quality.duplicates_removed} duplicates removed, ${h.weather.data_quality.values_clipped} values clipped`, `${h.weather.data_quality.rows_out} rows`],
              ['Engine build', `built ${h.built_at} in ${h.build_seconds}s`, h.offline_mode ? 'OFFLINE DEMO' : 'online'],
            ].map(([k, v, tag]) => (
              <div key={k} className="flex justify-between gap-2 p-1.5 rounded bg-[#13161a] border border-[#262b32]">
                <div><div className="text-white">{k}</div><div className="text-[#9ca3af]">{v}</div></div>
                <Badge tone={String(tag).includes('fallback') ? 'amber' : 'green'}>{tag}</Badge>
              </div>
            ))}
            {h.weather.errors?.length > 0 && <div className="text-amber-400">{h.weather.errors.join(' • ')}</div>}
          </div>
        </Card>
        <Card title="Assumptions Register" icon={FileText}>
          <div className="text-[13px] space-y-2">
            <div>
              <div className="text-xs uppercase tracking-wider text-[#00d68f] mb-1 flex items-center gap-1"><Globe className="w-3 h-3" /> Official (HackoWatt)</div>
              <ul className="list-disc pl-4 text-[#9ca3af] space-y-0.5">
                <li>Tariff €0.18 (00–06) / €0.28 (06–17) / €0.40 (17–22) / €0.28 (22–24)</li>
                <li>PV €1,300/kWp, export €0.08/kWh, OPEX 1%/yr; location Lisbon</li>
                <li>≥30 days hourly history; real historical & forecast weather incl. outdoor temperature</li>
                <li>Appliance ranges from Scenario 5 §03 (all simulator values lie inside them)</li>
              </ul>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-amber-400 mb-1">Model assumptions (documented)</div>
              <ul className="list-disc pl-4 text-[#9ca3af] space-y-0.5">
                <li>Two adults + dog; weekdays 25% both WFH / 40% one WFH / 35% both away; 45% of weekends travelling, dog joins 35% of trips</li>
                <li>Heat pump 1.5 kW / AC 1.2 kW rated, duty-cycled by outdoor temperature; dog-safe band 10–28 °C when alone</li>
                <li>Dishwasher 1.0 kWh & washer 0.8 kWh as 2-h blocks on selected days; kettle 2 kW × 4 min, coffee 1.2 kW × 7 min</li>
                <li>PVGIS 35° tilt, south, 14% loss; forecast PV = GHI × 1.10 tilt gain × 0.86; shared-rooftop PV access</li>
                <li>Seed 42, noise N(0, 0.05²) kWh, 6.9 kW single-phase cap; zero-PV threshold 0.1 kWh/h in 10–16 h</li>
              </ul>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
