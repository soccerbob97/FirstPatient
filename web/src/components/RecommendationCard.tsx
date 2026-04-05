import { Building2, MapPin, Link2 } from 'lucide-react';
import type { Recommendation } from '../api/client';

interface RecommendationCardProps {
  recommendation: Recommendation;
  rank: number;
}

const linkTypeLabels: Record<string, string> = {
  oversight: 'Study Oversight',
  site_contact: 'Site Contact',
  affiliation_match: 'Affiliation Match',
};

export function RecommendationCard({ recommendation, rank }: RecommendationCardProps) {
  const { investigator, site, link_type, scores } = recommendation;
  const matchPercent = Math.round(scores.final * 100);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        {/* Left: PI and Site Info */}
        <div className="flex items-start gap-4">
          {/* Rank Badge */}
          <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-medium">
            {rank}
          </div>

          <div>
            {/* PI Name */}
            <h3 className="text-lg font-semibold text-slate-800">
              {investigator.name}
            </h3>

            {/* Site Info */}
            <div className="mt-1 space-y-1">
              <div className="flex items-center gap-2 text-slate-600">
                <Building2 size={16} className="text-slate-400" />
                <span>{site.name}</span>
              </div>
              <div className="flex items-center gap-2 text-slate-500 text-sm">
                <MapPin size={14} className="text-slate-400" />
                <span>{site.city}, {site.country}</span>
              </div>
            </div>

            {/* Link Type Badge */}
            <div className="mt-3">
              <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-full">
                <Link2 size={12} />
                {linkTypeLabels[link_type] || link_type}
              </span>
            </div>
          </div>
        </div>

        {/* Right: Match Score */}
        <div className="text-right">
          <div className="text-2xl font-bold text-blue-600">{matchPercent}%</div>
          <div className="text-xs text-slate-500">Match Score</div>
        </div>
      </div>

      {/* Score Breakdown */}
      <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-3 gap-4 text-center">
        <div>
          <div className="text-sm font-medium text-slate-700">
            {Math.round(scores.similarity * 100)}%
          </div>
          <div className="text-xs text-slate-500">Similarity</div>
        </div>
        <div>
          <div className="text-sm font-medium text-slate-700">
            {scores.total_trials} trials
          </div>
          <div className="text-xs text-slate-500">Experience</div>
        </div>
        <div>
          <div className="text-sm font-medium text-slate-700">
            {Math.round(scores.completion_rate * 100)}%
          </div>
          <div className="text-xs text-slate-500">Completion</div>
        </div>
      </div>
    </div>
  );
}
