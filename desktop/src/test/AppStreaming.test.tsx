import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import App from '../App';
import type { ConversationDetail, SettingsSnapshot, TurnEvent } from '../types';

const bridge = vi.hoisted(() => ({ request: vi.fn(), streamRequest: vi.fn(), exportConversation: vi.fn(),
  chooseFiles: vi.fn(), confirmAction: vi.fn(), windowAction: vi.fn(), getUpdateInfo: vi.fn(),
  prepareUpdate: vi.fn(), installUpdate: vi.fn() }));
vi.mock('../bridge', () => ({ ...bridge, errorMessage: String, handleWindowClose: async () => () => {} }));
const settings = { base_url: 'https://example.org', chat_model: 'test', embedding_base_url: 'https://example.org',
  embedding_model: 'embed', embedding_dimension: 8, chunk_tokens: 500, chunk_overlap: 80, timeout: 30,
  max_retries: 2, embedding_batch_size: 20, retrieval_engine: 'numpy', min_score: .2, context_tokens: 4000,
  api_key_configured: true, embedding_api_key_configured: true, embedding_ready: true };
const snapshot: SettingsSnapshot = { home: 'preview:stream-test', saved: settings, effective: settings, overrides: [] };
let conversation: ConversationDetail;
let emit: (event: TurnEvent) => void;
let finish: (detail: ConversationDetail) => void;

beforeEach(() => {
  localStorage.clear(); vi.clearAllMocks();
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
  conversation = { id: 'saved', title: '已有对话', knowledge_base_id: 'kb', knowledge_base_name: '资料', created_at: '', updated_at: '', message_count: 2,
    messages: [{ id: 'u1', conversation_id: 'saved', role: 'user', content: '旧问题', position: 0, status: 'completed', request_id: 'old', reply_to: null, error: null, citations: [] },
      { id: 'a1', conversation_id: 'saved', role: 'assistant', content: '旧回答', position: 1, status: 'completed', request_id: null, reply_to: 'u1', error: null, citations: [] }] };
  bridge.getUpdateInfo.mockResolvedValue({ current_version: '0.3.0', can_install: false });
  bridge.exportConversation.mockResolvedValue({ saved: true, filename: 'Miniima-已有对话.md' });
  bridge.request.mockImplementation(async (method, params) => {
    if (method === 'initialize') return { settings: snapshot, knowledge_bases: [{ id: 'kb', name: '资料', ...settings, created_at: '' }] };
    if (method === 'conversations.list') return { items: [conversation], has_more: false, total: 1 };
    if (method === 'conversations.get') return structuredClone(conversation);
    if (method === 'settings.get') return snapshot;
    if (method === 'updates.check') return { available: false, current_version: '0.3.0', latest_version: '0.3.0' };
    if (method === 'conversations.cancel') {
      const user = conversation.messages.find(item => item.request_id === params.request_id)!;
      user.status = 'interrupted'; user.error = '已停止生成。来源尚未校验。';
      conversation.messages.push({ id: 'partial', conversation_id: 'saved', role: 'assistant', content: '第一段文字', position: 3,
        status: 'interrupted', request_id: null, reply_to: user.id, error: user.error, citations: [] });
      finish(structuredClone(conversation)); return { accepted: true };
    }
    return [];
  });
  bridge.streamRequest.mockImplementation((method, params, onEvent) => new Promise(resolve => {
    emit = onEvent; finish = resolve;
    const user = { ...conversation.messages[0], id: 'pending', content: String(params.question), position: 2,
      status: 'pending' as const, request_id: String(params.request_id) };
    conversation.messages.push(user);
    onEvent({ type: 'started', request_id: params.request_id, conversation_id: conversation.id, conversation: structuredClone(conversation) });
  }));
});

test('streamed text stays in its own tab, stop retains it, and export waits for terminal state', async () => {
  const user = userEvent.setup(); render(<App />);
  await user.click(await screen.findByRole('button', { name: '已有对话 资料' }));
  await screen.findByText('旧回答');
  await user.type(screen.getByLabelText('知识库问题'), '继续解释');
  await user.click(screen.getByRole('button', { name: '发送问题' }));
  const requestId = conversation.messages[2].request_id!;
  act(() => emit({ type: 'delta', request_id: requestId, conversation_id: 'saved', text: '第一段文字' }));
  expect(await screen.findByText('第一段文字')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '导出对话' })).toBeDisabled();
  await user.click(screen.getAllByRole('button', { name: '新建对话' })[1]);
  expect(screen.queryByText('第一段文字')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '关闭对话窗口：已有对话' }));
  expect(bridge.request.mock.calls.some(call => call[0] === 'conversations.cancel')).toBe(false);
  await user.click(screen.getByRole('button', { name: '已有对话 资料' }));
  expect(await screen.findByText('第一段文字')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '停止生成' }));
  expect(await screen.findByText('未完成 · 来源尚未校验')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '重新生成' })).toBeEnabled();
  expect(bridge.request).toHaveBeenCalledWith('conversations.cancel', { request_id: requestId });
  await user.click(screen.getByRole('button', { name: '导出对话' }));
  expect(bridge.exportConversation).toHaveBeenCalledWith('saved');
  expect(await screen.findByText('对话已导出：Miniima-已有对话.md')).toBeInTheDocument();
});

test('streaming preference is scoped to the data home and restored', async () => {
  const user = userEvent.setup(); const view = render(<App />);
  await screen.findByRole('button', { name: '已有对话 资料' });
  await user.click(screen.getByRole('button', { name: '模型与设置' }));
  const checkbox = await screen.findByRole('checkbox', { name: /流式显示回答/ });
  expect(checkbox).toBeChecked();
  await user.click(checkbox);
  expect(JSON.parse(localStorage.getItem('miniima-workspace:preview%3Astream-test')!).streamingEnabled).toBe(false);
  view.unmount(); render(<App />);
  await screen.findByRole('button', { name: '已有对话 资料' });
  await user.click(screen.getByRole('button', { name: '模型与设置' }));
  expect(await screen.findByRole('checkbox', { name: /流式显示回答/ })).not.toBeChecked();
});

test('cancelling the save dialog is silent and write failures are visible', async () => {
  const user = userEvent.setup(); render(<App />);
  await user.click(await screen.findByRole('button', { name: '已有对话 资料' }));
  await screen.findByText('旧回答');
  bridge.exportConversation.mockResolvedValueOnce({ saved: false });
  await user.click(screen.getByRole('button', { name: '导出对话' }));
  await waitFor(() => expect(bridge.exportConversation).toHaveBeenCalledOnce());
  expect(screen.queryByText(/对话已导出/)).not.toBeInTheDocument();
  bridge.exportConversation.mockRejectedValueOnce(new Error('无法写入所选目录'));
  await user.click(screen.getByRole('button', { name: '导出对话' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('无法写入所选目录');
});
