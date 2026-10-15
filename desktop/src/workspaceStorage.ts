import type { ConversationWindow, Outbox } from './types';

interface WorkspaceState { lastConversationId?: string | null; lastKb?: string; drafts?: Record<string, string>; outbox?: Outbox | null; windows?: ConversationWindow[]; activeWindowKey?: string }
const key = (home: string) => `miniima-workspace:${encodeURIComponent(home)}`;
export const draftKey = (kb: string, conversationId: string | null) => conversationId || `new:${kb}`;
export function readWorkspace(home: string): WorkspaceState {
  try {
    const saved = JSON.parse(localStorage.getItem(key(home)) || '{}');
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
  } catch { return {}; }
}
export function writeWorkspace(home: string, updates: Partial<WorkspaceState>) {
  try { localStorage.setItem(key(home), JSON.stringify({ ...readWorkspace(home), ...updates })); } catch { /* SQLite remains authoritative. */ }
}
export function draft(home: string, kb: string, conversationId: string | null) {
  const value = readWorkspace(home).drafts?.[draftKey(kb, conversationId)];
  return typeof value === 'string' ? value : '';
}
