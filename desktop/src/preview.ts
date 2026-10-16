import type { Bootstrap, ConversationDetail, KnowledgeBase, PublicSettings, Source, TrashItem } from './types';
import { referenceDocuments, referenceSources, referenceAnswer } from './referencePreview';

if (import.meta.env.DEV && new URLSearchParams(window.location.search).has('reference')) void import('./capture.css');
const reference = new URLSearchParams(window.location.search).has('reference');
const settings: PublicSettings = { base_url: 'https://api.deepseek.com', chat_model: 'deepseek-flash',
  embedding_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', embedding_model: 'qwen3.7-text-embedding',
  embedding_dimension: 1024, chunk_tokens: 500, chunk_overlap: 80, timeout: 30, max_retries: 2,
  embedding_batch_size: 20, retrieval_engine: 'cpp', min_score: .2, context_tokens: 4000,
  api_key_configured: true, embedding_api_key_configured: true, embedding_ready: true };
const base: KnowledgeBase = { id: 'network', name: '计算机网络', embedding_model: settings.embedding_model,
  embedding_dimension: 1024, embedding_base_url: settings.embedding_base_url, created_at: '2026-10-13' };
const source: Source = { id: 1, document_id: 'doc1', filename: 'network.md', content: '## TCP 三次握手\n\nTCP 用三次握手建立连接。客户端发送 SYN，服务器回复 SYN 与 ACK，客户端再发送 ACK。双方确认彼此的发送、接收能力，并交换初始序列号。',
  score: .9148, citation_number: 1, source_metadata: { line_start: 3, line_end: 7, heading_path: ['计算机网络笔记', 'TCP 三次握手'] } };
interface PreviewState { bases: KnowledgeBase[]; conversations: ConversationDetail[]; trash: TrashItem[] }
const storageKey = reference ? 'miniima-preview-reference-v2' : 'miniima-preview-v2';
const initialBases = reference ? ['全部文档', '计算机网络', '数据库系统', '人工智能', '科研资料', '课程笔记', '工作文档']
  .map((name, index) => ({ ...base, id: index ? 'reference-' + index : 'network', name }))
  : [base, { ...base, id: 'reading', name: '我的阅读笔记' }];
function readState(): PreviewState {
  try { const value = JSON.parse(localStorage.getItem(storageKey) || 'null'); if (value?.bases && value?.conversations && value?.trash) return value; } catch { /* Optional demo persistence. */ }
  return { bases: initialBases, conversations: [], trash: [] };
}
const state = readState();
function save() { try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch { /* Preview only. */ } }
function activeBases() { return state.bases.filter(kb => !state.trash.some(item => item.kind === 'kb' && item.id === kb.id)); }
function activeConversations() { return state.conversations.filter(conversation => activeBases().some(kb => kb.id === conversation.knowledge_base_id) && !state.trash.some(item => item.kind === 'conversation' && item.id === conversation.id)); }
const answer = reference ? referenceAnswer : 'TCP 三次握手的核心是**让双方确认连接可用，并同步初始序列号**。[1]\n\n1. 客户端发送 SYN，发起连接。\n2. 服务器回复 SYN + ACK，确认收到请求。\n3. 客户端发送 ACK，确认收到服务器的回应。\n\n第三次握手让服务器确认客户端已收到自己的初始序列号。';
const sources = reference ? referenceSources : [source];
const webSource: Source = { id: 'preview-web', chunk_id: null, document_id: 'web:preview', filename: 'TCP 规范 · RFC 9293',
  content: 'TCP 使用三次握手建立连接，同步双方的初始序列号。此处为开发预览的模拟网页摘要。', citation_number: 1,
  source_metadata: { kind: 'web', url: 'https://www.rfc-editor.org/rfc/rfc9293', retrieved_at: '2026-10-15T00:00:00Z',
    line_start: 0, line_end: 0, heading_path: ['TCP 规范 · RFC 9293'] } };

