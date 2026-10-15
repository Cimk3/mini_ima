import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, beforeEach, test, expect } from 'vitest';
import App from '../App';
import SettingsDialog from '../components/SettingsDialog';
import type { Bootstrap, ConversationDetail, SettingsSnapshot, Source, TrashItem } from '../types';

const mocks = vi.hoisted(() => ({ request: vi.fn(), chooseFiles: vi.fn(), confirmAction: vi.fn(), windowAction: vi.fn() }));
vi.mock('../bridge', () => ({ ...mocks, errorMessage: (error: unknown) => String(error), handleWindowClose: async () => () => {} }));
const config: SettingsSnapshot = { home: 'C:\\test-home', overrides: [], saved: {
  base_url: 'https://api.deepseek.com', chat_model: 'deepseek-flash', embedding_base_url: 'https://embedding.test/v1',
  embedding_model: 'qwen3.7-text-embedding', embedding_dimension: 1024, chunk_tokens: 500, chunk_overlap: 80,
  timeout: 30, max_retries: 2, embedding_batch_size: 20, retrieval_engine: 'cpp', min_score: .2, context_tokens: 4000,
  api_key_configured: true, embedding_api_key_configured: true, embedding_ready: true }, effective: {} as SettingsSnapshot['effective'] };
config.effective = { ...config.saved };
const bases = ['网络', '阅读'].map((name, index) => ({ id: `kb${index}`, name, embedding_model: config.saved.embedding_model,
  embedding_dimension: 1024, embedding_base_url: config.saved.embedding_base_url, created_at: '2026-10-13' }));
const document = { id: 'doc', filename: 'network.md', status: 'ready', error: null, chunk_count: 2, source_type: 'markdown', created_at: '2026-10-13' };
const source: Source = { id: 1, document_id: 'doc', filename: 'network.md', content: 'TCP 使用三次握手。', citation_number: 1,
  source_metadata: { line_start: 3, line_end: 7, heading_path: ['网络', 'TCP'] } };
let conversations: ConversationDetail[];
let trashItems: TrashItem[];
function conversationFor(question = 'TCP是什么？', text = 'TCP 三次握手用于同步序列号。[1]', id = 'saved', prior?: ConversationDetail): ConversationDetail {
  const position = prior?.messages.length || 0;
  const userId = `${id}-user-${position}`;
  return { id, knowledge_base_id: 'kb0', knowledge_base_name: '网络', title: prior?.title || question.slice(0, 30),
    created_at: '2026-10-15', updated_at: '2026-10-15', message_count: position + 2, messages: [...(prior?.messages || []),
      { id: userId, conversation_id: id, role: 'user', content: question, position, status: 'completed', request_id: `request-${position}`, reply_to: null, error: null, citations: [] },
      { id: `${id}-answer-${position}`, conversation_id: id, role: 'assistant', content: text, position: position + 1, status: 'completed', request_id: null, reply_to: userId, error: null, citations: [{ ...source, id: `${id}-cite-${position}` }] }] };
}

beforeEach(() => {
  localStorage.clear();
  conversations = []; trashItems = [];
  vi.clearAllMocks(); mocks.confirmAction.mockResolvedValue(false); mocks.chooseFiles.mockResolvedValue([]);
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  })));
  mocks.request.mockImplementation(async (method: string, params: Record<string, unknown>) => {
    if (method === 'initialize') return { knowledge_bases: bases, settings: config } satisfies Bootstrap;
    if (method === 'kb.list') return bases.filter(kb => !trashItems.some(item => item.kind === 'kb' && item.id === kb.id));
    if (method === 'conversations.list') {
      const visible = conversations.filter(conversation => !trashItems.some(item => item.id === conversation.id || (item.kind === 'kb' && item.id === conversation.knowledge_base_id)));
      const offset = Number(params.offset || 0);
      return { items: visible.slice(offset, offset + 50), total: visible.length, has_more: offset + 50 < visible.length };
    }
    if (method === 'conversations.get') {
      const found = conversations.filter(conversation => !trashItems.some(item => item.id === conversation.id || (item.kind === 'kb' && item.id === conversation.knowledge_base_id)))
        .find(item => params.request_id ? item.messages.some(message => message.request_id === params.request_id) : item.id === params.conversation_id);
      if (!found) throw Error('对话不存在'); return structuredClone(found);
    }
    if (method === 'conversations.send') {
      const prior = conversations.find(item => item.id === params.conversation_id);
      const detail = conversationFor(String(params.question), undefined, prior?.id || (conversations.length ? `saved-${conversations.length}` : 'saved'), prior);
      detail.knowledge_base_id = String(params.kb);
      detail.knowledge_base_name = bases.find(kb => kb.id === params.kb)!.name;
      detail.messages[detail.messages.length - 2].request_id = String(params.request_id);
      conversations = [...conversations.filter(item => item.id !== detail.id), detail]; return structuredClone(detail);
    }
    if (method === 'conversations.delete') {
      const item = conversations.find(item => item.id === params.conversation_id)!;
      trashItems.push({ kind: 'conversation', id: item.id, title: item.title, knowledge_base_name: item.knowledge_base_name, knowledge_base_id: item.knowledge_base_id, deleted_at: '2026-10-15' });
      return { deleted: true };
    }
    if (method === 'trash.list') return [...trashItems];
    if (method === 'trash.restore') { trashItems = trashItems.filter(item => item.id !== params.item_id); return { done: true }; }
    if (method === 'trash.purge') { trashItems = trashItems.filter(item => item.id !== params.item_id); conversations = conversations.filter(item => item.id !== params.item_id); return { done: true }; }
    if (method === 'trash.empty') { conversations = conversations.filter(item => !trashItems.some(entry => entry.id === item.id)); trashItems = []; return { done: true }; }
    if (method === 'settings.get' || method === 'settings.update') return config;
    if (method === 'docs.list') return params.kb === 'kb0' ? [document] : [];
    if (method === 'docs.preview') return source;
    if (method === 'ask') return { text: 'TCP 三次握手用于同步序列号。[1]', citations: [source], conversation_id: 'saved' };
    if (method === 'connections.test') return { connected: true, kind: params.kind, dimension: 1024 };
    return [];
  });
});

