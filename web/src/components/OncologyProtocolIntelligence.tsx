import React, { useState } from 'react';

interface RiskFlag {
  flag_name: string;
  severity: string;
  description: string;
  mitigation: string;
}

interface ScoreBreakdown {
  score: number;
  factors: Array<{ name: string; value: any; impact: number }>;
  recommendations: string[];
}

interface OncologyAnalysis {
  success: boolean;
  protocol_id: string;
  metadata: Record<string, any>;
  indication: Record<string, any>;
  intervention: Record<string, any>;
  population: Record<string, any>;
  endpoints: Record<string, any>;
  operational: Record<string, any>;
  design: Record<string, any>;
  scores: {
    overall_complexity: number;
    enrollment_difficulty: ScoreBreakdown;
    site_burden: ScoreBreakdown;
    protocol_complexity: ScoreBreakdown;
    monitoring_complexity: ScoreBreakdown;
    amendment_risk: ScoreBreakdown;
    patient_burden: ScoreBreakdown;
  };
  risk_flags: RiskFlag[];
  top_enrollment_bottlenecks: string[];
  site_capability_requirements: string[];
  feasibility_questions: string[];
  estimated_screen_fail_rate: number;
  estimated_enrollment_rate: number;
  site_matching_criteria: Record<string, any>;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const ScoreGauge: React.FC<{ score: number; label: string; size?: 'sm' | 'lg' }> = ({
  score, label, size = 'sm'
}) => {
  const getColor = (s: number) => {
    if (s <= 25) return '#93c5fd'; // blue-300 (low - lightest)
    if (s <= 45) return '#3b82f6'; // blue-500 (moderate)
    if (s <= 65) return '#2563eb'; // blue-600 (high)
    return '#1e40af'; // blue-800 (very high - darkest)
  };

  const radius = size === 'lg' ? 45 : 35;
  const strokeWidth = size === 'lg' ? 8 : 5;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center relative">
      <svg
        width={radius * 2 + strokeWidth * 2}
        height={radius * 2 + strokeWidth * 2}
        className="transform -rotate-90"
      >
        <circle
          cx={radius + strokeWidth}
          cy={radius + strokeWidth}
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={radius + strokeWidth}
          cy={radius + strokeWidth}
          r={radius}
          fill="none"
          stroke={getColor(score)}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
        />
      </svg>
      <div
        className="absolute flex flex-col items-center justify-center"
        style={{ top: strokeWidth, left: strokeWidth, width: radius * 2, height: radius * 2 }}
      >
        <span className={`font-semibold text-gray-900 ${size === 'lg' ? 'text-xl' : 'text-base'}`}>
          {score.toFixed(0)}
        </span>
      </div>
      <span className={`mt-1 text-center ${size === 'lg' ? 'text-xs font-medium' : 'text-xs'} text-gray-500`}>
        {label}
      </span>
    </div>
  );
};

const RiskFlagBadge: React.FC<{ flag: RiskFlag }> = ({ flag }) => {
  const severityStyles = {
    high: { badge: 'bg-blue-800 text-white', border: 'border-l-4 border-blue-800' },
    medium: { badge: 'bg-blue-500 text-white', border: 'border-l-4 border-blue-500' },
    low: { badge: 'bg-blue-300 text-blue-800', border: 'border-l-4 border-blue-300' }
  };
  const style = severityStyles[flag.severity as keyof typeof severityStyles] || severityStyles.medium;

  return (
    <div className={`bg-white p-4 rounded-lg shadow-sm ${style.border}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-xs font-medium uppercase px-2 py-0.5 rounded ${style.badge}`}>
          {flag.severity}
        </span>
        <span className="font-medium text-gray-900">{flag.flag_name}</span>
      </div>
      <p className="text-sm text-gray-600 mb-2">{flag.description}</p>
      {flag.mitigation && (
        <p className="text-sm text-gray-500 italic">→ {flag.mitigation}</p>
      )}
    </div>
  );
};