// Explicit development preview; never used by the packaged application.
export async function previewRequest(method: string, params: Record<string, unknown>): Promise<unknown> {
  await new Promise(resolve => setTimeout(resolve, 120));
  const snapshot = { saved: settings, effective: settings, overrides: [], home: reference ? 'preview:reference-v2' : 'preview:normal-v2' };
  switch (method) {
    case 'initialize': return { knowledge_bases: activeBases(), settings: snapshot } satisfies Bootstrap;
    case 'updates.check': return { current_version: '0.2.0', latest_version: '0.2.0', available: false, can_install: false };
    case 'updates.status': return { phase: 'idle', received: 0, total: 0 };
    case 'conversations.rename': {
      const item = activeConversations().find(item => item.id === params.conversation_id);
      const title = String(params.title || '').trim();
      if (!item || !title || title.length > 100) throw new Error('对话标题无效。');
      item.title = title; item.updated_at = new Date().toISOString(); save(); return structuredClone(item);
    }
    case 'kb.list': return activeBases();
    case 'kb.create': { const kb = { ...base, id: crypto.randomUUID(), name: String(params.name) }; state.bases.push(kb); save(); return kb; }
    case 'kb.delete': { const kb = activeBases().find(item => item.id === params.kb)!;
      state.trash.unshift({ kind: 'kb', id: kb.id, title: kb.name, knowledge_base_id: kb.id, knowledge_base_name: kb.name, deleted_at: new Date().toISOString() }); save(); return kb; }
    case 'docs.list': return params.kb === 'network' ? reference ? referenceDocuments : [
      { id: 'doc1', filename: 'network.md', status: 'ready', error: null, chunk_count: 8, source_type: 'markdown', created_at: '2026-10-13T10:30:00' },
      { id: 'doc2', filename: '以太网学习笔记.txt', status: 'ready', error: null, chunk_count: 5, source_type: 'txt', created_at: '2026-10-12T14:20:00' }] : [];
    case 'docs.preview': return sources.find(item => item.document_id === params.document_id) || sources[0];
    case 'search': return sources;
    case 'web.open': window.open(String(params.url), '_blank', 'noopener,noreferrer'); return { opened: true };
    case 'ask': return { text: answer, citations: sources, conversation_id: 'legacy-preview' };
    case 'conversations.list': { const term = String(params.query || '').trim().toLocaleLowerCase(); const items = activeConversations().filter(item => item.title.toLocaleLowerCase().includes(term)).sort((a, b) => b.updated_at.localeCompare(a.updated_at)); const offset = Number(params.offset || 0), limit = Number(params.limit || 50); return { items: items.slice(offset, offset + limit), total: items.length, has_more: offset + limit < items.length }; }
    case 'conversations.get': { const conversation = activeConversations().find(item => params.request_id ? item.messages.some(message => message.request_id === params.request_id) : item.id === params.conversation_id); if (!conversation) throw Error('对话不存在或已移入回收站。'); return conversation; }
    case 'conversations.send': {
      const previous = activeConversations().find(item => item.messages.some(message => message.request_id === params.request_id));
      if (previous) return structuredClone(previous);
      let conversation = activeConversations().find(item => item.id === params.conversation_id);
      if (!conversation) {
        const kb = activeBases().find(item => item.id === params.kb)!; const timestamp = new Date().toISOString();
        conversation = { id: crypto.randomUUID(), knowledge_base_id: kb.id, knowledge_base_name: kb.name, title: Array.from(String(params.question)).slice(0, 30).join(''), created_at: timestamp, updated_at: timestamp, message_count: 0, messages: [] };
        state.conversations.unshift(conversation);
      }
      if (conversation.messages.some(message => message.request_id === params.request_id)) return conversation;
      const userId = crypto.randomUUID(), position = conversation.messages.length;
      conversation.messages.push({ id: userId, conversation_id: conversation.id, role: 'user', content: String(params.question), position, status: 'completed', request_id: String(params.request_id), reply_to: null, error: null, citations: [], web_search: !!params.web_search });
      conversation.messages.push({ id: crypto.randomUUID(), conversation_id: conversation.id, role: 'assistant', content: params.web_search ? '根据联网搜索的模拟摘要，TCP 使用三次握手同步序列号。[1]' : position ? '结合前面的讨论，' + answer : answer, position: position + 1, status: 'completed', request_id: null, reply_to: userId, error: null, citations: (params.web_search ? [webSource] : sources).map(item => ({ ...item, id: crypto.randomUUID() })) });
      conversation.message_count = conversation.messages.length; conversation.updated_at = new Date().toISOString(); save(); return structuredClone(conversation);
    }
    case 'conversations.retry': {
      const conversation = activeConversations().find(item => item.messages.some(message => message.request_id === params.request_id));
      const user = conversation?.messages.find(message => message.request_id === params.request_id);
      if (!conversation || !user) throw Error('找不到需要重试的问题。');
      if (user.status === 'completed') return structuredClone(conversation);
      user.status = 'completed'; user.error = null;
      conversation.messages.push({ id: crypto.randomUUID(), conversation_id: conversation.id, role: 'assistant', content: user.web_search ? '根据联网搜索的模拟摘要，TCP 使用三次握手同步序列号。[1]' : answer,
        position: user.position + 1, status: 'completed', request_id: null, reply_to: user.id, error: null,
        citations: (user.web_search ? [webSource] : sources).map(item => ({ ...item, id: crypto.randomUUID() })) });
      conversation.messages.sort((a, b) => a.position - b.position);
      conversation.message_count = conversation.messages.length; conversation.updated_at = new Date().toISOString(); save(); return structuredClone(conversation);
    }
    case 'conversations.delete': { const conversation = activeConversations().find(item => item.id === params.conversation_id)!;
      state.trash.unshift({ kind: 'conversation', id: conversation.id, title: conversation.title, knowledge_base_id: conversation.knowledge_base_id, knowledge_base_name: conversation.knowledge_base_name, deleted_at: new Date().toISOString() }); save(); return { deleted: true }; }
    case 'trash.list': return state.trash;
    case 'trash.restore': {
      const item = state.trash.find(item => item.kind === params.kind && item.id === params.item_id)!;
      if (item.kind === 'conversation' && !activeBases().some(kb => kb.id === item.knowledge_base_id)) throw Error('请先恢复所属知识库，再恢复此对话。');
      state.trash = state.trash.filter(entry => entry !== item); save(); return { done: true };
    }
    case 'trash.purge': {
      if (params.kind === 'kb') { state.bases = state.bases.filter(kb => kb.id !== params.item_id); state.conversations = state.conversations.filter(item => item.knowledge_base_id !== params.item_id); state.trash = state.trash.filter(item => item.knowledge_base_id !== params.item_id); }
      else { state.conversations = state.conversations.filter(item => item.id !== params.item_id); state.trash = state.trash.filter(item => item.kind !== params.kind || item.id !== params.item_id); }
      save(); return { done: true };
    }
    case 'trash.empty': { for (const item of [...state.trash]) await previewRequest('trash.purge', { kind: item.kind, item_id: item.id }); return { done: true }; }
    case 'settings.get': return snapshot;
    case 'settings.qwen': return settings;
    case 'doctor': return { integrity: 'ok', foreign_key_errors: 0, engine: 'cpp' };
    default: throw Error('预览仅使用 Mock 数据，请在桌面应用中设置 API 或导入文档。');
  }
}
