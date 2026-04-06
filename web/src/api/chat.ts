const API_BASE = 'http://localhost:8000/api';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  recommendations?: Recommendation[];
  timestamp?: Date;
}

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

export interface ChatResponse {
  message: string;
  recommendations: Recommendation[] | null;
  conversation_id: string | null;
}

export async function sendChatMessage(
  messages: { role: string; content: string }[],
  filters?: { phase?: string; country?: string }
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ messages, filters }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to send message');
  }

  return response.json();
}

// Conversation persistence API
export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export async function listConversations(): Promise<{ conversations: ConversationSummary[], error?: string }> {
  const response = await fetch(`${API_BASE}/conversations`);
  if (!response.ok) {
    throw new Error('Failed to list conversations');
  }
  return response.json();
}

export async function getConversation(conversationId: string): Promise<{
  conversation: ConversationSummary;
  messages: ChatMessage[];
}> {
  const response = await fetch(`${API_BASE}/conversations/${conversationId}`);
  if (!response.ok) {
    throw new Error('Failed to get conversation');
  }
  return response.json();
}

export async function saveConversation(
  title: string,
  messages: ChatMessage[]
): Promise<{ conversation_id: string }> {
  const response = await fetch(`${API_BASE}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      messages: messages.map(m => ({
        role: m.role,
        content: m.content,
        metadata: m.recommendations ? { recommendations: m.recommendations } : {}
      }))
    }),
  });
  if (!response.ok) {
    throw new Error('Failed to save conversation');
  }
  return response.json();
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/conversations/${conversationId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error('Failed to delete conversation');
  }
}

export async function* streamChatMessage(
  messages: { role: string; content: string }[]
): AsyncGenerator<{ type: string; data: any }> {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ messages }),
  });

  if (!response.ok) {
    throw new Error('Failed to stream message');
  }

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) {
    throw new Error('No response body');
  }

  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          yield data;
        } catch {
          // Ignore parse errors
        }
      }
    }
  }
}