const ScoreCard: React.FC<{
  title: string;
  breakdown: ScoreBreakdown;
  expanded: boolean;
  onToggle: () => void;
}> = ({ title, breakdown, expanded, onToggle }) => {
  const getScoreColor = (score: number) => {
    if (score <= 25) return 'text-blue-400';
    if (score <= 45) return 'text-blue-500';
    if (score <= 65) return 'text-blue-600';
    return 'text-blue-800';
  };

  const getBorderColor = (score: number) => {
    if (score <= 25) return 'border-l-4 border-l-blue-300';
    if (score <= 45) return 'border-l-4 border-l-blue-400';
    if (score <= 65) return 'border-l-4 border-l-blue-500';
    return 'border-l-4 border-l-blue-700';
  };

  const getInterpretation = (score: number) => {
    if (score <= 25) return { label: 'Low', detail: 'Minimal challenges for trial execution' };
    if (score <= 45) return { label: 'Moderate', detail: 'Some challenges; standard mitigation should suffice' };
    if (score <= 65) return { label: 'High', detail: 'Significant challenges; experienced sites recommended' };
    return { label: 'Very High', detail: 'Major challenges; consider protocol optimization' };
  };

  const interpretation = getInterpretation(breakdown.score);

  return (
    <div className={`bg-white rounded-lg border border-gray-200 overflow-hidden ${getBorderColor(breakdown.score)}`}>
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <span className="font-medium text-gray-800">{title}</span>
        <div className="flex items-center gap-3">
          <span className={`text-sm font-semibold ${getScoreColor(breakdown.score)}`}>
            {interpretation.label} ({breakdown.score.toFixed(0)})
          </span>
          <svg
            className={`w-5 h-5 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-100">
          {/* Interpretation */}
          <div className="mt-3 p-2 bg-gray-50 rounded-md">
            <p className="text-sm text-gray-600 italic">{interpretation.detail}</p>
          </div>

          {breakdown.factors.length > 0 ? (
            <div className="mt-3">
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Contributing Factors</h4>
              <div className="space-y-2">
                {breakdown.factors.map((factor, idx) => (
                  <div key={idx} className="flex items-center justify-between text-sm">
                    <span className="text-gray-600">{factor.name}</span>
                    <span className={`font-medium ${getScoreColor(breakdown.score)}`}>
                      +{factor.impact}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="mt-3 p-2 bg-blue-50 rounded-md">
              <p className="text-sm text-blue-700">✓ No significant complexity factors identified - this is a straightforward protocol in this area</p>
            </div>
          )}

          {breakdown.recommendations.length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Recommendations</h4>
              <ul className="space-y-1">
                {breakdown.recommendations.map((rec, idx) => (
                  <li key={idx} className="text-sm text-gray-600 flex items-start gap-2">
                    <span className="text-blue-500 mt-0.5">•</span>
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const OncologyProtocolIntelligence: React.FC = () => {
  const [analysis, setAnalysis] = useState<OncologyAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedScores, setExpandedScores] = useState<Set<string>>(new Set(['enrollment']));
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  const toggleScore = (key: string) => {
    setExpandedScores(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handlePdfUpload = async () => {
    if (!pdfFile) return;

    setLoading(true);
    setError(null);
    setAnalysis(null); // Clear previous analysis
    try {
      const formData = new FormData();
      formData.append('file', pdfFile);

      console.log('Uploading PDF:', pdfFile.name);
      const response = await fetch(`${API_BASE}/api/oncology-protocol/analyze-pdf`, {
        method: 'POST',
        body: formData
      });

      console.log('Response status:', response.status);

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        console.error('Error response:', errData);
        throw new Error(errData.detail || 'PDF analysis failed');
      }

      const data = await response.json();
      console.log('Analysis result:', data.protocol_id, data.metadata?.trial_title);
      // Add source indicator
      data._source = 'pdf';
      data._filename = pdfFile.name;
      setAnalysis(data);
    } catch (err) {
      console.error('PDF upload error:', err);
      setError(err instanceof Error ? err.message : 'PDF analysis failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full bg-slate-50 p-6 overflow-y-auto">
      <div className="max-w-6xl mx-auto pb-20">
        {/* Header - Clean and minimal like PI Finder */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-semibold text-gray-900 mb-2">Protocol Intelligence</h1>
          <p className="text-gray-500 text-sm">
            Analyze clinical trial protocols for operational feasibility and enrollment risks
          </p>
        </div>

        {/* Upload Section */}
        <div className="bg-white rounded-lg shadow-sm mb-6">
          <div className="p-6">
            <div className="space-y-4">
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center bg-gray-50 hover:bg-gray-100 transition-colors">
                <input
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setPdfFile(e.target.files?.[0] || null)}
                  className="hidden"
                  id="pdf-upload"
                />
                <label htmlFor="pdf-upload" className="cursor-pointer">
                  <svg className="mx-auto h-10 w-10 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="mt-2 text-sm text-gray-600 font-medium">
                    {pdfFile ? pdfFile.name : 'Click to upload protocol PDF'}
                  </p>
                  <p className="mt-1 text-xs text-gray-400">PDF up to 50MB</p>
                </label>
              </div>

              {pdfFile && (
                <div className="flex justify-center">
                  <button
                    onClick={handlePdfUpload}
                    disabled={loading}
                    className="px-6 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                  >
                    {loading ? 'Analyzing...' : 'Analyze Protocol'}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-gray-100 border border-gray-300 rounded-lg text-gray-700">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Results */}
        {analysis && (
          <div className="space-y-4">
            {/* Protocol Header - Clean card */}
            <div className="bg-white rounded-lg shadow-sm p-6">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h2 className="text-lg font-semibold text-gray-900">
                    {analysis.metadata.trial_title || analysis.protocol_id}
                  </h2>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {analysis.metadata.phase && (
                      <span className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs font-medium">
                        {analysis.metadata.phase}
                      </span>
                    )}
                    {analysis.indication.cancer_type && (
                      <span className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs font-medium">
                        {analysis.indication.cancer_type}
                      </span>
                    )}
                    {analysis.intervention.intervention_type && (
                      <span className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs font-medium">
                        {analysis.intervention.intervention_type}
                      </span>
                    )}
                    {analysis.population.line_of_therapy && (
                      <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                        {analysis.population.line_of_therapy}
                      </span>
                    )}
                  </div>
                </div>

                <div className="ml-6">
                  <ScoreGauge
                    score={analysis.scores.overall_complexity}
                    label="Complexity"
                    size="lg"
                  />
                </div>
              </div>
            </div>

            {/* Key Metrics - Clean grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-white rounded-lg shadow-sm p-4">
                <div className="text-xs text-gray-500 mb-1">Est. Enrollment Rate</div>
                <div className="text-xl font-semibold text-gray-900">
                  {analysis.estimated_enrollment_rate?.toFixed(2) || '0.00'}
                </div>
                <div className="text-xs text-gray-400">pts/site/mo</div>
              </div>
              <div className="bg-white rounded-lg shadow-sm p-4">
                <div className="text-xs text-gray-500 mb-1">Est. Screen Fail Rate</div>
                <div className="text-xl font-semibold text-gray-900">
                  {analysis.estimated_screen_fail_rate?.toFixed(1) || '0'}%
                </div>
                <div className="text-xs text-gray-400">eligibility driven</div>
              </div>
              <div className="bg-white rounded-lg shadow-sm p-4">
                <div className="text-xs text-gray-500 mb-1">Risk Flags</div>
                <div className="text-xl font-semibold text-gray-900">
                  {analysis.risk_flags?.length || 0}
                  <span className="text-xs font-normal ml-1 text-gray-500">
                    ({analysis.risk_flags?.filter(f => f.severity === 'high').length || 0} high)
                  </span>
                </div>
                <a href="#risk-flags" className="text-xs text-blue-600 hover:underline">View details</a>
              </div>
              <div className="bg-white rounded-lg shadow-sm p-4">
                <div className="text-xs text-gray-500 mb-1">Site Requirements</div>
                <div className="text-xl font-semibold text-gray-900">
                  {analysis.site_capability_requirements?.length || 0}
                </div>
                <a href="#site-requirements" className="text-xs text-blue-600 hover:underline">View details</a>
              </div>
            </div>

            {/* Risk Flags */}
            <div id="risk-flags" className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase tracking-wide">Risk Flags ({analysis.risk_flags?.length || 0})</h3>
              {analysis.risk_flags && analysis.risk_flags.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {analysis.risk_flags.map((flag, idx) => (
                    <RiskFlagBadge key={idx} flag={flag} />
                  ))}
                </div>
              ) : (
                <p className="text-gray-500 italic">No significant risk flags identified for this protocol.</p>
              )}
            </div>

            {/* Score Breakdown */}
            <div id="score-breakdown" className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase tracking-wide">Score Breakdown</h3>
              <div className="space-y-3">
                <ScoreCard
                  title="Enrollment Difficulty"
                  breakdown={analysis.scores.enrollment_difficulty}
                  expanded={expandedScores.has('enrollment')}
                  onToggle={() => toggleScore('enrollment')}
                />
                <ScoreCard
                  title="Site Burden"
                  breakdown={analysis.scores.site_burden}
                  expanded={expandedScores.has('site')}
                  onToggle={() => toggleScore('site')}
                />
                <ScoreCard
                  title="Protocol Complexity"
                  breakdown={analysis.scores.protocol_complexity}
                  expanded={expandedScores.has('protocol')}
                  onToggle={() => toggleScore('protocol')}
                />
                <ScoreCard
                  title="Monitoring Complexity"
                  breakdown={analysis.scores.monitoring_complexity}
                  expanded={expandedScores.has('monitoring')}
                  onToggle={() => toggleScore('monitoring')}
                />
                <ScoreCard
                  title="Amendment Risk"
                  breakdown={analysis.scores.amendment_risk}
                  expanded={expandedScores.has('amendment')}
                  onToggle={() => toggleScore('amendment')}
                />
                <ScoreCard
                  title="Patient Burden"
                  breakdown={analysis.scores.patient_burden}
                  expanded={expandedScores.has('patient')}
                  onToggle={() => toggleScore('patient')}
                />
              </div>
            </div>

            {/* Enrollment Bottlenecks */}
            <div id="bottlenecks" className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase tracking-wide">Enrollment Bottlenecks ({analysis.top_enrollment_bottlenecks?.length || 0})</h3>
              {analysis.top_enrollment_bottlenecks && analysis.top_enrollment_bottlenecks.length > 0 ? (
                <ul className="space-y-2">
                  {analysis.top_enrollment_bottlenecks.map((bottleneck, idx) => (
                    <li key={idx} className="flex items-start gap-3 text-sm text-gray-600">
                      <span className="flex-shrink-0 w-5 h-5 bg-gray-100 text-gray-600 rounded-full flex items-center justify-center text-xs font-medium">
                        {idx + 1}
                      </span>
                      {bottleneck}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-gray-500 text-sm">No enrollment bottlenecks identified.</p>
              )}
            </div>

            {/* Site Requirements & Feasibility Questions */}
            <div id="site-requirements" className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase tracking-wide">Site Requirements ({analysis.site_capability_requirements?.length || 0})</h3>
                {analysis.site_capability_requirements && analysis.site_capability_requirements.length > 0 ? (
                  <ul className="space-y-2">
                    {analysis.site_capability_requirements.map((req, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                        <span className="text-blue-500 mt-0.5">•</span>
                        {req}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-gray-500 text-sm">No specific site requirements identified.</p>
                )}
              </div>

              <div id="feasibility" className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase tracking-wide">Feasibility Questions ({analysis.feasibility_questions?.length || 0})</h3>
                {analysis.feasibility_questions && analysis.feasibility_questions.length > 0 ? (
                  <ul className="space-y-2">
                    {analysis.feasibility_questions.map((q, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                        <span className="text-gray-400 mt-0.5">?</span>
                        {q}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-gray-500 text-sm">No specific feasibility questions generated.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default OncologyProtocolIntelligence;
