import React, { useState, useCallback } from 'react';

interface ScoreBreakdown {
  score: number;
  factors: Array<{ name: string; value: any; impact: number }>;
  recommendations: string[];
}

interface ProtocolScores {
  overall_complexity: number;
  enrollment_difficulty: ScoreBreakdown;
  site_burden: ScoreBreakdown;
  operational_complexity: ScoreBreakdown;
  amendment_risk: ScoreBreakdown;
  monitoring_complexity: ScoreBreakdown;
  patient_burden: ScoreBreakdown;
  estimated_enrollment_rate: number;
  estimated_screen_fail_rate: number;
  recommended_site_profile: Record<string, any>;
  recommended_pi_profile: Record<string, any>;
}

interface ProtocolAnalysis {
  success: boolean;
  protocol_id: string;
  metadata: Record<string, any>;
  eligibility: Record<string, any>;
  study_design: Record<string, any>;
  scores: ProtocolScores;
  feasibility_summary?: Record<string, any>;
  recommendations?: {
    recommended_pis: Array<{
      full_name: string;
      institution: string;
      match_score: number;
      match_reasons: string[];
    }>;
    execution_recommendations: string[];
  };
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const ScoreGauge: React.FC<{ score: number; label: string; size?: 'sm' | 'lg' }> = ({ 
  score, 
  label, 
  size = 'sm' 
}) => {
  const getColor = (s: number) => {
    if (s < 40) return '#22c55e'; // green
    if (s < 60) return '#eab308'; // yellow
    if (s < 80) return '#f97316'; // orange
    return '#ef4444'; // red
  };

  const radius = size === 'lg' ? 60 : 40;
  const strokeWidth = size === 'lg' ? 10 : 6;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center">
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
      <div className="absolute flex flex-col items-center justify-center" style={{
        width: radius * 2,
        height: radius * 2,
        marginTop: strokeWidth
      }}>
        <span className={`font-bold ${size === 'lg' ? 'text-2xl' : 'text-lg'}`}>
          {score.toFixed(0)}
        </span>
      </div>
      <span className={`mt-2 text-center ${size === 'lg' ? 'text-sm font-medium' : 'text-xs'} text-gray-600`}>
        {label}
      </span>
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
    if (score < 40) return 'text-green-600 bg-green-50';
    if (score < 60) return 'text-yellow-600 bg-yellow-50';
    if (score < 80) return 'text-orange-600 bg-orange-50';
    return 'text-red-600 bg-red-50';
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <span className="font-medium text-gray-800">{title}</span>
        <div className="flex items-center gap-3">
          <span className={`px-3 py-1 rounded-full text-sm font-semibold ${getScoreColor(breakdown.score)}`}>
            {breakdown.score.toFixed(0)}
          </span>
          <svg 
            className={`w-5 h-5 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>
      
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-100">
          <div className="mt-3">
            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Contributing Factors</h4>
            <div className="space-y-2">
              {breakdown.factors.map((factor, idx) => (
                <div key={idx} className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">{factor.name}</span>
                  <span className={`font-medium ${factor.impact > 10 ? 'text-red-600' : 'text-gray-800'}`}>
                    +{factor.impact}
                  </span>
                </div>
              ))}
            </div>
          </div>
          
          {breakdown.recommendations.length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Recommendations</h4>
              <ul className="space-y-1">
                {breakdown.recommendations.map((rec, idx) => (
                  <li key={idx} className="text-sm text-gray-600 flex items-start gap-2">
                    <span className="text-blue-500 mt-1">•</span>
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

const QuickScoreForm: React.FC<{ onAnalyze: (data: any) => void; loading: boolean }> = ({ 
  onAnalyze, 
  loading 
}) => {
  const [formData, setFormData] = useState({
    phase: 'Phase 2',
    therapeutic_area: 'Oncology',
    indication: '',
    inclusion_criteria_count: 10,
    exclusion_criteria_count: 10,
    requires_biomarker: false,
    requires_prior_therapy: false,
    number_of_arms: 2,
    blinding: 'double-blind',
    treatment_duration_weeks: 24,
    adaptive_design: false,
    dose_escalation: false,
    total_visits: 12,
    imaging_modalities: 2,
    pk_sampling: false,
    pk_timepoints: 0,
    biopsies_required: false,
    dsmb_required: true,
    cardiac_monitoring: false,
    target_enrollment: 200
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAnalyze(formData);
  };

  const updateField = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Basic Info */}
        <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
          <h3 className="font-semibold text-gray-800">Study Information</h3>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Phase</label>
            <select
              value={formData.phase}
              onChange={(e) => updateField('phase', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            >
              <option>Phase 1</option>
              <option>Phase 1/2</option>
              <option>Phase 2</option>
              <option>Phase 2/3</option>
              <option>Phase 3</option>
              <option>Phase 4</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Therapeutic Area</label>
            <select
              value={formData.therapeutic_area}
              onChange={(e) => updateField('therapeutic_area', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            >
              <option>Oncology</option>
              <option>Cardiology</option>
              <option>Neurology</option>
              <option>Immunology</option>
              <option>Infectious Disease</option>
              <option>Rare Disease</option>
              <option>Endocrinology</option>
              <option>Gastroenterology</option>
              <option>Respiratory</option>
              <option>Dermatology</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Target Enrollment</label>
            <input
              type="number"
              value={formData.target_enrollment}
              onChange={(e) => updateField('target_enrollment', parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* Eligibility */}
        <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
          <h3 className="font-semibold text-gray-800">Eligibility Criteria</h3>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Inclusion Criteria Count
            </label>
            <input
              type="number"
              value={formData.inclusion_criteria_count}
              onChange={(e) => updateField('inclusion_criteria_count', parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Exclusion Criteria Count
            </label>
            <input
              type="number"
              value={formData.exclusion_criteria_count}
              onChange={(e) => updateField('exclusion_criteria_count', parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="biomarker"
              checked={formData.requires_biomarker}
              onChange={(e) => updateField('requires_biomarker', e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded"
            />
            <label htmlFor="biomarker" className="text-sm text-gray-700">
              Requires Biomarker Testing
            </label>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="prior_therapy"
              checked={formData.requires_prior_therapy}
              onChange={(e) => updateField('requires_prior_therapy', e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded"
            />
            <label htmlFor="prior_therapy" className="text-sm text-gray-700">
              Requires Prior Therapy
            </label>
          </div>
        </div>

        {/* Study Design */}
        <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
          <h3 className="font-semibold text-gray-800">Study Design</h3>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Number of Arms</label>
            <input
              type="number"
              value={formData.number_of_arms}
              onChange={(e) => updateField('number_of_arms', parseInt(e.target.value))}
              min={1}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Blinding</label>
            <select
              value={formData.blinding}
              onChange={(e) => updateField('blinding', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            >
              <option value="open-label">Open Label</option>
              <option value="single-blind">Single Blind</option>
              <option value="double-blind">Double Blind</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Treatment Duration (weeks)
            </label>
            <input
              type="number"
              value={formData.treatment_duration_weeks}
              onChange={(e) => updateField('treatment_duration_weeks', parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="dose_escalation"
              checked={formData.dose_escalation}
              onChange={(e) => updateField('dose_escalation', e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded"
            />
            <label htmlFor="dose_escalation" className="text-sm text-gray-700">
              Dose Escalation
            </label>
          </div>
        </div>

        {/* Visits & Assessments */}
        <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
          <h3 className="font-semibold text-gray-800">Visits & Assessments</h3>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Total Visits</label>
            <input
              type="number"
              value={formData.total_visits}
              onChange={(e) => updateField('total_visits', parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Imaging Modalities
            </label>
            <input
              type="number"
              value={formData.imaging_modalities}
              onChange={(e) => updateField('imaging_modalities', parseInt(e.target.value))}
              min={0}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="pk_sampling"
              checked={formData.pk_sampling}
              onChange={(e) => updateField('pk_sampling', e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded"
            />
            <label htmlFor="pk_sampling" className="text-sm text-gray-700">
              PK Sampling Required
            </label>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="biopsies"
              checked={formData.biopsies_required}
              onChange={(e) => updateField('biopsies_required', e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded"
            />
            <label htmlFor="biopsies" className="text-sm text-gray-700">
              Biopsies Required
            </label>
          </div>
        </div>

        {/* Safety */}
        <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
          <h3 className="font-semibold text-gray-800">Safety Monitoring</h3>
          
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="dsmb"
              checked={formData.dsmb_required}
              onChange={(e) => updateField('dsmb_required', e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded"
            />
            <label htmlFor="dsmb" className="text-sm text-gray-700">
              DSMB Required
            </label>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="cardiac"
              checked={formData.cardiac_monitoring}
              onChange={(e) => updateField('cardiac_monitoring', e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded"
            />
            <label htmlFor="cardiac" className="text-sm text-gray-700">
              Cardiac Monitoring
            </label>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="adaptive"
              checked={formData.adaptive_design}
              onChange={(e) => updateField('adaptive_design', e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded"
            />
            <label htmlFor="adaptive" className="text-sm text-gray-700">
              Adaptive Design
            </label>
          </div>
        </div>
      </div>

      <div className="flex justify-center">
        <button
          type="submit"
          disabled={loading}
          className="px-8 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {loading ? (
            <>
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Analyzing...
            </>
          ) : (
            <>
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Analyze Protocol
            </>
          )}
        </button>
      </div>
    </form>
  );
};

const ProtocolIntelligence: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'quick' | 'pdf' | 'sample'>('quick');
  const [analysis, setAnalysis] = useState<ProtocolAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedScores, setExpandedScores] = useState<Set<string>>(new Set());
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  const toggleScore = (key: string) => {
    setExpandedScores(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleQuickScore = async (formData: any) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/protocol/quick-score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      
      if (!response.ok) {
        throw new Error('Analysis failed');
      }
      
      const data = await response.json();
      setAnalysis({
        success: true,
        protocol_id: 'Quick Analysis',
        metadata: {
          phase: formData.phase,
          therapeutic_area: formData.therapeutic_area,
          target_enrollment: formData.target_enrollment
        },
        eligibility: {},
        study_design: {},
        scores: data
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const handlePdfUpload = async () => {
    if (!pdfFile) return;
    
    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', pdfFile);
      formData.append('include_recommendations', 'true');
      
      const response = await fetch(`${API_BASE}/api/protocol/analyze-pdf`, {
        method: 'POST',
        body: formData
      });
      
      if (!response.ok) {
        throw new Error('PDF analysis failed');
      }
      
      const data = await response.json();
      setAnalysis(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PDF analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const loadSampleAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/protocol/sample-analysis`);
      if (!response.ok) {
        throw new Error('Failed to load sample');
      }
      const data = await response.json();
      setAnalysis(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sample');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Protocol Intelligence</h1>
          <p className="mt-2 text-gray-600">
            Analyze clinical trial protocols to assess operational complexity, predict enrollment challenges, 
            and get recommendations for site and PI selection.
          </p>
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-lg shadow-sm mb-6">
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              <button
                onClick={() => setActiveTab('quick')}
                className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'quick'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                Quick Score
              </button>
              <button
                onClick={() => setActiveTab('pdf')}
                className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'pdf'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                Upload PDF
              </button>
              <button
                onClick={() => { setActiveTab('sample'); loadSampleAnalysis(); }}
                className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'sample'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                Sample Analysis
              </button>
            </nav>
          </div>

          <div className="p-6">
            {activeTab === 'quick' && (
              <QuickScoreForm onAnalyze={handleQuickScore} loading={loading} />
            )}

            {activeTab === 'pdf' && (
              <div className="space-y-4">
                <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={(e) => setPdfFile(e.target.files?.[0] || null)}
                    className="hidden"
                    id="pdf-upload"
                  />
                  <label htmlFor="pdf-upload" className="cursor-pointer">
                    <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <p className="mt-2 text-sm text-gray-600">
                      {pdfFile ? pdfFile.name : 'Click to upload or drag and drop'}
                    </p>
                    <p className="mt-1 text-xs text-gray-500">PDF up to 50MB</p>
                  </label>
                </div>
                
                {pdfFile && (
                  <div className="flex justify-center">
                    <button
                      onClick={handlePdfUpload}
                      disabled={loading}
                      className="px-8 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                    >
                      {loading ? 'Analyzing PDF...' : 'Analyze Protocol'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'sample' && loading && (
              <div className="flex justify-center py-12">
                <svg className="animate-spin h-8 w-8 text-blue-600" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
            )}
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        {/* Results */}
        {analysis && (
          <div className="space-y-6">
            {/* Protocol Summary */}
            <div className="bg-white rounded-lg shadow-sm p-6">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">
                    {analysis.metadata.protocol_title || analysis.protocol_id}
                  </h2>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {analysis.metadata.phase && (
                      <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">
                        {analysis.metadata.phase}
                      </span>
                    )}
                    {analysis.metadata.therapeutic_area && (
                      <span className="px-3 py-1 bg-purple-100 text-purple-800 rounded-full text-sm">
                        {analysis.metadata.therapeutic_area}
                      </span>
                    )}
                    {analysis.metadata.sponsor && (
                      <span className="px-3 py-1 bg-gray-100 text-gray-800 rounded-full text-sm">
                        {analysis.metadata.sponsor}
                      </span>
                    )}
                  </div>
                </div>
                
                <div className="relative">
                  <ScoreGauge 
                    score={analysis.scores.overall_complexity} 
                    label="Overall Complexity" 
                    size="lg"
                  />
                </div>
              </div>
            </div>

            {/* Key Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="text-sm text-gray-500 mb-1">Est. Enrollment Rate</div>
                <div className="text-2xl font-bold text-gray-900">
                  {analysis.scores.estimated_enrollment_rate} pts/site/mo
                </div>
              </div>
              <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="text-sm text-gray-500 mb-1">Est. Screen Fail Rate</div>
                <div className="text-2xl font-bold text-gray-900">
                  {analysis.scores.estimated_screen_fail_rate}%
                </div>
              </div>
              <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="text-sm text-gray-500 mb-1">Recommended Sites</div>
                <div className="text-2xl font-bold text-gray-900">
                  {analysis.feasibility_summary?.recommended_site_count || 
                   Math.ceil((analysis.metadata.target_enrollment || 100) / 
                   (analysis.scores.estimated_enrollment_rate * 12))}
                </div>
              </div>
            </div>

            {/* Score Breakdown */}
            <div className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Score Breakdown</h3>
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
                  title="Operational Complexity"
                  breakdown={analysis.scores.operational_complexity}
                  expanded={expandedScores.has('operational')}
                  onToggle={() => toggleScore('operational')}
                />
                <ScoreCard
                  title="Amendment Risk"
                  breakdown={analysis.scores.amendment_risk}
                  expanded={expandedScores.has('amendment')}
                  onToggle={() => toggleScore('amendment')}
                />
                <ScoreCard
                  title="Monitoring Complexity"
                  breakdown={analysis.scores.monitoring_complexity}
                  expanded={expandedScores.has('monitoring')}
                  onToggle={() => toggleScore('monitoring')}
                />
                <ScoreCard
                  title="Patient Burden"
                  breakdown={analysis.scores.patient_burden}
                  expanded={expandedScores.has('patient')}
                  onToggle={() => toggleScore('patient')}
                />
              </div>
            </div>

            {/* Recommendations */}
            {analysis.recommendations && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Execution Recommendations</h3>
                <ul className="space-y-2">
                  {analysis.recommendations.execution_recommendations?.map((rec, idx) => (
                    <li key={idx} className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center text-sm font-medium">
                        {idx + 1}
                      </span>
                      <span className="text-gray-700">{rec}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Matching PIs */}
            {analysis.recommendations?.recommended_pis && analysis.recommendations.recommended_pis.length > 0 && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Recommended Investigators</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {analysis.recommendations.recommended_pis.slice(0, 6).map((pi, idx) => (
                    <div key={idx} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-start justify-between">
                        <div>
                          <h4 className="font-medium text-gray-900">{pi.full_name}</h4>
                          <p className="text-sm text-gray-500">{pi.institution}</p>
                        </div>
                        <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-sm font-medium">
                          {pi.match_score.toFixed(0)}%
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {pi.match_reasons.slice(0, 3).map((reason, ridx) => (
                          <span key={ridx} className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                            {reason}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ProtocolIntelligence;
