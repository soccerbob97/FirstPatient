const API_BASE = '/api';

export interface Recommendation {
  investigator: {
    id: number;
    name: string;
  };
  site: {
    id: number;
    name: string;
    city: string | null;
    country: string | null;
  };
  link_type: string;
  scores: {
    similarity: number;
    total_trials: number;
    completion_rate: number;
    final: number;
  };
}

export interface RecommendationResponse {
  query: string;
  total_results: number;
  recommendations: Recommendation[];
}

export interface RecommendationRequest {
  query: string;
  phase?: string;
  country?: string;
  max_results?: number;
}

export async function getRecommendations(request: RecommendationRequest): Promise<RecommendationResponse> {
  const response = await fetch(`${API_BASE}/recommendations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

export interface Trial {
  id: number;
  nct_id: string;
  brief_title: string;
  phase: string;
  overall_status: string;
}

export async function getTrials(params: { search?: string; phase?: string; limit?: number } = {}): Promise<Trial[]> {
  const searchParams = new URLSearchParams();
  if (params.search) searchParams.set('search', params.search);
  if (params.phase) searchParams.set('phase', params.phase);
  if (params.limit) searchParams.set('limit', params.limit.toString());

  const response = await fetch(`${API_BASE}/trials?${searchParams}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}