function usePhoneViewport() {
  vi.mocked(window.matchMedia).mockImplementation(query => ({
    matches: true, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
}

test('conversation windows keep separate drafts, switch, close, and restore after restart', async () => {
  const user = userEvent.setup(); const view = render(<App />); await screen.findByText('network.md');
  await user.type(screen.getByLabelText('知识库问题'), '第一个窗口草稿');
  await user.click(screen.getAllByRole('button', { name: '新建对话' })[1]);
  await user.type(screen.getByLabelText('知识库问题'), '第二个窗口草稿');
  let navigation = screen.getByRole('navigation', { name: '对话窗口' });
  await user.click(within(navigation).getAllByRole('button', { name: '切换对话：新对话' })[0]);
  expect(screen.getByLabelText('知识库问题')).toHaveValue('第一个窗口草稿');
  await user.click(within(navigation).getAllByRole('button', { name: '切换对话：新对话' })[1]);
  expect(screen.getByLabelText('知识库问题')).toHaveValue('第二个窗口草稿');
  view.unmount(); render(<App />); await screen.findByText('network.md');
  expect(screen.getByLabelText('知识库问题')).toHaveValue('第二个窗口草稿');
  navigation = screen.getByRole('navigation', { name: '对话窗口' });
  expect(within(navigation).getAllByRole('button', { name: '切换对话：新对话' })).toHaveLength(2);
  await user.click(within(navigation).getAllByRole('button', { name: '关闭对话窗口：新对话' })[1]);
  expect(screen.getByLabelText('知识库问题')).toHaveValue('第一个窗口草稿');
  expect(mocks.request.mock.calls.some(call => call[0] === 'conversations.delete')).toBe(false);
});

test('a late result updates its original conversation window instead of a newer window in the same knowledge base', async () => {
  const user = userEvent.setup(); let finish: (value: unknown) => void;
  const baseline = mocks.request.getMockImplementation()!;
  mocks.request.mockImplementation((method: string, params: Record<string, unknown>) => method === 'conversations.send'
    ? new Promise(resolve => { finish = resolve; }) : baseline(method, params));
  render(<App />); await screen.findByText('network.md');
  await user.type(screen.getByLabelText('知识库问题'), '窗口一的问题{Enter}');
  await user.click(screen.getAllByRole('button', { name: '新建对话' })[1]);
  const result = conversationFor('窗口一的问题', '属于窗口一的回答 [1]');
  conversations = [result]; finish!(result);
  await waitFor(() => expect(screen.getByRole('button', { name: '切换对话：窗口一的问题' })).toBeEnabled());
  expect(screen.queryByText('属于窗口一的回答 [1]')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '切换对话：窗口一的问题' }));
  expect(await screen.findByText('属于窗口一的回答 [1]')).toBeInTheDocument();
});

test('source sidebar collapses, remembers the layout, and citations reopen it', async () => {
  const user = userEvent.setup(); const view = render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('button', { name: '收起右侧来源栏' }));
  expect(screen.queryByLabelText('来源详情')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '展开来源栏' })).toHaveAttribute('aria-expanded', 'false');
  view.unmount(); render(<App />); await screen.findByText('network.md');
  expect(screen.queryByLabelText('来源详情')).not.toBeInTheDocument();
  await user.type(screen.getByLabelText('知识库问题'), 'TCP{Enter}');
  await user.click(await screen.findByRole('button', { name: '[1] network.md' }));
  expect(screen.getByLabelText('来源详情')).toBeInTheDocument();
  expect(localStorage.getItem('miniima-source-hidden')).toBe('false');
});

