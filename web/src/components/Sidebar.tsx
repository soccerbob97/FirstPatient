import { PlusCircle, Clock, LogOut } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

interface SearchHistoryItem {
  id: string;
  query: string;
  timestamp: Date;
}

interface SidebarProps {
  searchHistory: SearchHistoryItem[];
  onNewSearch: () => void;
  onSelectSearch: (id: string) => void;
}

export function Sidebar({ searchHistory, onNewSearch, onSelectSearch }: SidebarProps) {
  const { user, signOut } = useAuth();

  return (
    <aside className="w-64 bg-slate-50 border-r border-slate-200 flex flex-col h-screen">
      {/* Logo */}
      <div className="p-4 border-b border-slate-200">
        <h1 className="text-xl font-semibold text-blue-600">FirstPatient</h1>
      </div>

      {/* New Search Button */}
      <div className="p-4">
        <button
          onClick={onNewSearch}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <PlusCircle size={18} />
          <span>New Search</span>
        </button>
      </div>

      {/* Search History */}
      <div className="flex-1 overflow-y-auto px-4">
        {searchHistory.length > 0 && (
          <>
            <div className="flex items-center gap-2 text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">
              <Clock size={14} />
              <span>Recent Searches</span>
            </div>
            <ul className="space-y-1">
              {searchHistory.map((item) => (
                <li key={item.id}>
                  <button
                    onClick={() => onSelectSearch(item.id)}
                    className="w-full text-left px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 rounded-lg truncate transition-colors"
                  >
                    {item.query}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {/* Bottom Navigation */}
      <div className="p-4 border-t border-slate-200 space-y-1">
        {/* User Profile */}
        {user && (
          <div className="flex items-center gap-3 px-3 py-2 mb-2">
            {user.user_metadata?.avatar_url ? (
              <img 
                src={user.user_metadata.avatar_url} 
                alt="Profile" 
                className="w-8 h-8 rounded-full"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-medium text-sm">
                {(user.email?.[0] || 'U').toUpperCase()}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-700 truncate">
                {user.user_metadata?.full_name || user.email?.split('@')[0]}
              </p>
              <p className="text-xs text-slate-500 truncate">{user.email}</p>
            </div>
          </div>
        )}
        
        <button 
          onClick={() => signOut()}
          className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
        >
          <LogOut size={18} />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
}
