export interface KnowledgeBase { id: string; name: string; embedding_model: string; embedding_dimension: number; embedding_base_url: string; created_at: string }
export interface DocumentRecord { id: string; filename: string; status: 'ready' | 'failed'; error: string | null; chunk_count: number; source_type: string; created_at: string }
export interface Source { id: number | string; chunk_id?: number | null; document_id: string; filename: string; content: string; score?: number; citation_number?: number; source_metadata: { line_start: number; line_end: number; heading_path: string[] } }
export interface Answer { text: string; citations: Source[]; conversation_id: string }
export interface PublicSettings {
  base_url: string; chat_model: string; embedding_base_url: string; embedding_model: string; embedding_dimension: number;
  chunk_tokens: number; chunk_overlap: number; timeout: number; max_retries: number; embedding_batch_size: number;
  retrieval_engine: string; min_score: number; context_tokens: number;
  api_key_configured: boolean; embedding_api_key_configured: boolean; embedding_ready: boolean;
}
export interface SettingsSnapshot { saved: PublicSettings; effective: PublicSettings; overrides: string[]; home: string }
export interface Bootstrap { knowledge_bases: KnowledgeBase[]; settings: SettingsSnapshot }
export interface ImportResult { document: DocumentRecord; imported: boolean }
export interface ConnectionResult { kind: string; connected: boolean; dimension?: number }
export interface ImportEntry { path: string; status: 'pending' | 'imported' | 'duplicate' | 'failed'; message?: string }
export interface ConversationSummary { id: string; knowledge_base_id: string; knowledge_base_name: string; title: string; created_at: string; updated_at: string; message_count: number }
export interface ChatMessage { id: string; conversation_id: string; role: 'user' | 'assistant'; content: string; position: number; status: 'pending' | 'completed' | 'failed' | 'interrupted'; request_id: string | null; reply_to: string | null; error: string | null; citations: Source[] }
export interface ConversationDetail extends ConversationSummary { messages: ChatMessage[] }
export interface ConversationPage { items: ConversationSummary[]; total: number; has_more: boolean }
export interface TrashItem { kind: 'kb' | 'conversation'; id: string; title: string; knowledge_base_name: string; knowledge_base_id: string; deleted_at: string }
export interface Outbox { kb: string; question: string; request_id: string; conversation_id?: string }