test('web search toggles per window and webpage sources open through the desktop bridge', async () => {
  const user = userEvent.setup(); const baseline = mocks.request.getMockImplementation()!;
  mocks.request.mockImplementation(async (method: string, params: Record<string, unknown>) => {
    if (method !== 'conversations.send') return baseline(method, params);
    const result = conversationFor('TCP 当前规范');
    result.messages[0].web_search = true;
    result.messages[1].citations = [{ ...source, id: 'web-citation', filename: 'TCP RFC', chunk_id: null,
      source_metadata: { ...source.source_metadata, kind: 'web', url: 'https://example.org/tcp' } }];
    return result;
  });
  render(<App />); await screen.findByText('network.md');
  expect(screen.queryByText('深度思考')).not.toBeInTheDocument();
  expect(window.document.querySelector('.titlebar-divider')).toBeNull();
  const toggle = screen.getByRole('button', { name: '联网搜索' });
  expect(toggle).toHaveAttribute('aria-pressed', 'false'); await user.click(toggle);
  await user.click(screen.getAllByRole('button', { name: '新建对话' })[1]);
  expect(screen.getByRole('button', { name: '联网搜索' })).toHaveAttribute('aria-pressed', 'false');
  await user.click(within(screen.getByRole('navigation', { name: '对话窗口' })).getAllByRole('button', { name: '切换对话：新对话' })[0]);
  expect(screen.getByRole('button', { name: '联网搜索' })).toHaveAttribute('aria-pressed', 'true');
  await user.type(screen.getByLabelText('知识库问题'), 'TCP 当前规范{Enter}');
  await screen.findByText('已联网搜索');
  expect(mocks.request).toHaveBeenCalledWith('conversations.send', expect.objectContaining({ web_search: true }));
  await user.click(screen.getByRole('button', { name: '[1] TCP RFC' }));
  await user.click(screen.getByRole('button', { name: '打开网页' }));
  expect(mocks.request).toHaveBeenCalledWith('web.open', { url: 'https://example.org/tcp' });
});

test('phone navigation traps focus and closes after selecting a knowledge base', async () => {
  usePhoneViewport();
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  const trigger = screen.getByRole('button', { name: '打开知识库导航' });
  await user.click(trigger);
  const navigation = screen.getByRole('dialog', { name: '知识库导航' });
  expect(trigger).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('main')).toHaveAttribute('inert');
  within(navigation).getByRole('button', { name: '模型与设置' }).focus();
  await user.tab();
  expect(within(navigation).getByRole('button', { name: '关闭知识库导航' })).toHaveFocus();
  await user.click(within(navigation).getByRole('button', { name: '阅读' }));
  expect(screen.queryByRole('dialog', { name: '知识库导航' })).not.toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: '阅读', level: 1 })).toBeInTheDocument();
  await waitFor(() => expect(trigger).toHaveFocus());
  expect(screen.getByRole('main')).not.toHaveAttribute('inert');
});

test('phone source opens as a dialog and Escape returns to its document', async () => {
  usePhoneViewport();
  const user = userEvent.setup(); render(<App />);
  await user.click(await screen.findByText('最近文档'));
  const documentButton = await screen.findByRole('button', { name: /network.md/ });
  await user.click(documentButton);
  const sourceDialog = await screen.findByRole('dialog', { name: '来源详情' });
  expect(within(sourceDialog).getByText('行 3–7')).toBeInTheDocument();
  expect(within(sourceDialog).getByRole('button', { name: '关闭来源' })).toHaveFocus();
  expect(screen.getByRole('main')).toHaveAttribute('inert');
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await waitFor(() => expect(documentButton).toHaveFocus());
  expect(screen.getByRole('main')).not.toHaveAttribute('inert');
});

test('settings opened from phone navigation returns to the menu button', async () => {
  usePhoneViewport();
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  const trigger = screen.getByRole('button', { name: '打开知识库导航' });
  await user.click(trigger);
  await user.click(within(screen.getByRole('dialog', { name: '知识库导航' })).getByRole('button', { name: '模型与设置' }));
  expect(screen.queryByRole('dialog', { name: '知识库导航' })).not.toBeInTheDocument();
  const settingsDialog = screen.getByRole('dialog', { name: '模型与连接' });
  expect(within(settingsDialog).getAllByLabelText('服务地址')[0]).toHaveFocus();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(trigger).toHaveFocus());
});

test('loads shared documents and shows actual source location', async () => {
  const user = userEvent.setup(); render(<App />);
  await user.click(await screen.findByText('最近文档'));
  await user.click(await screen.findByRole('button', { name: /network.md/ }));
  expect(await screen.findByText('行 3–7')).toBeInTheDocument();
  expect(screen.getAllByText('TCP 使用三次握手。').length).toBeGreaterThan(0);
});

test('requires confirmation and does not delete on cancel', async () => {
  const user = userEvent.setup(); render(<App />);
  await screen.findByText('network.md'); await user.click(screen.getByRole('tab', { name: /文档/ }));
  await user.click(screen.getByRole('button', { name: '删除当前知识库' }));
  expect(mocks.confirmAction).toHaveBeenCalledWith(expect.stringContaining('网络'));
  expect(mocks.request.mock.calls.some(call => call[0] === 'kb.delete')).toBe(false);
});

