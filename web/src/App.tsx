import { useState, useCallback, useRef, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { SearchBar } from './components/SearchBar';
import { ChatMessage } from './components/ChatMessage';
import { FilterPanel } from './components/FilterPanel';
import { LoginPage } from './components/LoginPage';
import { useAuth } from './contexts/AuthContext';
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

// Main App component handles auth state
function App() {
  const { user, loading: authLoading } = useAuth();

  // Show loading while checking auth
  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Show login page if not authenticated
  if (!user) {
    return <LoginPage />;
  }

  // User is authenticated, show the chat interface
  return <ChatApp />;
}

// ChatApp component contains all the chat logic and hooks
function ChatApp() {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [dbAvailable, setDbAvailable] = useState(false);
  const [phase, setPhase] = useState('');
  const [country, setCountry] = useState('');
  const [lastQuery, setLastQuery] = useState('');
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const shouldScrollRef = useRef(false);

  // Load conversations from server on mount (only when user is authenticated)
  useEffect(() => {
    async function loadConversations() {
      try {
        console.log('Loading conversations for user:', user?.email);
        const result = await listConversations();
        console.log('Conversations loaded:', result);
        if (!result.error && result.conversations.length > 0) {
          setDbAvailable(true);
          setConversations(result.conversations.map(c => ({
            id: c.id,
            title: c.title,
            messages: [],
            timestamp: new Date(c.updated_at)
          })));
        } else {
          setDbAvailable(true); // DB exists but no conversations yet
        }
      } catch (err) {
        console.error('Error loading conversations:', err);
        // DB tables don't exist yet, use in-memory only
        setDbAvailable(false);
      }
    }
    if (user) {
      loadConversations();
    }
  }, [user]);

  // Disabled auto-scroll - user controls their own scrolling
  // useEffect(() => {
  //   if (shouldScrollRef.current) {
  //     messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  //     shouldScrollRef.current = false;
  //   }
  // }, [messages]);

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

    // Extract filters from query - reset filters if not mentioned in new query
    const extractedFilters = extractFiltersFromQuery(content);
    const newPhase = extractedFilters.phase || '';
    const newCountry = extractedFilters.country || '';
    setPhase(newPhase);
    setCountry(newCountry);
    setLastQuery(content);

    // Add user message
    const userMessage: ChatMessageType = {
      role: 'user',
      content,
      timestamp: new Date(),
    };
    
    shouldScrollRef.current = true; // Enable scroll for user-initiated messages
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    try {
      // Build message history for API
      const apiMessages = [...messages, userMessage].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      // Use only the filters extracted from this query (not persisted state)
      const filters = { 
        phase: newPhase || undefined, 
        country: newCountry || undefined 
      };
      const response = await sendChatMessage(apiMessages, filters);

      // Add assistant message
      const assistantMessage: ChatMessageType = {
        role: 'assistant',
        content: response.message,
        recommendations: response.recommendations || undefined,
        timestamp: new Date(),
      };

      shouldScrollRef.current = true; // Scroll to show assistant response
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
  }, [messages, isLoading, currentConversationId, dbAvailable, phase, country]);

  const handleNewChat = () => {
    setMessages([]);
    setCurrentConversationId(null);
    setError(null);
    setPhase('');
    setCountry('');
    setLastQuery('');
  };

  // Re-run search when filters change (if there's a previous query)
  const handleFilterChange = useCallback((newPhase: string, newCountry: string) => {
    setPhase(newPhase);
    setCountry(newCountry);
    
    // If we have a previous query and messages, re-run the search with new filters
    if (lastQuery && messages.length > 0 && !isLoading) {
      // Re-submit with updated filters
      handleSendMessageWithFilters(lastQuery, newPhase, newCountry);
    }
  }, [lastQuery, messages.length, isLoading]);

  const handleSendMessageWithFilters = useCallback(async (content: string, filterPhase: string, filterCountry: string) => {
    if (!content.trim() || isLoading) return;

    // Add user message showing filter change
    const userMessage: ChatMessageType = {
      role: 'user',
      content: `[Filter updated] ${content}`,
      timestamp: new Date(),
    };
    
    shouldScrollRef.current = true;
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    try {
      const apiMessages = [...messages, userMessage].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const filters = { 
        phase: filterPhase || undefined, 
        country: filterCountry || undefined 
      };
      const response = await sendChatMessage(apiMessages, filters);

      const assistantMessage: ChatMessageType = {
        role: 'assistant',
        content: response.message,
        recommendations: response.recommendations || undefined,
        timestamp: new Date(),
      };

      shouldScrollRef.current = true;
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  }, [messages, isLoading]);

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
                'Diabetes type 2 clinical study',
                'Phase 2 breast cancer trial',
                'Obesity trial in the US',
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
                  onPhaseChange={(p) => handleFilterChange(p, country)}
                  onCountryChange={(c) => handleFilterChange(phase, c)}
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
