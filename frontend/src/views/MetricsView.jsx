import React, { useMemo, useRef, useState } from 'react';
import {
  ComposedChart, Area, Line, Bar, BarChart, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceArea, ReferenceDot, Cell, Legend,
} from 'recharts';
import {
  Activity, Thermometer, TrendingUp, Info, Dog, ChevronLeft, ChevronRight, CalendarDays, Zap,
} from 'lucide-react';
import {
  COLORS, tooltipStyle, fmt, eur, NetdataCircularGauge, NetdataTachometer, NetdataSparkCard, Card,
  SectionHeader, Badge, peakBands, DAY_TYPE_LABEL,
} from '../components/ui.jsx';

const THUMB_PX = 16; // native range thumb width, used to map pointer x <-> hour index

// Hour slider with a floating time label that follows the pointer (hover, drag or touch)
function HourScrubber({ recs, selIdx, setSelIdx }) {
  const ref = useRef(null);
  const [hoverIdx, setHoverIdx] = useState(null);
  const [dragging, setDragging] = useState(false);
  const last = recs.length - 1;

  const idxFromEvent = (e) => {
    const r = ref.current.getBoundingClientRect();
    const frac = (e.clientX - r.left - THUMB_PX / 2) / Math.max(r.width - THUMB_PX, 1);
    return Math.round(Math.min(Math.max(frac, 0), 1) * last);
  };
  const shownIdx = dragging ? selIdx : hoverIdx;
  const rec = shownIdx !== null ? recs[shownIdx] : null;
  // x position of hour i, aligned with the centre of the native range thumb
  const at = (i) => `calc(${THUMB_PX / 2}px + ${i / Math.max(last, 1)} * (100% - ${THUMB_PX}px))`;
  const pos = rec ? at(shownIdx) : 0;

  // time scale: tick density adapts to the horizon (24 h / 3 d / 7 d)
  const major = last <= 24 ? 3 : last <= 72 ? 6 : 12;
  const minor = last <= 72 ? 1 : 3;
  const peakRuns = [];
  recs.forEach((r, i) => {
    if (!r.is_peak_tariff) return;
    const run = peakRuns[peakRuns.length - 1];
    if (run && run[1] === i - 1) run[1] = i; else peakRuns.push([i, i]);
  });

  return (
    <div className="relative flex-1 flex flex-col pt-1"
      onPointerMove={(e) => setHoverIdx(idxFromEvent(e))}
      onPointerLeave={() => { if (!dragging) setHoverIdx(null); }}>
      <input ref={ref} type="range" min={0} max={last} value={selIdx}
        onChange={(e) => setSelIdx(parseInt(e.target.value, 10))}
        onPointerDown={() => setDragging(true)}
        onPointerUp={() => { setDragging(false); }}
        onBlur={() => setDragging(false)}
        className="w-full h-1.5 bg-[#262b32] rounded-lg appearance-none cursor-pointer accent-[#0072f5]"
        aria-label="Select forecast hour" aria-valuetext={recs[selIdx]?.time} />

      {/* scale / ruler */}
      <div className="relative h-8 mt-1 select-none" aria-hidden="true">
        {peakRuns.map(([a, b]) => (
          <div key={`pk-${a}`} className="absolute top-0 h-1 rounded-full bg-rose-500/70" title="Evening peak €0.40"
            style={{ left: at(a), width: `calc(${(b - a + 1) / Math.max(last, 1)} * (100% - ${THUMB_PX}px))` }} />
        ))}
        {recs.map((r, i) => {
          const dayStart = r.hour === 0;
          const isMajor = dayStart || r.hour % major === 0;
          if (!isMajor && i % minor !== 0) return null;
          return (
            <div key={`t-${i}`} className={`absolute top-1 w-px ${i === selIdx ? 'bg-[#60a5fa]' : dayStart ? 'bg-[#9ca3af]' : isMajor ? 'bg-[#4b5563]' : 'bg-[#2d333b]'}`}
              style={{ left: at(i), height: dayStart ? 12 : isMajor ? 8 : 4 }} />
          );
        })}
        {recs.map((r, i) => {
          const dayStart = r.hour === 0;
          const isMajor = dayStart || r.hour % major === 0;
          // label majors, plus "now" at the start; skip majors crowding the "now" label
          if (i !== 0 && (!isMajor || i < Math.ceil(major / 2))) return null;
          const shift = i === 0 ? '0%' : i === last ? '-100%' : '-50%';
          return (
            <button key={`l-${i}`} type="button" onClick={() => setSelIdx(i)}
              className={`absolute top-3.5 text-[11px] font-mono leading-none px-0.5 rounded hover:text-white ${
                i === selIdx ? 'text-[#60a5fa] font-bold' : dayStart ? 'text-[#d1d5db] font-semibold' : 'text-[#6b7280]'}`}
              style={{ left: at(i), transform: `translateX(${shift})` }}>
              {i === 0 ? 'now' : dayStart ? r.label.slice(0, 3) : `${String(r.hour).padStart(2, '0')}h`}
            </button>
          );
        })}
        {recs.map((r, i) => r.is_top_peak && (
          <div key={`tp-${i}`} className="absolute -top-0.5 -translate-x-1/2 text-[10px] leading-none text-rose-400"
            style={{ left: at(i) }} title={`Top peak ${r.label} ${r.predicted_kwh} kWh`}>▲</div>
        ))}
      </div>

      {rec && (
        <div className="pointer-events-none absolute bottom-full mb-2 -translate-x-1/2 z-20 whitespace-nowrap
                        bg-[#0b0d10] border border-[#0072f5]/60 rounded px-2 py-1 text-xs font-mono shadow-lg"
          style={{ left: pos }}>
          <div className="text-white font-bold text-[13px]">{rec.label}</div>
          <div className="text-[#9ca3af]">{rec.time.slice(0, 10)} • {rec.temperature}°C</div>
          <div><span className="text-[#60a5fa]">{rec.predicted_kwh.toFixed(2)} kWh</span>
            <span className={rec.is_peak_tariff ? 'text-rose-400' : 'text-amber-400'}> • €{rec.tariff.toFixed(2)}</span></div>
          <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-x-4 border-x-transparent border-t-4 border-t-[#0072f5]/60" />
        </div>
      )}
    </div>
  );
}

export default function MetricsView({ data, pv, selIdx, setSelIdx, horizon }) {
  const fc = data.forecast;
  const ex = data.explanations;
  const opt = data.optimization;
  const recs = fc.records;
  const sel = recs[Math.min(selIdx, recs.length - 1)];
  const optSel = opt.series[Math.min(selIdx, opt.series.length - 1)];
  const bands = useMemo(() => peakBands(recs), [recs]);
  const chartData = useMemo(() => recs.map((r) => ({ ...r, band: [r.lower_kwh, r.upper_kwh] })), [recs]);

  const windowMax = (lo, hi) => {
    const pts = recs.filter((r) => r.hour >= lo && r.hour < hi);
    if (!pts.length) return null;
    return pts.reduce((m, r) => (r.predicted_kwh > m.predicted_kwh ? r : m), pts[0]);
  };
  const morning = windowMax(6, 9);
  const evening = windowMax(17, 22);
  const topLoads = fc.components.filter((c) => c.kwh > 0).slice(0, 4);
  const maxLoad = topLoads.length ? topLoads[0].kwh : 1;
  const catColor = { essential: COLORS.green, flexible: COLORS.blue, comfort: COLORS.rose };
  const b = pv?.selected?.scenario_b;
  const importH = Math.max(0, optSel.optimized_kwh - optSel.pv_kwh);
  const exportH = Math.max(0, optSel.pv_kwh - optSel.optimized_kwh);
  const tick = horizon === '24h' ? 2 : horizon === '3d' ? 5 : 11;

  return (
    <div className="space-y-4">
      <SectionHeader title="Forecast Telemetry" right={`Hour ${selIdx + 1}/${recs.length}: ${sel.time} • ${sel.people_home} resident(s) home • dog ${sel.dog_home ? 'home' : 'away'}`} />

      {/* Hour scrubber drives the gauges */}
      <div className="flex items-center gap-2 bg-[#181b1f] border border-[#262b32] rounded-lg px-3 py-2">
        <button onClick={() => setSelIdx(Math.max(0, selIdx - 1))} className="p-1 rounded hover:bg-[#262b32]" title="Previous hour"><ChevronLeft className="w-4 h-4" /></button>
        <HourScrubber recs={recs} selIdx={selIdx} setSelIdx={setSelIdx} />
        <button onClick={() => setSelIdx(Math.min(recs.length - 1, selIdx + 1))} className="p-1 rounded hover:bg-[#262b32]" title="Next hour"><ChevronRight className="w-4 h-4" /></button>
        <span className="text-[13px] font-mono text-white w-24 text-right">{sel.label}</span>
        <button onClick={() => setSelIdx(0)} className="text-xs px-2 py-0.5 rounded border border-[#2d333b] text-[#9ca3af] hover:text-white">NOW</button>
      </div>

      {/* ROW 1: gauges for the selected hour */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <NetdataCircularGauge label="Forecast Demand" value={sel.predicted_kwh} unit="kWh/h" color={COLORS.blue} max={6.9} sub={`±${fmt((sel.upper_kwh - sel.lower_kwh) / 2, 2)}`} />
        <NetdataCircularGauge label="PV Generation" value={sel.pv_kwh} unit="kWh/h" color={COLORS.amber} max={6.9} sub={`${fc.config.pv_kwp} kWp`} />
        <NetdataTachometer label="Grid Limit Ratio (6.9 kW)" value={sel.predicted_kwh} max={6.9} unit="kW" />
        <NetdataCircularGauge label={`Solar Self-Consumption (${horizon})`} value={opt.after.self_consumption_pct} unit="%" color={COLORS.green} max={100} />
        <NetdataCircularGauge label="Grid Import (optimised)" value={importH} unit="kWh/h" color={COLORS.teal} max={6.9} sub={`€${sel.tariff.toFixed(2)}/kWh`} />
        <NetdataCircularGauge label="PV Grid Export" value={exportH} unit="kWh/h" color={COLORS.orange} max={6.9} sub="€0.08/kWh" />
      </div>

      {/* ROW 2 */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <NetdataSparkCard label={`Total Forecast (${horizon})`} value={fmt(fc.summary.total_kwh, 1)} unit="kWh" data={recs} dataKey="predicted_kwh"
          color={COLORS.blue} sub={`${fmt(fc.summary.avg_kwh_per_day, 1)} kWh/day • ±${fmt(fc.summary.uncertainty_kwh, 1)}`} />
        <NetdataSparkCard label="Evening Peak (17–22h)" value={evening ? fmt(evening.predicted_kwh) : '—'} unit="kWh"
          data={recs.filter((r) => r.hour >= 17 && r.hour < 22)} dataKey="predicted_kwh" color={COLORS.rose}
          sub={evening ? `${evening.label} @ €0.40` : 'outside horizon'} />
        <div className="col-span-1 lg:col-span-2 bg-[#181b1f] border border-[#262b32] rounded-lg p-3 flex flex-col h-[172px]">
          <div className="flex justify-between text-[13px] text-[#9ca3af] font-medium mb-1">
            <span>Top Loads by Contribution ({horizon})</span><span className="font-mono">kWh</span>
          </div>
          <div className="space-y-1.5 text-[13px]">
            {topLoads.map((item) => (
              <div key={item.component} className="space-y-0.5">
                <div className="flex justify-between text-xs text-[#d1d5db]">
                  <span className="truncate">{item.label} <span className="text-[#6b7280]">• {item.category}</span></span>
                  <span className="font-mono">{fmt(item.kwh, 2)}</span>
                </div>
                <div className="h-1.5 w-full bg-[#2a3038] rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${(item.kwh / maxLoad) * 100}%`, backgroundColor: catColor[item.category] }} />
                </div>
              </div>
            ))}
          </div>
        </div>
        <NetdataSparkCard label="Forecast Energy Cost" value={eur(fc.summary.estimated_cost_eur)} unit="no PV"
          data={recs} dataKey="tariff" color={COLORS.purple} sub={`${eur(opt.after.cost_eur)} with PV + shifting`} />
        <NetdataSparkCard label="Morning Peak (06–09h)" value={morning ? fmt(morning.predicted_kwh) : '—'} unit="kWh"
          data={recs.filter((r) => r.hour >= 6 && r.hour < 9)} dataKey="predicted_kwh" color={COLORS.sky}
          sub={morning ? `${morning.label} kettle & coffee` : 'outside horizon'} />
      </div>

      {/* ROW 3: main forecast chart */}
      <Card title={`Hourly Energy Demand Forecast • next ${horizon}`} icon={Activity} iconColor="text-[#00d68f]"
        subtitle="HistGradientBoostingRegressor recursive forecast with 80% interval, essential (never-zero) baseline, outdoor temperature and €0.40 evening-peak bands. Click the chart to inspect an hour."
        right={<div className="flex gap-2 flex-wrap"><Badge tone="blue">{fmt(fc.summary.total_kwh, 1)} kWh total</Badge><Badge tone="rose">peak {fmt(fc.summary.peak_kwh)} kWh</Badge></div>}>
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 5, left: -15, bottom: 0 }}
              onClick={(e) => { if (e && e.activeTooltipIndex !== undefined) setSelIdx(e.activeTooltipIndex); }}>
              <defs>
                <linearGradient id="demandGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={COLORS.blue} stopOpacity={0.5} /><stop offset="95%" stopColor={COLORS.blue} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#262b32" vertical={false} />
              <XAxis dataKey="label" stroke="#6b7280" fontSize={12} interval={tick} />
              <YAxis yAxisId="e" stroke="#6b7280" fontSize={12} unit=" kWh" />
              <YAxis yAxisId="t" orientation="right" stroke={COLORS.amber} fontSize={12} unit="°C" domain={['dataMin - 2', 'dataMax + 2']} />
              <Tooltip {...tooltipStyle} formatter={(v, n) => (Array.isArray(v) ? [`${v[0]} – ${v[1]} kWh`, n] : [n.includes('Temp') ? `${v} °C` : `${v} kWh`, n])} />
              {bands.map((b, i) => <ReferenceArea key={`band-${i}`} yAxisId="e" x1={b.x1} x2={b.x2} fill="#ff0000" fillOpacity={0.08} />)}
              <Area yAxisId="e" type="monotone" dataKey="band" name="80% interval" stroke="none" fill={COLORS.blue} fillOpacity={0.12} isAnimationActive={false} />
              <Area yAxisId="e" type="monotone" dataKey="predicted_kwh" name="Forecast demand" stroke={COLORS.blue} strokeWidth={2.5} fill="url(#demandGrad)" isAnimationActive={false} />
              <Line yAxisId="e" type="stepAfter" dataKey="essential_kwh" name="Essential (never zero)" stroke={COLORS.green} strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
              <Line yAxisId="t" type="monotone" dataKey="temperature" name="Temperature" stroke={COLORS.amber} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              {fc.peaks.top3.map((p) => {
                const r = recs.find((x) => x.time === p.time);
                return r ? <ReferenceDot key={`peak-${p.rank}`} yAxisId="e" x={r.label} y={r.predicted_kwh} r={5} fill={COLORS.rose} stroke="#fff"
                  label={{ value: `#${p.rank}`, position: 'top', fill: '#fda4af', fontSize: 12 }} /> : null;
              })}
              <ReferenceDot yAxisId="e" x={sel.label} y={sel.predicted_kwh} r={4} fill="#fff" stroke={COLORS.blue} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-[#262b32] text-[13px] font-mono">
          <span className="flex items-center gap-1.5 text-white"><span className="w-2.5 h-2.5 rounded-sm bg-[#0072f5]" /> Forecast</span>
          <span className="flex items-center gap-1.5 text-[#9ca3af]"><span className="w-2.5 h-2.5 rounded-sm bg-[#0072f5]/30" /> 80% interval</span>
          <span className="flex items-center gap-1.5 text-[#00d68f]"><span className="w-2.5 h-0.5 bg-[#00d68f]" /> Essential baseline</span>
          <span className="flex items-center gap-1.5 text-amber-400"><span className="w-2.5 h-0.5 bg-[#f5a623]" /> Outdoor temp</span>
          <span className="flex items-center gap-1.5 text-rose-400"><span className="w-2.5 h-2.5 rounded-full bg-rose-500" /> Top-3 peaks</span>
          <span className="flex items-center gap-1.5 text-rose-400"><span className="w-2.5 h-2.5 rounded-sm bg-rose-950 border border-rose-600" /> Peak tariff €0.40</span>
          <span className="ml-auto text-[#6b7280]">Selected: <strong className="text-white">{sel.label}</strong> — {ex.hourly[sel.time]}</span>
        </div>
      </Card>

      {/* ROW 4: peaks + explanation */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card title="Highest-Demand Hours" icon={TrendingUp} iconColor="text-rose-400" subtitle={`Peak threshold ${fmt(fc.peaks.threshold_kwh)} kWh/h • ${fc.peaks.peak_in_evening_tariff_pct}% of top-3 in €0.40 band`}>
          <div className="space-y-2">
            {fc.peaks.top3.map((p) => (
              <div key={p.rank} className="p-2 rounded bg-[#13161a] border border-[#262b32] text-[13px]">
                <div className="flex justify-between items-center">
                  <span className="text-white font-bold">#{p.rank} {p.day} {String(p.hour).padStart(2, '0')}:00</span>
                  <span className="font-mono text-rose-400 font-bold">{fmt(p.kwh)} kWh</span>
                </div>
                <div className="text-[#9ca3af] mt-0.5">{p.explanation}</div>
                <div className="mt-1"><Badge tone={p.tariff >= 0.4 ? 'rose' : 'grey'}>{p.tariff_label} €{p.tariff.toFixed(2)}</Badge></div>
              </div>
            ))}
            <div className="text-xs uppercase tracking-wider text-[#6b7280] pt-1">Peak periods</div>
            <div className="flex flex-wrap gap-1">
              {fc.peaks.peak_periods.slice(0, 10).map((p, i) => <Badge key={i} tone="amber">{p.label} • {fmt(p.energy_kwh, 1)} kWh</Badge>)}
            </div>
          </div>
        </Card>

        <Card title="Why Demand Changes" icon={Info} className="lg:col-span-2" subtitle="Explanation engine: ML forecast decoupled from rule-based context drivers (occupancy, meals, weather-driven HVAC, pet, appliances).">
          <div className="space-y-2 text-[12px] text-[#d1d5db]">
            <p className="p-2 rounded bg-[#13161a] border border-[#0072f5]/40">{ex.summary}</p>
            <p className="p-2 rounded bg-[#13161a] border border-[#262b32]"><strong className="text-rose-400">Peak: </strong>{ex.peak}</p>
            <p className="p-2 rounded bg-[#13161a] border border-[#262b32]"><strong className="text-[#00d68f]">Low: </strong>{ex.lowest}</p>
            {ex.absence && <p className="p-2 rounded bg-[#13161a] border border-[#262b32] flex gap-2"><Dog className="w-4 h-4 text-[#00d68f] shrink-0 mt-0.5" /><span>{ex.absence}</span></p>}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1">
              {ex.day_changes.map((d) => (
                <div key={d.date} className="p-2 rounded bg-[#13161a] border border-[#262b32] text-[13px]">
                  <div className="flex justify-between items-center gap-2">
                    <span className="text-white font-semibold">{d.day}{d.partial_day ? ' (partial)' : ''}</span>
                    <span className="flex gap-1">
                      <Badge tone={d.day_type === 'weekend_travel' ? 'purple' : 'blue'}>{DAY_TYPE_LABEL[d.day_type]}</Badge>
                      <Badge tone={d.dog_home ? 'green' : 'grey'}>{d.dog_home ? 'dog home' : 'dog away'}</Badge>
                    </span>
                  </div>
                  <div className="font-mono text-[#9ca3af]">{d.partial_day ? `${fmt(d.kwh_in_horizon, 1)} kWh in ${d.hours} h` : `${fmt(d.kwh_per_day, 1)} kWh/day`} • {d.temp_mean}°C
                    {d.change_pct !== null && <span className={d.change_pct > 0 ? 'text-rose-400' : 'text-[#00d68f]'}> • {d.change_pct > 0 ? '+' : ''}{d.change_pct}%</span>}
                  </div>
                  <div className="text-[#9ca3af]">{d.explanation}</div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      {/* ROW 5: weather + daily totals */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Outdoor Weather Forecast" icon={Thermometer} iconColor="text-amber-400"
          subtitle={`${data.health.weather.provider} • ${fc.config.weather_scenario === 'live' ? 'live data' : 'what-if scenario: ' + fc.config.weather_scenario}`}
          right={<Badge tone="amber">{fc.summary.temp_min}°C – {fc.summary.temp_max}°C</Badge>}>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={recs} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#262b32" vertical={false} />
                <XAxis dataKey="label" stroke="#6b7280" fontSize={12} interval={tick} />
                <YAxis yAxisId="t" stroke={COLORS.amber} fontSize={12} unit="°C" domain={['dataMin - 2', 'dataMax + 2']} />
                <YAxis yAxisId="r" orientation="right" stroke="#6b7280" fontSize={12} unit=" W" />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area yAxisId="r" type="monotone" dataKey="radiation" name="Solar radiation (W/m²)" stroke={COLORS.amber} fill={COLORS.amber} fillOpacity={0.12} strokeOpacity={0.4} isAnimationActive={false} />
                <Line yAxisId="t" type="monotone" dataKey="temperature" name="Temperature (°C)" stroke={COLORS.rose} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line yAxisId="r" type="monotone" dataKey="cloud_cover" name="Cloud cover (%)" stroke="#9ca3af" strokeDasharray="3 3" dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Daily Totals & Context" icon={CalendarDays} subtitle="Forecast energy per day with the occupancy plan used as model context."
          right={<Badge tone="green">{fmt(ex.essential_share_pct, 0)}% essential</Badge>}>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={fc.peaks.daily_peaks} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#262b32" vertical={false} />
                <XAxis dataKey="day" stroke="#6b7280" fontSize={12} />
                <YAxis stroke="#6b7280" fontSize={12} unit=" kWh" />
                <Tooltip {...tooltipStyle} formatter={(v, n, p) => [`${v} kWh (${p.payload.hours} h, peak ${p.payload.peak_hour})`, 'Total']} />
                <Bar dataKey="total_kwh" name="Total" radius={[3, 3, 0, 0]}>
                  {fc.peaks.daily_peaks.map((d, i) => {
                    const plan = fc.day_plans.find((p) => p.day === d.date);
                    return <Cell key={i} fill={plan?.day_type === 'weekend_travel' ? COLORS.purple : plan?.wfh_count ? COLORS.blue : COLORS.teal} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-1 pt-2">
            {fc.day_plans.map((p) => (
              <Badge key={p.day} tone={p.travel ? 'purple' : p.wfh_count ? 'blue' : 'grey'}>
                {p.day.slice(5)} {DAY_TYPE_LABEL[p.day_type]}{p.dog_home ? '' : ' • dog away'}
              </Badge>
            ))}
          </div>
        </Card>
      </div>

      {b && (
        <div className="bg-[#181b1f] border border-[#262b32] rounded-lg p-3 text-[13px] text-[#9ca3af] flex flex-wrap gap-x-6 gap-y-1 items-center">
          <span className="flex items-center gap-1.5 text-white font-semibold"><Zap className="w-3.5 h-3.5 text-amber-400" />{pv.selected.capacity_kwp} kWp PV + shifting:</span>
          <span>self-sufficiency <strong className="text-[#00d68f]">{b.self_sufficiency_pct}%</strong></span>
          <span>grid purchase −<strong className="text-white">{fmt(b.grid_reduction_kwh, 0)} kWh/yr</strong></span>
          <span>net savings <strong className="text-white">{eur(b.net_annual_savings_eur, 0)}/yr</strong></span>
          <span>payback <strong className="text-amber-400">{b.payback_years ?? '—'} yrs</strong></span>
        </div>
      )}
    </div>
  );
}