test('new key entry is visible, existing keys stay blank, and a hide toggle works', async () => {
  const user = userEvent.setup(); render(<SettingsDialog snapshot={config} onClose={() => {}} onSaved={() => {}} onBusy={() => {}} />);
  const input = screen.getByLabelText('Qwen API Key');
  expect(input).toHaveAttribute('type', 'text'); expect(input).toHaveValue('');
  await user.type(input, 'new-test-key'); expect(input).toHaveValue('new-test-key');
  await user.click(screen.getByRole('button', { name: '隐藏向量 API Key' })); expect(input).toHaveAttribute('type', 'password');
  expect(screen.getByLabelText('DeepSeek API Key')).toHaveAttribute('type', 'text');
  await user.click(screen.getByRole('button', { name: '保存设置' }));
  await waitFor(() => expect(mocks.request).toHaveBeenCalledWith('settings.update', { values: expect.objectContaining({ embedding_api_key: 'new-test-key', api_key: '' }) }));
});

test('appearance switches across the whole app and persists', async () => {
  const user = userEvent.setup(); const view = render(<App />);
  await screen.findByText('network.md');
  expect(window.document.documentElement).toHaveAttribute('data-theme', 'light');
  expect(screen.getByRole('button', { name: '切换深色模式' }).querySelector('.lucide-moon')).not.toBeNull();
  await user.click(screen.getByRole('button', { name: '切换深色模式' }));
  expect(window.document.documentElement).toHaveAttribute('data-theme', 'dark');
  expect(localStorage.getItem('miniima-appearance')).toBe('dark');
  view.unmount(); render(<App />); await screen.findByText('network.md');
  expect(screen.getByRole('button', { name: '切换浅色模式' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '切换浅色模式' }).querySelector('.lucide-sun')).not.toBeNull();
});

test('settings traps Tab, closes with Escape and returns focus to its trigger', async () => {
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  const trigger = screen.getByRole('button', { name: '模型与设置' });
  fireEvent.click(trigger);
  const dialog = screen.getByRole('dialog');
  expect(window.document.activeElement).toBe(within(dialog).getAllByLabelText('服务地址')[0]);
  const last = within(dialog).getByRole('button', { name: '保存设置' });
  last.focus(); await user.tab();
  expect(within(dialog).getByRole('button', { name: '关闭设置' })).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await waitFor(() => expect(trigger).toHaveFocus());
});

test('tabs respond to arrow keys and IME confirmation does not send a question', async () => {
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  const questionTab = screen.getByRole('tab', { name: '问答' });
  questionTab.focus(); await user.keyboard('{ArrowDown}{End}{Home}');
  expect(screen.getByRole('tab', { name: '问答' })).toHaveFocus();
  fireEvent.change(screen.getByLabelText('知识库问题'), { target: { value: '中文问题' } });
  fireEvent.keyDown(screen.getByLabelText('知识库问题'), { key: 'Enter', isComposing: true });
  expect(mocks.request.mock.calls.some(call => call[0] === 'conversations.send')).toBe(false);
  await user.click(screen.getByRole('button', { name: '发送问题' }));
  expect(await screen.findByText('TCP 三次握手用于同步序列号。[1]')).toBeInTheDocument();
});

test('save-and-test uses the connection response and shows failures honestly', async () => {
  const user = userEvent.setup(); render(<SettingsDialog snapshot={config} onClose={() => {}} onSaved={() => {}} onBusy={() => {}} />);
  await user.click(screen.getByRole('button', { name: /保存并测试向量连接/ }));
  expect(await screen.findByText('向量连接成功，输出维度 1024。')).toBeInTheDocument();
  mocks.request.mockImplementation(async (method: string) => { if (method === 'settings.update') return config; throw 'API 错误 HTTP 401'; });
  await user.click(screen.getByRole('button', { name: /保存并测试问答连接/ }));
  expect(await screen.findByText('API 错误 HTTP 401')).toBeInTheDocument();
});

test('batch import reports success, duplicates, failures and continues', async () => {
  const user = userEvent.setup(); mocks.chooseFiles.mockResolvedValue(['C:\\a.md', 'C:\\b.md', 'C:\\c.txt']);
  const baseline = mocks.request.getMockImplementation()!;
  mocks.request.mockImplementation(async (method: string, params: Record<string, unknown>) => {
    if (method !== 'docs.import') return baseline(method, params);
    if (params.path === 'C:\\c.txt') throw '文档不包含可提取文本';
    return { document, imported: params.path === 'C:\\a.md' };
  });
  render(<App />); await screen.findByText('network.md'); await user.click(screen.getByRole('tab', { name: /文档/ }));
  await user.click(screen.getByRole('button', { name: '导入文档' }));
  expect(await screen.findByText('处理完成：1 个导入，1 个重复跳过，1 个失败。')).toBeInTheDocument();
  const progress = within(screen.getByLabelText('导入进度'));
  expect(progress.getByText('文档不包含可提取文本')).toBeInTheDocument();
  expect(mocks.request.mock.calls.filter(call => call[0] === 'docs.import')).toHaveLength(3);
});

