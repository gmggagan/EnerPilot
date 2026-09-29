import React from 'react';
import {
  ComposedChart, BarChart, Bar, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { Sun, BarChart3, CalendarRange, Clock, Lock, Award, Info } from 'lucide-react';
import { COLORS, tooltipStyle, fmt, eur, Card, SectionHeader, Row, Loading } from '../components/ui.jsx';

const CAPS = [2, 4, 6, 8, 10, 12];

function ScenarioBox({ title, s, accent, border, desc }) {
  return (
    <div className={`bg-[#13161a] border ${border} rounded p-3 text-[13px]`}>
      <span className={`text-xs font-bold uppercase tracking-wider block ${accent}`}>{title}</span>
      <span className="text-xs text-[#6b7280] block mb-1.5">{desc}</span>
      <Row k="Annual PV production" v={`${fmt(s.annual_production_kwh, 0)} kWh`} />
      <Row k="Self-generated share of demand" v={`${fmt(s.self_sufficiency_pct, 1)}%`} accent={accent} />
      <Row k="PV self-consumption" v={`${fmt(s.self_consumption_pct, 1)}%`} />
      <Row k="Grid electricity purchased" v={`${fmt(s.grid_purchased_kwh, 0)} kWh`} />
      <Row k="Reduction in grid purchase" v={`${fmt(s.grid_reduction_kwh, 0)} kWh (${fmt(s.grid_reduction_pct, 0)}%)`} accent={accent} />
      <Row k="Exported energy / revenue" v={`${fmt(s.exported_kwh, 0)} kWh / ${eur(s.export_revenue_eur, 0)}`} />
      <div className="border-t border-[#262b32] my-1.5" />
      <Row k="Capital investment" v={eur(s.capital_investment_eur, 0)} />
      <Row k="Annual OPEX (1%)" v={eur(s.annual_opex_eur, 0)} />
      <Row k="Gross annual savings" v={eur(s.gross_annual_savings_eur, 0)} />
      <Row k="Net annual savings" v={eur(s.net_annual_savings_eur, 0)} accent={accent} />
      <div className="flex justify-between border-t border-[#262b32] pt-1.5 mt-1.5">
        <span className="text-[#9ca3af]">Indicative payback</span>
        <span className={`font-mono font-bold text-base ${accent}`}>{s.payback_years ?? '—'} yrs</span>
      </div>
    </div>
  );
}

export default function PVView({ pv, pvCapacity, setPvCapacity, restWindow, setRestWindow, loading }) {
  if (!pv) return <Loading label="Running annual PV simulation (PVGIS × 365-day demand)…" />;
  const sel = pv.selected;
  const a = sel.scenario_a;
  const b = sel.scenario_b;
  const comp = pv.comparison.map((c) => ({
    cap: `${c.capacity_kwp} kWp`, paybackA: c.scenario_a.payback_years, paybackB: c.scenario_b.payback_years,
    savingsA: c.scenario_a.net_annual_savings_eur, savingsB: c.scenario_b.net_annual_savings_eur,
    selfA: c.scenario_a.self_sufficiency_pct, selfB: c.scenario_b.self_sufficiency_pct,
  }));
  const as = pv.assumptions;

  return (
    <div className="space-y-4">
      <SectionHeader title="Renewable Energy Simulator" color={COLORS.amber}
        right={`${as.pv_source.provider} • ${as.pv_source.annual_kwh_per_kwp} kWh/kWp/yr`} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2" title="Rooftop / Community PV Sizing" icon={Sun} iconColor="text-amber-400"
          subtitle={`Lisbon PVGIS: ${as.tilt_deg}° tilt, ${as.azimuth_deg}° (south) azimuth, ${as.system_loss_pct}% system loss • €${as.pv_cost_per_kwp_eur}/kWp • export €${as.export_tariff_eur_kwh}/kWh`}
          right={<div className="bg-[#1c2127] border border-[#2d333b] px-3 py-1 rounded text-[13px] font-mono text-amber-400 font-bold">
            {pvCapacity} kWp Array ({eur(pvCapacity * as.pv_cost_per_kwp_eur, 0)}){loading ? ' …' : ''}</div>}>
          <div className="py-1">
            <input type="range" min="2" max="12" step="2" value={pvCapacity} onChange={(e) => setPvCapacity(parseInt(e.target.value, 10))}
              className="w-full h-1.5 bg-[#262b32] rounded-lg appearance-none cursor-pointer accent-[#0072f5]" aria-label="PV capacity" />
            <div className="flex justify-between text-xs text-[#6b7280] font-mono mt-1.5">
              {CAPS.map((c) => (
                <button key={c} onClick={() => setPvCapacity(c)} className={`hover:text-white ${c === pvCapacity ? 'text-amber-400 font-bold' : ''}`}>
                  {c} kWp{c === pv.best_payback_capacity_kwp ? ' ★' : ''}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 my-3 flex-wrap">
            <span className="text-[13px] text-[#9ca3af]">Scenario B shifting honours the rest window:</span>
            <button onClick={() => setRestWindow(!restWindow)}
              className={`px-3 py-1 rounded text-[13px] font-semibold border flex items-center gap-1.5 ${restWindow ? 'bg-[#1c2d27] border-[#00d68f]/40 text-[#00d68f]' : 'bg-[#22272e] border-[#373e47] text-[#9ca3af]'}`}>
              <Lock className="w-3.5 h-3.5" />Rest Window (22h–07h): {restWindow ? 'ENFORCED' : 'OFF'}
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <ScenarioBox title="A • PV only — current habits" desc="PV investment without changing household behaviour" s={a} accent="text-amber-400" border="border-[#262b32]" />
            <ScenarioBox title="B • PV + intelligent load shifting" desc={`${sel.cycles_shifted}/${sel.cycles_total} appliance cycles/yr moved to better periods`} s={b} accent="text-[#00d68f]" border="border-[#00d68f]/30" />
          </div>
        </Card>

        <Card title="Investment Verdict" icon={Award} iconColor="text-amber-400">
          <div className="space-y-2 text-[13px] text-[#d1d5db]">
            <div className="p-2 rounded bg-[#13161a] border border-[#00d68f]/30">
              Shifting adds <strong className="text-[#00d68f]">{eur(sel.shifting_benefit_eur, 0)}/yr</strong> on top of PV-only
              {sel.payback_gain_years !== null && <> and pays back <strong className="text-[#00d68f]">{sel.payback_gain_years} yrs</strong> sooner</>}.
            </div>
            <div className="p-2 rounded bg-[#13161a] border border-[#262b32]">
              Shortest payback (Scenario B): <strong className="text-amber-400">{pv.best_payback_capacity_kwp} kWp</strong>. Larger arrays save more per year but export more at only €0.08/kWh, so payback lengthens.
            </div>
            <div className="p-2 rounded bg-[#13161a] border border-[#262b32]">
              Load shifting <em>without</em> PV (tariff only): <strong className="text-white">{eur(pv.shifting_only.annual_saving_eur, 0)}/yr</strong>
              {' '}({eur(pv.shifting_only.annual_cost_before_eur, 0)} → {eur(pv.shifting_only.annual_cost_after_eur, 0)}).
            </div>
            <div className="p-2 rounded bg-[#13161a] border border-[#262b32]">
              25-year net benefit at {sel.capacity_kwp} kWp: A <strong className="text-white">{eur(a.net_benefit_25y_eur, 0)}</strong> • B <strong className="text-[#00d68f]">{eur(b.net_benefit_25y_eur, 0)}</strong>
            </div>
            <div className="text-xs text-[#6b7280] flex gap-1.5"><Info className="w-3 h-3 shrink-0 mt-0.5" />
              Annual demand {fmt(a.annual_demand_kwh, 0)} kWh from the simulated 365-day household profile; baseline grid cost {eur(a.baseline_cost_eur, 0)}/yr at the official TOU tariff. Shared-rooftop / community PV assumed (Scenario 5).
            </div>
            {sel.shift_summary?.length > 0 && (
              <div className="pt-1">
                <div className="text-xs uppercase tracking-wider text-[#6b7280] mb-1">Cycles shifted per year</div>
                {sel.shift_summary.map((s) => <Row key={s.appliance} k={`${s.appliance} (${s.cycles_shifted}×)`} v={eur(s.saving_eur, 0)} accent="text-[#00d68f]" />)}
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card title="Capacity Comparison • Scenario A vs B" icon={BarChart3} subtitle="Payback (bars) and net annual savings (lines) for 2–12 kWp. Click a row to select it.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={comp} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#262b32" vertical={false} />
                <XAxis dataKey="cap" stroke="#6b7280" fontSize={12} />
                <YAxis yAxisId="y" stroke="#6b7280" fontSize={12} unit=" y" />
                <YAxis yAxisId="e" orientation="right" stroke="#6b7280" fontSize={12} unit="€" />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar yAxisId="y" dataKey="paybackA" name="Payback A (yrs)" fill={COLORS.amber} radius={[3, 3, 0, 0]} />
                <Bar yAxisId="y" dataKey="paybackB" name="Payback B (yrs)" fill={COLORS.green} radius={[3, 3, 0, 0]} />
                <Line yAxisId="e" dataKey="savingsA" name="Net savings A (€/yr)" stroke={COLORS.orange} dot />
                <Line yAxisId="e" dataKey="savingsB" name="Net savings B (€/yr)" stroke={COLORS.teal} dot />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-xs uppercase tracking-wider text-[#6b7280] border-b border-[#262b32] text-right">
                  <th className="text-left py-1">kWp</th><th>Prod. kWh</th><th>Self-gen A/B</th><th>Grid −kWh B</th><th>Net €/yr A/B</th><th>Payback A/B</th>
                </tr>
              </thead>
              <tbody>
                {pv.comparison.map((c) => (
                  <tr key={c.capacity_kwp} onClick={() => setPvCapacity(c.capacity_kwp)}
                    className={`border-b border-[#1f242b] text-right font-mono cursor-pointer hover:bg-[#1a1f26] ${c.capacity_kwp === pvCapacity ? 'bg-[#1c2127] text-white' : 'text-[#9ca3af]'}`}>
                    <td className="text-left py-1.5">{c.capacity_kwp}{c.capacity_kwp === pv.best_payback_capacity_kwp ? ' ★' : ''}</td>
                    <td>{fmt(c.scenario_a.annual_production_kwh, 0)}</td>
                    <td>{fmt(c.scenario_a.self_sufficiency_pct, 0)}% / <span className="text-[#00d68f]">{fmt(c.scenario_b.self_sufficiency_pct, 0)}%</span></td>
                    <td>{fmt(c.scenario_b.grid_reduction_kwh, 0)}</td>
                    <td>{fmt(c.scenario_a.net_annual_savings_eur, 0)} / <span className="text-[#00d68f]">{fmt(c.scenario_b.net_annual_savings_eur, 0)}</span></td>
                    <td>{c.scenario_a.payback_years ?? '—'} / <span className="text-[#00d68f]">{c.scenario_b.payback_years ?? '—'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title={`Monthly Energy Balance • ${sel.capacity_kwp} kWp`} icon={CalendarRange} iconColor="text-amber-400">
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sel.monthly} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#262b32" vertical={false} />
                <XAxis dataKey="month" stroke="#6b7280" fontSize={12} />
                <YAxis stroke="#6b7280" fontSize={12} unit=" kWh" />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="pv" name="PV production" fill={COLORS.amber} />
                <Bar dataKey="demand_a" name="Demand" fill={COLORS.grey} />
                <Bar dataKey="grid_a" name="Grid purchase A" fill={COLORS.orange} />
                <Bar dataKey="grid_b" name="Grid purchase B" fill={COLORS.green} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Average Day • Demand vs PV" icon={Clock} subtitle="Scenario B moves flexible cycles under the solar curve.">
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={sel.typical_day} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#262b32" vertical={false} />
                <XAxis dataKey="hour" stroke="#6b7280" fontSize={12} interval={2} />
                <YAxis stroke="#6b7280" fontSize={12} unit=" kWh" />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area dataKey="pv" name="PV" stroke={COLORS.amber} fill={COLORS.amber} fillOpacity={0.15} />
                <Line dataKey="demand_a" name="Demand A (habits)" stroke="#9ca3af" strokeDasharray="3 3" dot={false} />
                <Line dataKey="demand_b" name="Demand B (shifted)" stroke={COLORS.green} strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </div>
  );
}
