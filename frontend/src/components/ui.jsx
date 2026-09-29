import React from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export const COLORS = {
  blue: '#0072f5', green: '#00d68f', teal: '#00c49f', amber: '#f5a623', rose: '#f43f5e',
  purple: '#a855f7', orange: '#ff8042', grey: '#6b7280', sky: '#38bdf8',
};

export const tooltipStyle = {
  contentStyle: { backgroundColor: '#13161a', borderColor: '#2d333b', borderRadius: '0.5rem', fontSize: '13px', color: '#fff' },
  labelStyle: { color: '#9ca3af' },
};

export const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(d));
export const eur = (v, d = 2) => (v === null || v === undefined ? '—' : `€${Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}`);

// --- NETDATA-STYLE CIRCULAR GAUGE COMPONENT ---
export const NetdataCircularGauge = ({ label, value, unit, color = COLORS.teal, max = 10, sub }) => {
  const percentage = Math.min(Math.max((value || 0) / max, 0), 1);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="bg-[#181b1f] border border-[#262b32] rounded-lg p-3 flex flex-col items-center justify-between h-[172px]">
      <span className="text-[13px] text-[#9ca3af] font-medium tracking-wide text-center leading-tight">{label}</span>
      <div className="relative flex items-center justify-center">
        <svg className="w-24 h-24 transform -rotate-90">
          <circle cx="48" cy="48" r={radius} stroke="#2a3038" strokeWidth={5} fill="transparent" />
          <circle cx="48" cy="48" r={radius} stroke={color} strokeWidth={5} fill="transparent"
            strokeDasharray={circumference} strokeDashoffset={circumference * (1 - percentage)}
            strokeLinecap="round" className="transition-all duration-700 ease-out" />
        </svg>
        <div className="absolute flex flex-col items-center justify-center text-center">
          <span className="text-xl font-bold text-white tracking-tight leading-none">{typeof value === 'number' ? value.toFixed(2) : value}</span>
          <span className="text-xs text-[#9ca3af] mt-0.5">{unit}</span>
        </div>
      </div>
      {sub ? (
        <div className="w-full text-center text-xs text-[#9ca3af] font-mono truncate" title={sub}>{sub}</div>
      ) : (
        <div className="w-full flex justify-between text-[11px] text-[#6b7280] px-3 font-mono"><span>0</span><span>{max}</span></div>
      )}
    </div>
  );
};

// --- NETDATA-STYLE TACHOMETER DIAL GAUGE ---
export const NetdataTachometer = ({ label, value, max = 6.9, unit = 'kW' }) => {
  const percentage = Math.min(Math.max((value || 0) / max, 0), 1);
  const angle = -140 + percentage * 280;
  return (
    <div className="bg-[#181b1f] border border-[#262b32] rounded-lg p-3 flex flex-col items-center justify-between h-[172px]">
      <span className="text-[13px] text-[#9ca3af] font-medium tracking-wide text-center leading-tight">{label}</span>
      <div className="relative w-28 h-20 overflow-hidden flex items-end justify-center">
        <svg className="w-28 h-28 transform translate-y-3" viewBox="0 0 100 100">
          <path d="M 15 75 A 42 42 0 1 1 85 75" fill="none" stroke="#2a3038" strokeWidth="8" strokeLinecap="round" />
          <path d="M 15 75 A 42 42 0 1 1 85 75" fill="none" stroke={percentage > 0.8 ? COLORS.rose : COLORS.blue} strokeWidth="8"
            strokeDasharray="210" strokeDashoffset={210 * (1 - percentage)} strokeLinecap="round" />
        </svg>
        <div className="absolute bottom-2 w-1 h-12 bg-white rounded-full origin-bottom transition-transform duration-700 shadow-md"
          style={{ transform: `rotate(${angle}deg)` }} />
        <div className="absolute bottom-1 w-3 h-3 bg-white rounded-full border-2 border-[#181b1f]" />
      </div>
      <div className="text-center -mt-1">
        <span className="text-lg font-bold text-white tracking-tight">{(value || 0).toFixed(2)}</span>
        <span className="text-xs text-[#9ca3af] ml-1">{unit}</span>
        <span className="text-xs text-[#6b7280] ml-1">({(percentage * 100).toFixed(0)}%)</span>
      </div>
      <div className="w-full flex justify-between text-[11px] text-[#6b7280] px-2 font-mono"><span>0</span><span>{max}</span></div>
    </div>
  );
};

// --- NETDATA-STYLE SPARKLINE METRIC CARD ---
export const NetdataSparkCard = ({ label, value, unit, data, dataKey, color = COLORS.blue, sub }) => (
  <div className="bg-[#181b1f] border border-[#262b32] rounded-lg p-3 relative flex flex-col justify-between h-[172px] overflow-hidden">
    <span className="text-[13px] text-[#9ca3af] font-medium z-10 leading-tight">{label}</span>
    {data && data.length > 1 && (
      <div className="absolute inset-0 top-6 px-1 opacity-40 pointer-events-none">
        <ResponsiveContainer width="100%" height="70%">
          <LineChart data={data}>
            <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    )}
    <div className="z-10 mt-auto">
      <span className="text-3xl font-extrabold text-white tracking-tight">{value}</span>
      {unit && <span className="text-[13px] text-[#9ca3af] ml-1.5">{unit}</span>}
      {sub && <div className="text-xs text-[#9ca3af] mt-0.5 truncate" title={sub}>{sub}</div>}
    </div>
  </div>
);