test('an old question result cannot leak into another knowledge base', async () => {
  const user = userEvent.setup(); let finish: (value: unknown) => void;
  const baseline = mocks.request.getMockImplementation()!;
  mocks.request.mockImplementation((method: string, params: Record<string, unknown>) => method === 'conversations.send'
    ? new Promise(resolve => { finish = resolve; }) : baseline(method, params));
  render(<App />); await screen.findByText('network.md'); await user.click(screen.getByRole('tab', { name: '问答' }));
  await user.type(screen.getByLabelText('知识库问题'), 'TCP是什么？'); await user.click(screen.getByRole('button', { name: '发送问题' }));
  await user.click(screen.getByRole('button', { name: '阅读' }));
  finish!(conversationFor('TCP是什么？', '来自旧知识库的回答', 'old'));
  await waitFor(() => expect(screen.getByRole('button', { name: '发送问题' })).toBeDisabled());
  expect(screen.queryByText('来自旧知识库的回答')).not.toBeInTheDocument();
});

test('answer renders valid citations while raw HTML remains inactive', async () => {
  const user = userEvent.setup(); const baseline = mocks.request.getMockImplementation()!;
  mocks.request.mockImplementation(async (method: string, params: Record<string, unknown>) => method === 'conversations.send'
    ? conversationFor('TCP', '**有效回答** [1]\n<script>alert(1)</script><img src="https://bad.test/image">') : baseline(method, params));
  render(<App />); await screen.findByText('network.md'); await user.click(screen.getByRole('tab', { name: '问答' }));
  fireEvent.change(screen.getByLabelText('知识库问题'), { target: { value: 'TCP' } });
  await user.click(screen.getByRole('button', { name: '发送问题' }));
  expect(await screen.findByText('有效回答')).toBeInTheDocument();
  expect(window.document.querySelector('.answer-markdown script, .answer-markdown img')).toBeNull();
  await user.click(screen.getByRole('button', { name: /\[1\].*network.md/ }));
  expect(await screen.findByText('行 3–7')).toBeInTheDocument();
});

test('reference titlebar forwards native window actions', async () => {
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('button', { name: '最小化窗口' }));
  await user.click(screen.getByRole('button', { name: '最大化或还原窗口' }));
  await user.click(screen.getByRole('button', { name: '关闭窗口' }));
  expect(mocks.windowAction.mock.calls.map(call => call[0])).toEqual(['minimize', 'maximize', 'close']);
});

test('closing an expanded source restores the workspace without leaving a blank overlay', async () => {
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.type(screen.getByLabelText('知识库问题'), 'TCP');
  await user.click(screen.getByRole('button', { name: '发送问题' }));
  await user.click(await screen.findByRole('button', { name: '展开来源预览' }));
  expect(screen.getByRole('dialog', { name: '来源详情' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '模型与设置' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: '关闭来源' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '模型与设置' })).toBeEnabled();
  expect(screen.getByRole('heading', { name: '核对每一处来源' })).toBeInTheDocument();
});

test('top search respects the current workspace and new conversation only clears the view', async () => {
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('tab', { name: '搜索' }));
  await user.type(screen.getByRole('textbox', { name: '搜索知识库或直接提问' }), 'TCP{Enter}');
  await waitFor(() => expect(mocks.request).toHaveBeenCalledWith('search', { kb: 'kb0', question: 'TCP', top_k: 5 }));
  await user.click(screen.getByRole('tab', { name: '问答' }));
  await user.type(screen.getByLabelText('知识库问题'), 'TCP');
  await user.click(screen.getByRole('button', { name: '发送问题' }));
  expect(await screen.findByText('TCP 三次握手用于同步序列号。[1]')).toBeInTheDocument();
  await user.click(screen.getAllByRole('button', { name: '新建对话' })[0]);
  expect(screen.getByRole('heading', { name: '和你的知识，聊一聊。' })).toBeInTheDocument();
  expect(screen.getByLabelText('知识库问题')).toHaveValue('');
  expect(mocks.request.mock.calls.some(call => call[0] === 'kb.delete')).toBe(false);
});

test.each(['搜索', '文档 1'])('new conversation from %s focuses the mounted question input', async workspace => {
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('tab', { name: workspace }));
  await user.click(screen.getAllByRole('button', { name: '新建对话' })[0]);
  expect(screen.getByLabelText('知识库问题')).toHaveFocus();
  await user.keyboard('直接输入新问题');
  expect(screen.getByLabelText('知识库问题')).toHaveValue('直接输入新问题');
});

