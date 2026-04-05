import { X, ChevronDown } from 'lucide-react';

interface FilterPanelProps {
  phase: string;
  country: string;
  onPhaseChange: (phase: string) => void;
  onCountryChange: (country: string) => void;
}

const PHASES = [
  { value: '', label: 'All Phases' },
  { value: 'EARLY_PHASE1', label: 'Early Phase 1' },
  { value: 'PHASE1', label: 'Phase 1' },
  { value: 'PHASE2', label: 'Phase 2' },
  { value: 'PHASE3', label: 'Phase 3' },
  { value: 'PHASE4', label: 'Phase 4' },
];

const COUNTRIES = [
  { value: '', label: 'All Countries' },
  { value: 'United States', label: 'United States' },
  { value: 'China', label: 'China' },
  { value: 'Germany', label: 'Germany' },
  { value: 'France', label: 'France' },
  { value: 'United Kingdom', label: 'United Kingdom' },
  { value: 'Japan', label: 'Japan' },
  { value: 'Canada', label: 'Canada' },
  { value: 'Australia', label: 'Australia' },
];

export function FilterPanel({ phase, country, onPhaseChange, onCountryChange }: FilterPanelProps) {
  const hasFilters = phase || country;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* Phase Select */}
      <div className="relative">
        <select
          value={phase}
          onChange={(e) => onPhaseChange(e.target.value)}
          className="appearance-none bg-white border border-slate-300 rounded-lg pl-3 pr-10 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent cursor-pointer"
        >
          {PHASES.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" size={20} />
      </div>

      {/* Country Select */}
      <div className="relative">
        <select
          value={country}
          onChange={(e) => onCountryChange(e.target.value)}
          className="appearance-none bg-white border border-slate-300 rounded-lg pl-3 pr-10 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent cursor-pointer"
        >
          {COUNTRIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" size={20} />
      </div>

      {/* Clear Filters */}
      {hasFilters && (
        <button
          onClick={() => {
            onPhaseChange('');
            onCountryChange('');
          }}
          className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
        >
          <X size={14} />
          Clear
        </button>
      )}
    </div>
  );
}