export const Card = ({ title, icon: Icon, iconColor = 'text-[#0072f5]', right, children, className = '', subtitle }) => (
  <div className={`bg-[#181b1f] border border-[#262b32] rounded-lg p-4 ${className}`}>
    {(title || right) && (
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2 border-b border-[#262b32] pb-2 mb-3">
        <div>
          <h3 className="text-[13px] font-bold text-white uppercase tracking-wider flex items-center gap-2">
            {Icon && <Icon className={`w-4 h-4 ${iconColor}`} />}{title}
          </h3>
          {subtitle && <p className="text-[13px] text-[#6b7280] mt-0.5">{subtitle}</p>}
        </div>
        {right}
      </div>
    )}
    {children}
  </div>
);

export const SectionHeader = ({ title, right, color = COLORS.green }) => (
  <div className="flex items-center justify-between border-b border-[#21262d] pb-1.5">
    <div className="flex items-center gap-2">
      <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
      <h2 className="text-[13px] font-bold text-white uppercase tracking-wider">{title}</h2>
    </div>
    {right && <span className="text-[13px] text-[#6b7280] font-mono">{right}</span>}
  </div>
);

export const Stat = ({ label, value, accent = 'text-white', hint }) => (
  <div className="bg-[#13161a] border border-[#262b32] rounded p-2.5">
    <div className="text-xs uppercase tracking-wider text-[#6b7280]">{label}</div>
    <div className={`text-lg font-bold font-mono ${accent}`}>{value}</div>
    {hint && <div className="text-xs text-[#6b7280] leading-tight">{hint}</div>}
  </div>
);

export const Row = ({ k, v, accent = 'text-white' }) => (
  <div className="flex justify-between gap-2 py-0.5">
    <span className="text-[#9ca3af]">{k}</span><span className={`font-mono ${accent} text-right`}>{v}</span>
  </div>
);

export const Badge = ({ children, tone = 'grey' }) => {
  const tones = {
    grey: 'bg-[#1c2127] border-[#2d333b] text-[#9ca3af]',
    green: 'bg-[#162a22] border-[#00d68f]/40 text-[#00d68f]',
    amber: 'bg-amber-950/40 border-amber-500/40 text-amber-400',
    rose: 'bg-rose-950/40 border-rose-500/40 text-rose-400',
    blue: 'bg-[#0f1f38] border-[#0072f5]/50 text-[#60a5fa]',
    purple: 'bg-purple-950/40 border-purple-500/40 text-purple-300',
  };
  return <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-xs font-mono ${tones[tone]}`}>{children}</span>;
};

export const Segmented = ({ options, value, onChange, small }) => (
  <div className="flex bg-[#1c2127] border border-[#2d333b] rounded p-0.5 flex-wrap">
    {options.map((o) => (
      <button key={o.value} onClick={() => onChange(o.value)} title={o.title || o.label}
        className={`${small ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-0.5 text-[13px]'} font-mono rounded transition-colors ${
          value === o.value ? 'bg-[#0072f5] text-white font-bold' : 'text-[#9ca3af] hover:text-white'}`}>
        {o.label}
      </button>
    ))}
  </div>
);

export const Loading = ({ label = 'Loading…' }) => (
  <div className="flex items-center justify-center gap-2 text-[13px] text-[#9ca3af] py-10">
    <RefreshCw className="w-4 h-4 animate-spin text-[#0072f5]" />{label}
  </div>
);

export const ErrorBanner = ({ error, onRetry }) => (
  <div className="bg-rose-950/30 border border-rose-600/40 text-rose-300 rounded-lg p-3 text-[13px] flex items-center justify-between gap-3">
    <span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{error}</span>
    {onRetry && <button onClick={onRetry} className="px-2 py-1 rounded border border-rose-500/50 hover:bg-rose-900/40">Retry</button>}
  </div>
);

// Group consecutive peak-tariff points into shaded bands for charts
export const peakBands = (rows, key = 'label') => {
  const bands = [];
  let cur = null;
  rows.forEach((r) => {
    if (r.is_peak_tariff) {
      if (!cur) { cur = { x1: r[key], x2: r[key] }; bands.push(cur); } else cur.x2 = r[key];
    } else cur = null;
  });
  return bands;
};

export const STRATEGY = {
  solar_window: { label: 'SOLAR 10–16h', tone: 'amber' },
  offpeak_fallback: { label: 'OFF-PEAK 00–06h', tone: 'blue' },
  cheapest_allowed: { label: 'CHEAPEST ALLOWED', tone: 'purple' },
  keep: { label: 'KEEP', tone: 'grey' },
  fixed: { label: 'FIXED BY YOU', tone: 'green' },
};

export const DAY_TYPE_LABEL = {
  both_wfh: 'Both WFH', one_wfh: 'One WFH', both_away: 'Both away',
  weekend_home: 'Weekend home', weekend_travel: 'Travel',
};