test('follow-ups append, each answer keeps its source, and a restart restores the conversation', async () => {
  const user = userEvent.setup(); const view = render(<App />); await screen.findByText('network.md');
  await user.type(screen.getByLabelText('知识库问题'), 'TCP是什么？{Enter}');
  await screen.findByText('TCP 三次握手用于同步序列号。[1]');
  await user.type(screen.getByLabelText('知识库问题'), '那为什么需要三次？{Enter}');
  await waitFor(() => expect(within(screen.getByLabelText('对话消息')).getAllByRole('heading', { level: 2 })).toHaveLength(2));
  const calls = mocks.request.mock.calls.filter(call => call[0] === 'conversations.send');
  expect(calls[0][1]).not.toHaveProperty('conversation_id');
  expect(calls[1][1]).toMatchObject({ conversation_id: 'saved', question: '那为什么需要三次？' });
  expect(calls[1][1].request_id).not.toBe(calls[0][1].request_id);
  expect(screen.getAllByRole('button', { name: '[1] network.md' })).toHaveLength(2);
  await user.click(screen.getAllByRole('button', { name: '[1] network.md' })[0]);
  expect(await screen.findByText('行 3–7')).toBeInTheDocument();
  view.unmount(); render(<App />);
  await screen.findByLabelText('对话消息');
  expect(within(screen.getByLabelText('对话消息')).getAllByRole('heading', { level: 2 })).toHaveLength(2);
  expect(screen.getAllByRole('button', { name: '[1] network.md' })).toHaveLength(2);
  expect(mocks.request.mock.calls.filter(call => call[0] === 'conversations.send')).toHaveLength(2);
});

test('new conversation keeps old history and restores a snapshot even when the original chunk is gone', async () => {
  const old = conversationFor('旧问题', '旧回答 [1]', 'old-cli');
  old.messages[1].citations[0] = { ...source, id: 'snapshot-own-id', chunk_id: null, content: '只保存在历史中的片段。' };
  conversations = [old];
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.click(within(screen.getByRole('navigation', { name: '历史对话' })).getByRole('button', { name: '旧问题 网络' }));
  expect(await screen.findByText('旧回答 [1]')).toBeInTheDocument();
  await user.click(screen.getAllByRole('button', { name: '新建对话' })[1]);
  expect(screen.getByLabelText('知识库问题')).toHaveFocus();
  expect(screen.queryByText('旧回答 [1]')).not.toBeInTheDocument();
  expect(conversations).toHaveLength(1);
  await user.click(screen.getByRole('button', { name: '旧问题 网络' }));
  await user.click(await screen.findByRole('button', { name: '[1] network.md' }));
  expect(screen.getAllByText('只保存在历史中的片段。').length).toBeGreaterThan(0);
});

test('knowledge base drafts survive switching and stay scoped to the data home', async () => {
  const user = userEvent.setup(); const view = render(<App />); await screen.findByText('network.md');
  await user.type(screen.getByLabelText('知识库问题'), '网络草稿');
  await user.click(screen.getByRole('button', { name: '阅读' }));
  await user.type(screen.getByLabelText('知识库问题'), '阅读草稿');
  await user.click(screen.getByRole('tab', { name: '搜索' }));
  await user.click(screen.getByRole('button', { name: '网络' }));
  expect(screen.getByLabelText('知识库问题')).toHaveValue('网络草稿');
  view.unmount(); const secondView = render(<App />); await screen.findByText('network.md');
  expect(screen.getByLabelText('知识库问题')).toHaveValue('网络草稿');
  secondView.unmount();
  const baseline = mocks.request.getMockImplementation()!;
  mocks.request.mockImplementation(async (method: string, params: Record<string, unknown>) => method === 'initialize'
    ? { knowledge_bases: bases, settings: { ...config, home: 'C:\\different-home' } } : baseline(method, params));
  render(<App />); await screen.findByText('network.md');
  expect(screen.getByLabelText('知识库问题')).toHaveValue('');
});

test('an interrupted outbox is recovered by request ID without resending the question', async () => {
  const interrupted = conversationFor('未完成的问题');
  interrupted.messages = [{ ...interrupted.messages[0], request_id: 'stable-outbox', status: 'interrupted', error: '上次处理已中断，可重试。' }];
  conversations = [interrupted];
  localStorage.setItem(`miniima-workspace:${encodeURIComponent(config.home)}`, JSON.stringify({ outbox: { kb: 'kb0', question: '未完成的问题', request_id: 'stable-outbox' } }));
  render(<App />);
  expect(await screen.findByRole('button', { name: '重试问题' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: '未完成的问题' })).toBeInTheDocument();
  expect(mocks.request).toHaveBeenCalledWith('conversations.get', { request_id: 'stable-outbox' });
  expect(mocks.request.mock.calls.some(call => call[0] === 'conversations.send')).toBe(false);
});

