import { useState, useCallback, useEffect, useRef } from 'react';
import { Sidebar } from './components/Sidebar';
import { SearchBar } from './components/SearchBar';
import { FilterPanel } from './components/FilterPanel';
import { RecommendationCard } from './components/RecommendationCard';
import { getRecommendations, type Recommendation } from './api/client';

// Phase detection patterns
const PHASE_PATTERNS: { pattern: RegExp; value: string }[] = [
  { pattern: /\b(early\s*phase\s*1|phase\s*1a|phase\s*1b)\b/i, value: 'EARLY_PHASE1' },
  { pattern: /\bphase\s*1\b/i, value: 'PHASE1' },
  { pattern: /\bphase\s*2\b/i, value: 'PHASE2' },
  { pattern: /\bphase\s*3\b/i, value: 'PHASE3' },
  { pattern: /\bphase\s*4\b/i, value: 'PHASE4' },
];

// Country detection patterns
const COUNTRY_PATTERNS: { pattern: RegExp; value: string }[] = [
  { pattern: /\b(united\s*states|usa|u\.s\.a\.|u\.s\.|america)\b/i, value: 'United States' },
  { pattern: /\bchina\b/i, value: 'China' },
  { pattern: /\bgermany\b/i, value: 'Germany' },
  { pattern: /\bfrance\b/i, value: 'France' },
  { pattern: /\b(united\s*kingdom|uk|u\.k\.|britain|england)\b/i, value: 'United Kingdom' },
  { pattern: /\bjapan\b/i, value: 'Japan' },
  { pattern: /\bcanada\b/i, value: 'Canada' },
  { pattern: /\baustralia\b/i, value: 'Australia' },
  { pattern: /\bitaly\b/i, value: 'Italy' },
  { pattern: /\bspain\b/i, value: 'Spain' },
];

function detectFiltersFromQuery(query: string): { phase: string; country: string } {
  let phase = '';
  let country = '';

  // Detect phase
  for (const { pattern, value } of PHASE_PATTERNS) {
    if (pattern.test(query)) {
      phase = value;
      break;
    }
  }

  // Detect country
  for (const { pattern, value } of COUNTRY_PATTERNS) {
    if (pattern.test(query)) {
      country = value;
      break;
    }
  }

  return { phase, country };
}

interface SearchHistoryItem {
  id: string;
  query: string;
  timestamp: Date;
  results: Recommendation[];
}

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [currentQuery, setCurrentQuery] = useState('');
  const [searchHistory, setSearchHistory] = useState<SearchHistoryItem[]>([]);
  const [phase, setPhase] = useState('');
  const [country, setCountry] = useState('');
  
  const isFirstRender = useRef(true);

  const executeSearch = useCallback(async (query: string, phaseFilter: string, countryFilter: string, addToHistory = true) => {
    if (!query.trim()) return;
    
    setIsLoading(true);
    setError(null);
    setCurrentQuery(query);

    try {
      const response = await getRecommendations({
        query,
        phase: phaseFilter || undefined,
        country: countryFilter || undefined,
        max_results: 10,
      });

      setRecommendations(response.recommendations);

      if (addToHistory) {
        const historyItem: SearchHistoryItem = {
          id: Date.now().toString(),
          query,
          timestamp: new Date(),
          results: response.recommendations,
        };
        setSearchHistory((prev) => [historyItem, ...prev.slice(0, 9)]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setRecommendations([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    
    if (currentQuery) {
      executeSearch(currentQuery, phase, country, false);
    }
  }, [phase, country]);

  const handleSearch = useCallback((query: string) => {
    // Auto-detect filters from query text
    const detected = detectFiltersFromQuery(query);
    
    // Use detected values, or keep existing if not detected
    const newPhase = detected.phase || phase;
    const newCountry = detected.country || country;
    
    // Update filter state if detected
    if (detected.phase) setPhase(detected.phase);
    if (detected.country) setCountry(detected.country);
    
    executeSearch(query, newPhase, newCountry, true);
  }, [executeSearch, phase, country]);

  const handleNewSearch = () => {
    setRecommendations([]);
    setCurrentQuery('');
    setError(null);
    setPhase('');
    setCountry('');
  };

  const handleSelectSearch = (id: string) => {
    const item = searchHistory.find((h) => h.id === id);
    if (item) {
      setCurrentQuery(item.query);
      setRecommendations(item.results);
    }
  };

  const hasResults = recommendations.length > 0;
  const showWelcome = !hasResults && !isLoading && !error && !currentQuery;

  return (
    <div className="flex h-screen bg-white">
      <Sidebar
        searchHistory={searchHistory}
        onNewSearch={handleNewSearch}
        onSelectSearch={handleSelectSearch}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Welcome State - Search bar centered in middle */}
        {showWelcome && (
          <div className="flex-1 flex flex-col items-center justify-center px-6">
            <h1 className="text-3xl font-semibold text-slate-800 mb-4 text-center">
              Find your ideal clinical trial team
            </h1>
            <p className="text-slate-500 mb-8 max-w-md mx-auto text-center">
              Describe your trial and we'll recommend the best Principal Investigators and sites based on experience and expertise.
            </p>
            <div className="w-full max-w-2xl">
              <SearchBar onSearch={handleSearch} isLoading={isLoading} />
            </div>
          </div>
        )}

        {/* Results State - Search bar at bottom */}
        {!showWelcome && (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Scrollable Results Area */}
            <div className="flex-1 overflow-y-auto">
              <div className="max-w-3xl mx-auto px-6 py-6 pb-4">
                {/* Results Header */}
                <div className="mb-4">
                  <h2 className="text-lg font-medium text-slate-700">
                    Results for "{currentQuery}"
                  </h2>
                  {hasResults && !isLoading && (
                    <p className="text-sm text-slate-500 mt-1">
                      Found {recommendations.length} recommendations
                    </p>
                  )}
                </div>

                {/* Error */}
                {error && (
                  <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
                    {error}
                  </div>
                )}

                {/* Loading */}
                {isLoading && (
                  <div className="text-center py-12">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-600 border-t-transparent"></div>
                    <p className="mt-4 text-slate-500">Finding the best matches...</p>
                  </div>
                )}

                {/* Results */}
                {hasResults && !isLoading && (
                  <div className="space-y-4">
                    {recommendations.map((rec, index) => (
                      <RecommendationCard
                        key={`${rec.investigator.id}-${rec.site.id}`}
                        recommendation={rec}
                        rank={index + 1}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Bottom Search Bar with Filters */}
            <div className="flex-shrink-0 bg-white">
              <div className="max-w-3xl mx-auto px-6 py-4">
                {/* Filters - above search bar, expanding upward */}
                <div className="mb-3">
                  <FilterPanel
                    phase={phase}
                    country={country}
                    onPhaseChange={setPhase}
                    onCountryChange={setCountry}
                  />
                </div>
                {/* Search Bar */}
                <SearchBar 
                  onSearch={handleSearch} 
                  isLoading={isLoading}
                  defaultValue={currentQuery}
                />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
