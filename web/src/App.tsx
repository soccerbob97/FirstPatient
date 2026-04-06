import { useState, useCallback, useRef, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { SearchBar } from './components/SearchBar';
import { ChatMessage } from './components/ChatMessage';
import { FilterPanel } from './components/FilterPanel';
import { 
  sendChatMessage, 
  listConversations,
  getConversation,
  saveConversation,
  type ChatMessage as ChatMessageType
} from './api/chat';

interface Conversation {
  id: string;
  title: string;
  messages: ChatMessageType[];
  timestamp: Date;
}

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [dbAvailable, setDbAvailable] = useState(false);
  const [phase, setPhase] = useState('');
  const [country, setCountry] = useState('');
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load conversations from server on mount
  useEffect(() => {
    async function loadConversations() {
      try {
        const result = await listConversations();
        if (!result.error && result.conversations.length > 0) {
          setDbAvailable(true);
          setConversations(result.conversations.map(c => ({
            id: c.id,
            title: c.title,
            messages: [],
            timestamp: new Date(c.updated_at)
          })));
        }
      } catch {
        // DB tables don't exist yet, use in-memory only
        setDbAvailable(false);
      }
    }
    loadConversations();
  }, []);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Extract filters from query text
  const extractFiltersFromQuery = (query: string) => {
    const lowerQuery = query.toLowerCase();
    
    // Country detection
    const countryPatterns: Record<string, string> = {
      'united states': 'United States',
      'us': 'United States',
      'usa': 'United States',
      'united kingdom': 'United Kingdom',
      'uk': 'United Kingdom',
      'germany': 'Germany',
      'france': 'France',
      'japan': 'Japan',
      'china': 'China',
      'canada': 'Canada',
      'australia': 'Australia',
    };
    
    // Phase detection
    const phasePatterns: Record<string, string> = {
      'phase 1': 'PHASE1',
      'phase1': 'PHASE1',
      'phase i': 'PHASE1',
      'phase 2': 'PHASE2',
      'phase2': 'PHASE2',
      'phase ii': 'PHASE2',
      'phase 3': 'PHASE3',
      'phase3': 'PHASE3',
      'phase iii': 'PHASE3',
      'phase 4': 'PHASE4',
      'phase4': 'PHASE4',
      'phase iv': 'PHASE4',
      'early phase': 'EARLY_PHASE1',
    };
    
    let detectedCountry: string | undefined;
    let detectedPhase: string | undefined;
    
    for (const [pattern, value] of Object.entries(countryPatterns)) {
      if (lowerQuery.includes(pattern)) {
        detectedCountry = value;
        break;
      }
    }
    
    for (const [pattern, value] of Object.entries(phasePatterns)) {
      if (lowerQuery.includes(pattern)) {
        detectedPhase = value;
        break;
      }
    }
    
    return { country: detectedCountry, phase: detectedPhase };
  };

  const handleSendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isLoading) return;

    // Extract and set filters from query
    const extractedFilters = extractFiltersFromQuery(content);
    if (extractedFilters.country) setCountry(extractedFilters.country);
    if (extractedFilters.phase) setPhase(extractedFilters.phase);

    // Add user message
    const userMessage: ChatMessageType = {
      role: 'user',
      content,
      timestamp: new Date(),
    };
    
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    try {
      // Build message history for API
      const apiMessages = [...messages, userMessage].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      // Use extracted filters or existing state
      const filters = { 
        phase: extractedFilters.phase || phase || undefined, 
        country: extractedFilters.country || country || undefined 
      };
      const response = await sendChatMessage(apiMessages, filters);

      // Add assistant message
      const assistantMessage: ChatMessageType = {
        role: 'assistant',
        content: response.message,
        recommendations: response.recommendations || undefined,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);

      // Update conversation history
      const allMessages = [...messages, userMessage, assistantMessage];
      if (!currentConversationId) {
        const title = content.slice(0, 50) + (content.length > 50 ? '...' : '');
        const localId = Date.now().toString();
        
        const newConversation: Conversation = {
          id: localId,
          title,
          messages: allMessages,
          timestamp: new Date(),
        };
        setConversations((prev) => [newConversation, ...prev]);
        setCurrentConversationId(localId);
        
        // Try to save to server if DB is available
        if (dbAvailable) {
          try {
            const result = await saveConversation(title, allMessages);
            // Update with server ID
            setConversations((prev) => prev.map(c => 
              c.id === localId ? { ...c, id: result.conversation_id } : c
            ));
            setCurrentConversationId(result.conversation_id);
          } catch {
            // Keep using local ID
          }
        }
      } else {
        setConversations((prev) =>
          prev.map((c) =>
            c.id === currentConversationId
              ? { ...c, messages: allMessages }
              : c
          )
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  }, [messages, isLoading, currentConversationId, dbAvailable]);

  const handleNewChat = () => {
    setMessages([]);
    setCurrentConversationId(null);
    setError(null);
  };

  const handleSelectConversation = async (id: string) => {
    // First check local cache
    const localConv = conversations.find((c) => c.id === id);
    if (localConv && localConv.messages.length > 0) {
      setMessages(localConv.messages);
      setCurrentConversationId(id);
      return;
    }
    
    // Try to load from server if DB is available
    if (dbAvailable) {
      try {
        const result = await getConversation(id);
        const loadedMessages = result.messages.map(m => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          recommendations: (m as any).metadata?.recommendations,
          timestamp: new Date((m as any).created_at)
        }));
        setMessages(loadedMessages);
        setCurrentConversationId(id);
        
        // Update local cache
        setConversations(prev => prev.map(c => 
          c.id === id ? { ...c, messages: loadedMessages } : c
        ));
      } catch {
        // Fall back to local
        if (localConv) {
          setMessages(localConv.messages);
          setCurrentConversationId(id);
        }
      }
    } else if (localConv) {
      setMessages(localConv.messages);
      setCurrentConversationId(id);
    }
  };

  const showWelcome = messages.length === 0 && !isLoading;

  // Convert conversations to search history format for Sidebar
  const searchHistory = conversations.map((c) => ({
    id: c.id,
    query: c.title,
    timestamp: c.timestamp,
    results: c.messages.find((m) => m.recommendations)?.recommendations || [],
  }));

  return (
    <div className="flex h-screen bg-white">
      <Sidebar
        searchHistory={searchHistory}
        onNewSearch={handleNewChat}
        onSelectSearch={handleSelectConversation}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Welcome State */}
        {showWelcome && (
          <div className="flex-1 flex flex-col items-center justify-center px-6">
            <h1 className="text-3xl font-semibold text-slate-800 mb-4 text-center">
              Find your ideal clinical trial team
            </h1>
            <p className="text-slate-500 mb-8 max-w-md mx-auto text-center">
              Ask me about finding Principal Investigators and sites for your clinical trial. I can help you search, compare options, and get detailed information.
            </p>
            <div className="w-full max-w-2xl">
              <SearchBar onSearch={handleSendMessage} isLoading={isLoading} placeholder="Ask about PIs, sites, or clinical trials..." />
            </div>
            <div className="mt-6 flex flex-wrap gap-2 justify-center max-w-xl">
              {[
                'Phase 2 diabetes trial in the US',
                'Oncology investigators in Germany',
                'Compare top cardiology sites',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => handleSendMessage(suggestion)}
                  className="px-3 py-1.5 text-sm bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Chat State */}
        {!showWelcome && (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto">
              <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
                {messages.map((message, index) => (
                  <ChatMessage key={index} message={message} />
                ))}

                {/* Loading indicator */}
                {isLoading && (
                  <div className="flex gap-4">
                    <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center">
                      <div className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
                    </div>
                    <div className="bg-slate-100 rounded-2xl rounded-bl-md px-4 py-3">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </div>
                )}

                {/* Error */}
                {error && (
                  <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
                    {error}
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Bottom Input with Filters */}
            <div className="flex-shrink-0 bg-white border-t border-slate-200">
              <div className="max-w-3xl mx-auto px-6 py-4 space-y-3">
                <FilterPanel
                  phase={phase}
                  country={country}
                  onPhaseChange={setPhase}
                  onCountryChange={setCountry}
                />
                <SearchBar
                  onSearch={handleSendMessage}
                  isLoading={isLoading}
                  placeholder="Ask a follow-up question..."
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