test('failed questions stay visible and retry uses the same request without duplicating a message', async () => {
  const baseline = mocks.request.getMockImplementation()!;
  let stableId: unknown;
  mocks.request.mockImplementation(async (method: string, params: Record<string, unknown>) => {
    if (method === 'conversations.send') {
      stableId = params.request_id;
      const detail = conversationFor(String(params.question));
      detail.messages = [{ ...detail.messages[0], request_id: String(stableId), status: 'failed', error: '模拟 API 超时' }];
      conversations = [detail]; return detail;
    }
    if (method === 'conversations.retry') {
      expect(params.request_id).toBe(stableId);
      const detail = conversationFor('需要重试的问题'); conversations = [detail]; return detail;
    }
    return baseline(method, params);
  });
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.type(screen.getByLabelText('知识库问题'), '需要重试的问题{Enter}');
  expect(await screen.findByText('模拟 API 超时')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '重试问题' }));
  expect(await screen.findByText('TCP 三次握手用于同步序列号。[1]')).toBeInTheDocument();
  expect(screen.getAllByRole('heading', { name: '需要重试的问题' })).toHaveLength(1);
  expect(screen.queryByRole('button', { name: '重试问题' })).not.toBeInTheDocument();
});

test('a late answer updates its history without replacing the conversation currently being viewed', async () => {
  conversations = [conversationFor('另一条历史问题', '另一条历史回答', 'other')];
  const baseline = mocks.request.getMockImplementation()!;
  let finish: (value: unknown) => void;
  mocks.request.mockImplementation((method: string, params: Record<string, unknown>) => method === 'conversations.send'
    ? new Promise(resolve => { finish = resolve; }) : baseline(method, params));
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.type(screen.getByLabelText('知识库问题'), '正在等待的问题{Enter}');
  await user.click(screen.getByRole('button', { name: '另一条历史问题 网络' }));
  await screen.findByText('另一条历史回答');
  const late = conversationFor('正在等待的问题', '迟到的回答', 'late'); conversations.push(late); finish!(late);
  await waitFor(() => expect(screen.getByRole('button', { name: '正在等待的问题 网络' })).toBeInTheDocument());
  expect(screen.queryByText('迟到的回答')).not.toBeInTheDocument();
  expect(screen.getByText('另一条历史回答')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '正在等待的问题 网络' }));
  expect(await screen.findByText('迟到的回答')).toBeInTheDocument();
});

test('opening the pending conversation still receives its completed answer', async () => {
  const prior = conversationFor('原来的问题', '原来的回答'); conversations = [prior];
  const baseline = mocks.request.getMockImplementation()!;
  let finish: (value: unknown) => void;
  mocks.request.mockImplementation((method: string, params: Record<string, unknown>) => {
    if (method !== 'conversations.send') return baseline(method, params);
    const pending = conversationFor(String(params.question), undefined, 'saved', prior);
    pending.messages.pop(); pending.messages.at(-1)!.status = 'pending'; conversations = [pending];
    return new Promise(resolve => { finish = resolve; });
  });
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('button', { name: '原来的问题 网络' }));
  await screen.findByText('原来的回答');
  await user.type(screen.getByLabelText('知识库问题'), '生成中的问题{Enter}');
  await user.click(screen.getAllByRole('button', { name: '新建对话' })[1]);
  await user.click(screen.getByRole('button', { name: '原来的问题 网络' }));
  await screen.findByText('正在参考知识库回答…');
  const completed = conversationFor('生成中的问题', '刚完成的回答', 'saved', prior);
  conversations = [completed]; finish!(completed);
  expect(await screen.findByText('刚完成的回答')).toBeInTheDocument();
  expect(screen.queryByText('正在参考知识库回答…')).not.toBeInTheDocument();
});

test('refresh clears a conversation that another entry point moved to trash', async () => {
  conversations = [conversationFor('外部删除的对话', '应从当前界面移除的回答')];
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('button', { name: '外部删除的对话 网络' }));
  await screen.findByText('应从当前界面移除的回答');
  trashItems.push({ kind: 'conversation', id: 'saved', title: '外部删除的对话', knowledge_base_id: 'kb0', knowledge_base_name: '网络', deleted_at: '2026-10-15' });
  await user.click(screen.getByRole('button', { name: '刷新知识库' }));
  expect(await screen.findByText('当前对话已移入回收站或被彻底删除，可在回收站查看。')).toBeInTheDocument();
  expect(screen.queryByText('应从当前界面移除的回答')).not.toBeInTheDocument();
});

test('a refresh started in an old conversation cannot replace the newly selected conversation', async () => {
  conversations = [conversationFor('问题 A', '回答 A', 'A'), conversationFor('问题 B', '回答 B', 'B')];
  const baseline = mocks.request.getMockImplementation()!;
  let finishSettings: (value: unknown) => void;
  mocks.request.mockImplementation((method: string, params: Record<string, unknown>) => method === 'settings.get'
    ? new Promise(resolve => { finishSettings = resolve; }) : baseline(method, params));
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('button', { name: '问题 A 网络' })); await screen.findByText('回答 A');
  await user.click(screen.getByRole('button', { name: '刷新知识库' }));
  await user.click(screen.getByRole('button', { name: '问题 B 网络' })); await screen.findByText('回答 B');
  finishSettings!(config);
  await waitFor(() => expect(mocks.request.mock.calls.filter(call => call[0] === 'conversations.list')).toHaveLength(2));
  expect(screen.getByText('回答 B')).toBeInTheDocument();
  expect(screen.queryByText('回答 A')).not.toBeInTheDocument();
});

test('conversation deletion can be cancelled, restored, and permanent deletion requires confirmation', async () => {
  conversations = [conversationFor('要保留的记录')];
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('button', { name: '删除对话：要保留的记录' }));
  expect(mocks.request.mock.calls.some(call => call[0] === 'conversations.delete')).toBe(false);
  mocks.confirmAction.mockResolvedValue(true);
  await user.click(screen.getByRole('button', { name: '删除对话：要保留的记录' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: '删除对话：要保留的记录' })).not.toBeInTheDocument());
  await user.click(screen.getByRole('tab', { name: '回收站' }));
  await user.click(await screen.findByRole('button', { name: '恢复' }));
  expect(await screen.findByRole('button', { name: '要保留的记录 网络' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '删除对话：要保留的记录' }));
  await user.click(screen.getByRole('button', { name: '刷新知识库' }));
  mocks.confirmAction.mockResolvedValue(false);
  await user.click(await screen.findByRole('button', { name: '彻底删除' }));
  expect(mocks.request.mock.calls.some(call => call[0] === 'trash.purge')).toBe(false);
  await user.click(screen.getByRole('button', { name: '清空回收站' }));
  expect(mocks.request.mock.calls.some(call => call[0] === 'trash.empty')).toBe(false);
  mocks.confirmAction.mockResolvedValue(true);
  await user.click(screen.getByRole('button', { name: '清空回收站' }));
  expect(await screen.findByText('回收站是空的')).toBeInTheDocument();
});

test('the recycle bin remains available with no active knowledge base', async () => {
  trashItems = [{ kind: 'kb', id: 'kb0', title: '网络', knowledge_base_name: '网络', knowledge_base_id: 'kb0', deleted_at: '2026-10-15' }];
  const baseline = mocks.request.getMockImplementation()!;
  mocks.request.mockImplementation(async (method: string, params: Record<string, unknown>) => method === 'initialize'
    ? { knowledge_bases: [], settings: config } : baseline(method, params));
  const user = userEvent.setup(); render(<App />); await screen.findByText('让你的资料，成为答案。');
  await user.click(screen.getByRole('tab', { name: '回收站' }));
  expect(await screen.findByRole('button', { name: '恢复' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '恢复' }));
  expect(await screen.findByRole('button', { name: '网络 1' })).toBeInTheDocument();
});

test('history loads fifty conversations at a time and opens a conversation in its own knowledge base', async () => {
  conversations = Array.from({ length: 53 }, (_, i) => conversationFor(`历史问题${i}`, `历史回答${i}`, `history-${i}`));
  conversations[52].knowledge_base_id = 'kb1'; conversations[52].knowledge_base_name = '阅读';
  const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  const history = within(screen.getByRole('navigation', { name: '历史对话' }));
  expect(history.getAllByRole('button', { name: /删除对话/ })).toHaveLength(50);
  await user.click(history.getByRole('button', { name: '加载更多对话' }));
  await waitFor(() => expect(history.getAllByRole('button', { name: /删除对话/ })).toHaveLength(53));
  expect(mocks.request).toHaveBeenCalledWith('conversations.list', { offset: 50, limit: 50 });
  await user.click(history.getByRole('button', { name: '历史问题52 阅读' }));
  expect(await screen.findByText('历史回答52')).toBeInTheDocument();
  expect(screen.getByLabelText('当前知识库')).toHaveValue('kb1');
});

test('desktop sidebar can be fully hidden and restored after restarting', async () => {
  const user = userEvent.setup(); const view = render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('button', { name: '隐藏侧边栏' }));
  expect(window.document.querySelector('.app-shell')).toHaveClass('sidebar-hidden');
  expect(screen.getByLabelText('知识库导航')).toHaveAttribute('inert');
  expect(localStorage.getItem('miniima-sidebar-hidden')).toBe('true');
  view.unmount(); render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('button', { name: '展开侧边栏' }));
  expect(window.document.querySelector('.app-shell')).not.toHaveClass('sidebar-hidden');
});

test('new conversation from the phone drawer puts keyboard focus in the composer', async () => {
  usePhoneViewport(); const user = userEvent.setup(); render(<App />); await screen.findByText('network.md');
  await user.click(screen.getByRole('button', { name: '打开知识库导航' }));
  await user.click(within(screen.getByRole('dialog', { name: '知识库导航' })).getByRole('button', { name: '新建对话' }));
  await waitFor(() => expect(screen.getByLabelText('知识库问题')).toHaveFocus());
  expect(screen.queryByRole('dialog', { name: '知识库导航' })).not.toBeInTheDocument();
});
