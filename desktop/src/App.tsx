import { useEffect, useRef, useState } from 'react';
import { BookOpen, Plus, FileText, Search, Sparkles, Upload, Settings2, Trash2, X,
  Loader2, ChevronRight, Check, AlertCircle, Layers, Database,
  MessageCircleMore, MessageSquare, Archive, ChevronDown, History, MoreHorizontal, PanelRightOpen, PanelRightClose, Pencil, FileDown } from 'lucide-react';
import { request, streamRequest, exportConversation, chooseFiles, confirmAction, errorMessage, handleWindowClose } from './bridge';
import SettingsDialog from './components/SettingsDialog';
import NewKnowledgeBaseDialog from './components/NewKnowledgeBaseDialog';
import SourceDrawer from './components/SourceDrawer';
import Titlebar from './components/Titlebar';
import { useDialog } from './components/useDialog';
import { useMediaQuery } from './hooks/useMediaQuery';
import ChatWorkspace from './components/ChatWorkspace';
import ConversationTabs from './components/ConversationTabs';
import RenameConversationDialog from './components/RenameConversationDialog';
import { useUpdates } from './hooks/useUpdates';
import { UpdateBanner } from './components/UpdateSection';
import TrashView from './components/TrashView';
import { readWorkspace, writeWorkspace, draft, draftKey } from './workspaceStorage';
import type { Bootstrap, ConversationDetail, ConversationPage, ConversationSummary, ConversationWindow, DocumentRecord, GenerationView, ImportEntry, ImportResult, KnowledgeBase, Outbox, SettingsSnapshot, Source, TrashItem, TurnEvent } from './types';

type Tab = 'documents' | 'search' | 'ask' | 'trash';
const date = (value: string) => value ? new Date(value).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }) : '未记录';
const location = (s: Source) => `行 ${s.source_metadata.line_start}–${s.source_metadata.line_end}`;
const filename = (path: string) => path.split(/[\\/]/).pop() || path;
type Theme = 'light' | 'dark';
function savedTheme(): Theme {
  try { return localStorage.getItem('miniima-appearance') === 'dark' ? 'dark' : 'light'; }
  catch { return 'light'; }
}

export default function App() {
  const compactNavigation = useMediaQuery('(max-width: 767px)');
  const overlaySource = useMediaQuery('(max-width: 1079px)');
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [sidebarHidden, setSidebarHidden] = useState(() => { try { return localStorage.getItem('miniima-sidebar-hidden') === 'true'; } catch { return false; } });
  const [sourceHidden, setSourceHidden] = useState(() => { try { return localStorage.getItem('miniima-source-hidden') === 'true'; } catch { return false; } });
  const [windows, setWindows] = useState<ConversationWindow[]>([]);
  const windowsRef = useRef<ConversationWindow[]>([]);
  const [closedWindows, setClosedWindows] = useState<ConversationWindow[]>([]);
  const closedWindowsRef = useRef<ConversationWindow[]>([]);
  const [activeWindowKey, setActiveWindowKey] = useState('');
  const activeWindow = useRef('');
  const [webSearch, setWebSearch] = useState(false);
  const [theme, setTheme] = useState<Theme>(savedTheme);
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [selected, setSelected] = useState('');
  const [settings, setSettings] = useState<SettingsSnapshot | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [tab, setTab] = useState<Tab>('ask');
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState<Source[] | null>(null);
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [historyMore, setHistoryMore] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyQuery, setHistoryQuery] = useState('');
  const historyFilter = useRef('');
  const historySearchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [renameTarget, setRenameTarget] = useState<ConversationSummary | null>(null);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [trash, setTrash] = useState<TrashItem[]>([]);
  const [trashLoading, setTrashLoading] = useState(false);
  const [sourceGroup, setSourceGroup] = useState<Source[]>([]);
  const [pendingTurn, setPendingTurn] = useState<{ view: number; windowKey: string; request: Outbox } | null>(null);
  const [unconfirmed, setUnconfirmed] = useState<Outbox | null>(null);
  const [generation, setGeneration] = useState<GenerationView | null>(null);
  const generationRef = useRef<GenerationView | null>(null);
  const [streamingEnabled, setStreamingEnabled] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [source, setSource] = useState<Source | null>(null);
  const [expandedSource, setExpandedSource] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [startup, setStartup] = useState(true);
  const updates = useUpdates(startup, !!busy, state => setBusy(state ? 'update' : null));
  const [docsLoading, setDocsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [imports, setImports] = useState<ImportEntry[]>([]);
  const selection = useRef('');
  const loadingId = useRef(0);
  const viewVersion = useRef(0);
  const activeConversation = useRef(activeId);
  const workspaceTab = useRef(tab);
  const historyVersion = useRef(0);
  const homeRef = useRef('');
  const busyRef = useRef(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const answerRef = useRef<HTMLDivElement>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const focusNewQuestion = useRef(false);
  const [focusRequest, setFocusRequest] = useState(0);
  const modalTrigger = useRef<HTMLElement | null>(null);
  const navigationTrigger = useRef<HTMLButtonElement>(null);
  const sourceTrigger = useRef<HTMLElement | null>(null);
  const sourceToggle = useRef<HTMLButtonElement>(null);
  const navigationVisible = compactNavigation && navigationOpen;
  const navigationRef = useDialog<HTMLElement>(() => setNavigationOpen(false), false, navigationTrigger.current, navigationVisible);
  const base = bases.find(kb => kb.id === selected);
  const currentGeneration = generation && (generation.windowKey === activeWindowKey || generation.conversationId === activeId) ? generation : undefined;
  const modalOpen = (settingsOpen && !!settings) || newOpen || !!renameTarget;
  const sourceModal = !!source && overlaySource;
  busyRef.current = !!busy;
  activeConversation.current = activeId;
  workspaceTab.current = tab;

  useEffect(() => {
    if (!compactNavigation) setNavigationOpen(false);
  }, [compactNavigation]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('miniima-appearance', theme); } catch { /* Appearance also works without storage. */ }
    return () => { delete document.documentElement.dataset.theme; };
  }, [theme]);

  useEffect(() => {
    contentRef.current?.scrollTo?.({ top: 0 });
  }, [tab, selected]);

  useEffect(() => () => clearTimeout(historySearchTimer.current), []);

  useEffect(() => {
    try { localStorage.setItem('miniima-sidebar-hidden', String(sidebarHidden)); } catch { /* Optional layout preference. */ }
  }, [sidebarHidden]);

  useEffect(() => {
    try { localStorage.setItem('miniima-source-hidden', String(sourceHidden)); } catch { /* Optional layout preference. */ }
  }, [sourceHidden]);

  useEffect(() => {
    if (settings && !startup) writeWorkspace(settings.home, { windows, activeWindowKey });
  }, [windows, activeWindowKey, settings?.home, startup]);

  useEffect(() => {
    if (!settings || startup || tab !== 'ask') return;
    writeWorkspace(settings.home, { lastConversationId: activeId, lastKb: selected });
  }, [selected, activeId, settings?.home, startup, tab]);

  useEffect(() => {
    if (tab !== 'ask' || !focusNewQuestion.current || busy || startup || conversationLoading || navigationVisible || modalOpen || sourceModal) return;
    // Run after the navigation drawer has returned focus to its trigger.
    queueMicrotask(() => {
      if (questionRef.current && !questionRef.current.disabled) {
        questionRef.current.focus();
        focusNewQuestion.current = false;
      }
    });
  }, [tab, focusRequest, busy, startup, conversationLoading, navigationVisible, modalOpen, sourceModal]);

  async function loadDocuments(kb: string) {
    const version = ++loadingId.current;
    setDocsLoading(true);
    try {
      const docs = await request<DocumentRecord[]>('docs.list', { kb });
      if (selection.current === kb && version === loadingId.current) setDocuments(docs);
    } catch (e) { if (selection.current === kb && version === loadingId.current) setError(errorMessage(e)); }
    finally { if (version === loadingId.current) setDocsLoading(false); }
  }

  function updateWindows(next: ConversationWindow[] | ((items: ConversationWindow[]) => ConversationWindow[])) {
    const items = typeof next === 'function' ? next(windowsRef.current) : next;
    windowsRef.current = items; setWindows(items);
    if (homeRef.current) writeWorkspace(homeRef.current, { windows: items });
  }

  function updateClosedWindows(next: ConversationWindow[] | ((items: ConversationWindow[]) => ConversationWindow[])) {
    const items = typeof next === 'function' ? next(closedWindowsRef.current) : next;
    closedWindowsRef.current = items; setClosedWindows(items);
    if (homeRef.current) writeWorkspace(homeRef.current, { closedWindows: items });
  }

  function saveConversationDraft(kb: string, id: string | null, text: string) {
    if (!id) return; // Blank conversations are stored by their unique window keys.
    const saved = readWorkspace(homeRef.current);
    writeWorkspace(homeRef.current, { drafts: { ...saved.drafts, [draftKey(kb, id)]: text } });
  }

  function changeQuery(text: string) {
    setQuery(text);
    if (tab === 'ask') {
      updateWindows(items => items.map(item => item.key === activeWindow.current ? { ...item, draft: text } : item));
      saveConversationDraft(selected, activeId, text);
      if (!text && unconfirmed && unconfirmed.kb === selected
        && (!unconfirmed.window_key || unconfirmed.window_key === activeWindow.current)) {
        setUnconfirmed(null); writeWorkspace(homeRef.current, { outbox: null });
      }
    }
  }

  function changeWebSearch(enabled: boolean) {
    setWebSearch(enabled);
    updateWindows(items => items.map(item => item.key === activeWindow.current ? { ...item, webSearch: enabled } : item));
  }

  function blankWindow(kb: string, forceNew = false): ConversationWindow {
    const existing = !forceNew && windowsRef.current.find(item => item.kb === kb && !item.conversationId);
    if (existing) return existing;
    const item = { key: crypto.randomUUID(), kb, conversationId: null, title: '新对话',
      draft: forceNew ? '' : draft(homeRef.current, kb, null), webSearch: false };
    updateWindows(items => [...items, item]);
    if (item.draft) {
      const saved = readWorkspace(homeRef.current);
      writeWorkspace(homeRef.current, { drafts: { ...saved.drafts, [draftKey(kb, null)]: '' } });
    }
    return item;
  }

  function activateBlank(item: ConversationWindow, activateConversation = true) {
    ++viewVersion.current;
    activeWindow.current = item.key; setActiveWindowKey(item.key); setWebSearch(item.webSearch);
    if (activateConversation) setTab('ask');
    setNavigationOpen(false);
    const changed = selection.current !== item.kb;
    selection.current = item.kb; setSelected(item.kb); setQuery(item.draft); setMatches(null);
    setActiveId(null); setConversation(null); setConversationLoading(false); setSource(null); setSourceGroup([]); setImports([]); setError(null); setMessage(null);
    if (changed) setDocuments([]);
    if (item.kb) void loadDocuments(item.kb);
  }

  function switchWindow(item: ConversationWindow) {
    if (item.key === activeWindow.current && tab === 'ask') return;
    if (item.conversationId) void openConversation(item.conversationId);
    else activateBlank(item);
  }

  function closeWindow(key: string) {
    const index = windowsRef.current.findIndex(item => item.key === key);
    const closed = windowsRef.current[index];
    if (!closed) return;
    if (closed.draft) updateClosedWindows(items => [...items.filter(item => item.key !== key), closed]);
    const remaining = windowsRef.current.filter(item => item.key !== key);
    updateWindows(remaining);
    if (activeWindow.current === key) {
      focusNewQuestion.current = true; setFocusRequest(value => value + 1);
      const next = remaining[Math.max(0, index - 1)] || blankWindow(selected, true);
      switchWindow(next);
    }
  }

  function restoreDraft() {
    const item = [...closedWindowsRef.current].reverse().find(window => bases.some(kb => kb.id === window.kb));
    if (!item) return;
    focusNewQuestion.current = true; setFocusRequest(value => value + 1);
    if (item.conversationId) { void openConversation(item.conversationId); return; }
    updateWindows(items => [...items, item]);
    updateClosedWindows(items => items.filter(window => window.key !== item.key));
    activateBlank(item);
  }

  function selectBase(id: string, activateConversation = true) {
    activateBlank(blankWindow(id), activateConversation);
  }

  async function loadHistory(offset = 0) {
    const version = ++historyVersion.current;
    setHistoryLoading(true);
    try {
      const page = await request<ConversationPage>('conversations.list', { offset, limit: 50, query: historyFilter.current });
      if (version !== historyVersion.current) return;
      setHistory(old => offset ? [...new Map([...old, ...page.items].map(item => [item.id, item])).values()] : page.items);
      setHistoryMore(page.has_more);
    } catch (e) { if (version === historyVersion.current) setError(errorMessage(e)); }
    finally { if (version === historyVersion.current) setHistoryLoading(false); }
  }

  function searchHistory(value: string) {
    historyFilter.current = value;
    ++historyVersion.current;
    setHistoryQuery(value); setHistory([]); setHistoryMore(false); setHistoryLoading(true);
    clearTimeout(historySearchTimer.current);
    historySearchTimer.current = setTimeout(() => { void loadHistory(); }, 200);
  }

  async function renameConversation(title: string) {
    if (!renameTarget || busy) return;
    const id = renameTarget.id;
    setBusy('rename'); setRenameError(null);
    try {
      const detail = await request<ConversationDetail>('conversations.rename', { conversation_id: id, title });
      updateWindows(items => items.map(item => item.conversationId === id ? { ...item, title: detail.title } : item));
      setConversation(old => old?.id === id ? { ...old, title: detail.title, updated_at: detail.updated_at } : old);
      setRenameTarget(null); setMessage('对话标题已保存。');
      await loadHistory();
    } catch (e) { setRenameError(errorMessage(e)); }
    finally { setBusy(null); }
  }

  async function loadTrash() {
    setTrashLoading(true);
    try { setTrash(await request<TrashItem[]>('trash.list')); }
    catch (e) { setError(errorMessage(e)); }
    finally { setTrashLoading(false); }
  }

  async function openConversation(id: string, existing?: ConversationDetail) {
    const version = ++viewVersion.current;
    const summary = existing || history.find(item => item.id === id);
    let window = windowsRef.current.find(item => item.conversationId === id);
    if (!window) {
      window = closedWindowsRef.current.find(item => item.conversationId === id) || { key: crypto.randomUUID(), kb: summary?.knowledge_base_id || selection.current, conversationId: id,
        title: summary?.title || '对话', draft: draft(homeRef.current, summary?.knowledge_base_id || selection.current, id), webSearch: false };
      updateWindows(items => [...items, window!]);
    }
    const key = window.key;
    activeWindow.current = key; setActiveWindowKey(key); setWebSearch(window.webSearch);
    setNavigationOpen(false); setTab('ask'); setActiveId(id); setConversation(null); setConversationLoading(true);
    setSource(null); setSourceGroup([]); setError(null); setMessage(null);
    setQuery(window.draft);
    try {
      const detail = existing || await request<ConversationDetail>('conversations.get', { conversation_id: id });
      updateWindows(items => items.map(item => item.key === key ? { ...item, kb: detail.knowledge_base_id, title: detail.title } : item));
      updateClosedWindows(items => items.filter(item => item.conversationId !== id));
      if (viewVersion.current !== version) return;
      setConversation(detail);
      if (selection.current !== detail.knowledge_base_id) {
        selection.current = detail.knowledge_base_id; setSelected(detail.knowledge_base_id); setDocuments([]);
        void loadDocuments(detail.knowledge_base_id);
      }
    } catch (e) {
      if (viewVersion.current === version) {
        updateWindows(items => items.filter(item => item.key !== key));
        activateBlank(blankWindow(selection.current)); setError(errorMessage(e));
      }
    } finally { if (viewVersion.current === version) setConversationLoading(false); }
  }

  async function initialize() {
    setStartup(true); setError(null);
    try {
      const data = await request<Bootstrap>('initialize');
      homeRef.current = data.settings.home;
      const saved = readWorkspace(data.settings.home);
      setStreamingEnabled(saved.streamingEnabled !== false);
      setBases(data.knowledge_bases); setSettings(data.settings);
      updateClosedWindows(Array.isArray(saved.closedWindows) ? saved.closedWindows.filter(item => item
        && typeof item.key === 'string' && typeof item.kb === 'string' && typeof item.title === 'string'
        && typeof item.draft === 'string' && item.draft.length > 0 && typeof item.webSearch === 'boolean'
        && (item.conversationId === null || typeof item.conversationId === 'string')) : []);
      const restored = Array.isArray(saved.windows) ? saved.windows.filter(item => item && typeof item.key === 'string'
        && typeof item.title === 'string' && typeof item.draft === 'string' && typeof item.webSearch === 'boolean'
        && (item.conversationId === null || typeof item.conversationId === 'string')
        && data.knowledge_bases.some(kb => kb.id === item.kb)).filter((item, index, list) => list.findIndex(other => other.key === item.key
          || !!item.conversationId && other.conversationId === item.conversationId) === index) : [];
      updateWindows(restored);
      const drafts = { ...saved.drafts };
      for (const item of restored) if (!item.conversationId) delete drafts[draftKey(item.kb, null)];
      writeWorkspace(homeRef.current, { drafts });
      const current = data.knowledge_bases.find(kb => kb.id === saved.lastKb) || data.knowledge_bases[0];
      if (restored.length) {
        selection.current = current?.id || ''; setSelected(selection.current);
        if (selection.current) void loadDocuments(selection.current);
      } else selectBase(current?.id || '');
      await loadHistory();
      if (saved.outbox) {
        try {
          const recovered = await request<ConversationDetail>('conversations.get', { request_id: saved.outbox.request_id });
          updateWindows(items => items.map(item => item.key === saved.outbox!.window_key
            ? { ...item, conversationId: recovered.id, title: recovered.title, draft: '' } : item));
          updateClosedWindows(items => items.filter(item => item.key !== saved.outbox!.window_key));
          saveConversationDraft(saved.outbox.kb, recovered.id, '');
          await openConversation(recovered.id, recovered);
          writeWorkspace(homeRef.current, { outbox: null });
        } catch {
          if (data.knowledge_bases.some(kb => kb.id === saved.outbox!.kb)) {
            const originalWindow = windowsRef.current.find(item => item.key === saved.outbox!.window_key && !item.conversationId);
            if (originalWindow) activateBlank(originalWindow); else selectBase(saved.outbox.kb);
            changeQuery(saved.outbox.question); changeWebSearch(!!saved.outbox.web_search); setUnconfirmed(saved.outbox);
          }
        }
      } else {
        const savedWindow = restored.find(item => item.key === saved.activeWindowKey) || restored[0];
        if (savedWindow?.conversationId) await openConversation(savedWindow.conversationId);
        else if (savedWindow) activateBlank(savedWindow);
        else if (saved.lastConversationId) await openConversation(saved.lastConversationId);
      }
      if (!data.settings.effective.embedding_ready || !data.settings.effective.api_key_configured) setSettingsOpen(true);
    } catch (e) { setError(errorMessage(e)); }
    finally { setStartup(false); }
  }

  useEffect(() => { void initialize(); let off: (() => void) | undefined; let disposed = false;
    void handleWindowClose(() => busyRef.current).then(cleanup => { if (disposed) cleanup(); else off = cleanup; });
    return () => { disposed = true; off?.(); };
  }, []);

  async function refresh() {
    const version = viewVersion.current;
    const conversationId = activeConversation.current;
    try {
      const [items, config] = await Promise.all([request<KnowledgeBase[]>('kb.list'), request<SettingsSnapshot>('settings.get')]);
      setBases(items); setSettings(config);
      updateWindows(windows => windows.filter(window => items.some(kb => kb.id === window.kb)));
      if (items.some(kb => kb.id === selection.current)) await loadDocuments(selection.current);
      else selectBase(items[0]?.id || '');
      await loadHistory();
      if (tab === 'trash') await loadTrash();
      if (conversationId && viewVersion.current === version && items.some(kb => kb.id === selection.current)) {
        try {
          const detail = await request<ConversationDetail>('conversations.get', { conversation_id: conversationId });
          if (viewVersion.current === version && activeConversation.current === conversationId) setConversation(detail);
        } catch (e) {
          if (viewVersion.current !== version || activeConversation.current !== conversationId) return;
          if (!/对话不存在|已移入回收站/.test(errorMessage(e))) throw e;
          updateWindows(items => items.filter(window => window.conversationId !== conversationId));
          if (workspaceTab.current === 'ask') newQuestion();
          else { setActiveId(null); setConversation(null); }
          setMessage('当前对话已移入回收站或被彻底删除，可在回收站查看。');
        }
      }
    } catch (e) { setError(errorMessage(e)); }
  }

  async function createBase(event: React.FormEvent) {
    event.preventDefault(); if (!newName.trim() || busy) return;
    setBusy('create'); setError(null);
    try {
      const created = await request<KnowledgeBase>('kb.create', { name: newName.trim() });
      setBases(await request<KnowledgeBase[]>('kb.list')); selectBase(created.id); setNewOpen(false); setNewName('');
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(null); }
  }

  function openNew(event?: React.MouseEvent<HTMLButtonElement>) {
    modalTrigger.current = navigationVisible ? navigationTrigger.current : event?.currentTarget || null;
    event?.currentTarget.focus();
    setNavigationOpen(false);
    if (!settings?.effective.embedding_model || !settings.effective.embedding_dimension) { setSettingsOpen(true); return; }
    setNewOpen(true);
  }

  function openSettings(event: React.MouseEvent<HTMLButtonElement>) {
    modalTrigger.current = navigationVisible ? navigationTrigger.current : event.currentTarget;
    event.currentTarget.focus();
    setNavigationOpen(false);
    setSettingsOpen(true);
  }

  function openSource(item: Source, trigger: HTMLElement, sources: Source[] = [item]) {
    sourceTrigger.current = trigger;
    setSourceHidden(false);
    setSourceGroup(sources);
    setSource(item);
  }

  function collapseSource() {
    setSourceHidden(true);
    queueMicrotask(() => sourceToggle.current?.focus());
  }

  async function deleteBase() {
    if (!base || busy) return;
    const captured = base;
    if (!await confirmAction(`将「${captured.name}」及其文档和对话移入回收站？之后可以恢复。`)) return;
    setBusy('delete'); setError(null);
    try { await request('kb.delete', { kb: captured.id });
      updateWindows(items => items.filter(item => item.kb !== captured.id));
      const items = await request<KnowledgeBase[]>('kb.list'); setBases(items); selectBase(items[0]?.id || '');
      await loadHistory(); setMessage('知识库已移入回收站，可在回收站中恢复。');
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(null); }
  }

  async function importDocuments() {
    if (!selected || busy) return;
    const kb = selected;
    let paths: string[];
    try { paths = await chooseFiles(); } catch (e) { setError(errorMessage(e)); return; }
    if (!paths.length) return;
    setTab('documents');
    setBusy('import'); setError(null); setMessage(null);
    const entries: ImportEntry[] = paths.map(path => ({ path, status: 'pending' }));
    if (selection.current === kb) setImports([...entries]);
    try {
      for (let i = 0; i < paths.length; i++) {
        try { const result = await request<ImportResult>('docs.import', { kb, path: paths[i] });
          entries[i] = { path: paths[i], status: result.imported ? 'imported' : 'duplicate' };
        } catch (e) { entries[i] = { path: paths[i], status: 'failed', message: errorMessage(e) }; }
        if (selection.current === kb) setImports([...entries]);
      }
      if (selection.current === kb) {
        await loadDocuments(kb);
        setMessage(`处理完成：${entries.filter(e => e.status === 'imported').length} 个导入，${entries.filter(e => e.status === 'duplicate').length} 个重复跳过，${entries.filter(e => e.status === 'failed').length} 个失败。`);
      }
    } finally { setBusy(null); }
  }

  function generationEvents(windowKey: string, requestId: string) {
    let accepted = false;
    generationRef.current = { windowKey, requestId, text: '', phase: 'searching', stopping: false };
    setGeneration(generationRef.current);
    return { accepted: () => accepted, onEvent: (event: TurnEvent) => {
      const previous = generationRef.current;
      if (!previous || previous.requestId !== event.request_id) return;
      const next = { ...previous, conversationId: event.conversation_id };
      if (event.type === 'started') {
        accepted = true;
        const detail = event.conversation;
        updateWindows(items => items.map(item => item.key === windowKey ? { ...item, conversationId: detail.id, title: detail.title, draft: '' } : item));
        updateClosedWindows(items => items.filter(item => item.key !== windowKey));
        saveConversationDraft(detail.knowledge_base_id, detail.id, '');
        writeWorkspace(homeRef.current, { outbox: null }); setUnconfirmed(null);
        if (workspaceTab.current === 'ask' && (activeWindow.current === windowKey || activeConversation.current === detail.id)) {
          setConversation(detail); setActiveId(detail.id);
        }
        void loadHistory();
      } else if (event.type === 'delta') next.text += event.text;
      else if (!next.stopping) next.phase = event.phase;
      generationRef.current = next; setGeneration(next);
    } };
  }

  function finishGeneration() { generationRef.current = null; setGeneration(null); }

  async function stopGeneration() {
    const active = generationRef.current;
    if (!active || active.stopping) return;
    generationRef.current = { ...active, stopping: true, phase: 'stopping' }; setGeneration(generationRef.current);
    try { await request('conversations.cancel', { request_id: active.requestId }); }
    catch (e) {
      if (generationRef.current?.requestId === active.requestId) {
        generationRef.current = { ...generationRef.current, stopping: false }; setGeneration(generationRef.current);
      }
      setError(errorMessage(e));
    }
  }

  async function exportCurrentConversation() {
    if (!conversation || currentGeneration || exporting || conversationLoading || conversation.messages.some(item => item.status === 'pending')) return;
    setExporting(true); setError(null);
    try {
      const result = await exportConversation(conversation.id);
      if (result.saved) setMessage(`对话已导出：${result.filename}`);
    } catch (e) { setError(errorMessage(e)); }
    finally { setExporting(false); }
  }

  async function runQuery(event?: React.FormEvent, suggestion?: string, requestedMode?: 'search' | 'ask') {
    event?.preventDefault(); const text = (suggestion || query).trim();
    if (!text || !selected || busy || conversationLoading) return;
    const kb = selected; const mode = requestedMode || (tab === 'search' ? 'search' : 'ask');
    const version = viewVersion.current;
    const windowKey = activeWindow.current;
    setQuery(mode === 'search' ? text : ''); setBusy(mode); setError(null); setMessage(null); setSource(null);
    const outgoing: Outbox = unconfirmed && unconfirmed.kb === kb && unconfirmed.question === text
      && (!unconfirmed.window_key || unconfirmed.window_key === windowKey)
      && unconfirmed.conversation_id === (activeId || undefined) && !!unconfirmed.web_search === webSearch ? unconfirmed
      : { kb, question: text, request_id: crypto.randomUUID(), window_key: windowKey, ...(activeId ? { conversation_id: activeId } : {}), ...(webSearch ? { web_search: true } : {}) };
    if (mode === 'ask') {
      setPendingTurn({ view: version, windowKey, request: outgoing }); writeWorkspace(homeRef.current, { outbox: outgoing });
    }
    const progress = mode === 'ask' ? generationEvents(windowKey, outgoing.request_id) : null;
    try {
      if (mode === 'search') {
        const result = await request<Source[]>('search', { kb, question: text, top_k: 5 });
        if (selection.current === kb && viewVersion.current === version) setMatches(result);
      } else {
        const result = await streamRequest('conversations.send', { ...outgoing, stream: streamingEnabled }, progress!.onEvent);
        writeWorkspace(homeRef.current, { outbox: null }); setUnconfirmed(null);
        updateWindows(items => items.map(item => item.key === windowKey ? { ...item, conversationId: result.id, title: result.title, draft: '' } : item));
        updateClosedWindows(items => items.filter(item => item.key !== windowKey));
        saveConversationDraft(kb, outgoing.conversation_id || null, '');
        saveConversationDraft(kb, result.id, '');
        if (workspaceTab.current === 'ask' && selection.current === kb && (activeWindow.current === windowKey || activeConversation.current === result.id)) {
          setConversation(result); setActiveId(result.id);
          const sources = result.messages.filter(message => message.role === 'assistant').at(-1)?.citations || [];
          if (!overlaySource && workspaceTab.current === 'ask' && viewVersion.current === version) { setSource(sources[0] || null); setSourceGroup(sources); }
        }
        await loadHistory();
      }
    } catch (e) {
      if (mode === 'ask' && !progress?.accepted()) {
        setUnconfirmed(outgoing);
        updateWindows(items => items.map(item => item.key === windowKey ? { ...item, draft: text } : item));
      }
      if (selection.current === kb && viewVersion.current === version) {
        setError(errorMessage(e));
        if (mode === 'ask' && !progress?.accepted()) setQuery(text);
      }
      if (progress?.accepted()) {
        try {
          const detail = await request<ConversationDetail>('conversations.get', { request_id: outgoing.request_id });
          if (activeConversation.current === detail.id) setConversation(detail);
        } catch { /* The persisted question is recovered on restart. */ }
      }
    } finally { setBusy(null); setPendingTurn(null); if (mode === 'ask') finishGeneration(); }
  }

  async function retryQuestion(requestId: string) {
    if (busy) return;
    const version = viewVersion.current;
    setBusy('ask'); setError(null);
    const windowKey = activeWindow.current;
    const original = conversation?.messages.find(item => item.request_id === requestId);
    if (original) setPendingTurn({ view: version, windowKey, request: { request_id: requestId, kb: selected, question: original.content } });
    const progress = generationEvents(windowKey, requestId);
    try {
      const detail = await streamRequest('conversations.retry', { request_id: requestId, stream: streamingEnabled }, progress.onEvent);
      if ((activeWindow.current === windowKey && viewVersion.current === version) || activeConversation.current === detail.id) setConversation(detail);
      await loadHistory();
    } catch (e) { if (viewVersion.current === version) setError(errorMessage(e)); }
    finally { setBusy(null); setPendingTurn(null); finishGeneration(); }
  }

  async function deleteConversation(item: ConversationSummary) {
    if (busy || !await confirmAction(`将对话「${item.title}」移入回收站？之后可以恢复。`)) return;
    const version = viewVersion.current;
    setBusy('delete'); setError(null);
    try {
      await request('conversations.delete', { conversation_id: item.id });
      updateWindows(items => items.filter(window => window.conversationId !== item.id));
      if (activeId === item.id && viewVersion.current === version) newQuestion();
      await loadHistory(); setMessage('对话已移入回收站。');
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(null); }
  }

  async function trashAction(action: 'restore' | 'purge' | 'empty', item?: TrashItem) {
    if (busy) return;
    if (action !== 'restore' && !await confirmAction(action === 'empty' ? '确认清空回收站？其中的知识库和对话将无法恢复。' : `确认彻底删除「${item!.title}」？此操作无法恢复。`)) return;
    setBusy('trash'); setError(null);
    try {
      await request(`trash.${action}`, item ? { kind: item.kind, item_id: item.id } : {});
      const items = await request<KnowledgeBase[]>('kb.list'); setBases(items);
      updateWindows(windows => windows.filter(window => items.some(kb => kb.id === window.kb)));
      if (!items.some(kb => kb.id === selection.current)) selectBase(items[0]?.id || '', false);
      await Promise.all([loadHistory(), loadTrash()]);
      setMessage(action === 'restore' ? '项目已恢复。' : action === 'empty' ? '回收站已清空。' : '项目已彻底删除。');
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(null); }
  }

  async function previewDocument(document: DocumentRecord, trigger: HTMLElement) {
    const kb = selected;
    const version = viewVersion.current;
    try { const excerpt = await request<Source | null>('docs.preview', { kb, document_id: document.id });
      if (selection.current === kb && viewVersion.current === version) { if (excerpt) openSource(excerpt, trigger); else setMessage('此文档尚没有可预览的有效片段。'); }
    } catch (e) { setError(errorMessage(e)); }
  }

  function changeTab(next: Tab) {
    if (next !== tab) ++viewVersion.current;
    setTab(next); setQuery(next === 'ask' ? windowsRef.current.find(item => item.key === activeWindow.current)?.draft || '' : ''); setSource(null); setError(null);
    if (next === 'trash') void loadTrash();
  }

  function newQuestion() {
    focusNewQuestion.current = true;
    setFocusRequest(value => value + 1);
    activateBlank(blankWindow(selected, true));
  }

  const relatedSources = tab === 'ask' ? sourceGroup : tab === 'search' ? matches || [] : source ? [source] : [];

  function navigateTabs(event: React.KeyboardEvent<HTMLDivElement>) {
    const tabs: Tab[] = ['ask', 'search', 'documents', 'trash'];
    const index = tabs.indexOf(tab);
    const next = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? (index + 1) % tabs.length
      : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? (index + tabs.length - 1) % tabs.length
      : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
    if (next === null) return;
    event.preventDefault(); changeTab(tabs[next]);
    document.getElementById(`tab-${tabs[next]}`)?.focus();
  }

  return <div className={`app-shell ${sidebarHidden && !compactNavigation ? 'sidebar-hidden' : ''}`}>
    <div className="titlebar-region">
      <Titlebar compact={compactNavigation} locked={modalOpen || sourceModal || navigationVisible || expandedSource} theme={theme} onTheme={() => setTheme(theme === 'light' ? 'dark' : 'light')} onSettings={openSettings} disabled={!!busy || startup || !settings} onQuery={text => {
        const mode = tab === 'ask' ? 'ask' : 'search'; if (mode !== tab) changeTab(mode); void runQuery(undefined, text, mode);
      }} sidebarHidden={sidebarHidden} sidebarExpanded={compactNavigation ? navigationVisible : !sidebarHidden} sidebarTriggerRef={navigationTrigger} onSidebar={() => compactNavigation ? setNavigationOpen(true) : setSidebarHidden(!sidebarHidden)} />
    </div>
    {navigationVisible && <div className="navigation-backdrop" onClick={() => setNavigationOpen(false)} aria-hidden="true" />}
    <aside ref={navigationRef} id="knowledge-navigation" className={`sidebar ${navigationVisible ? 'is-open' : ''}`}
      inert={modalOpen || sourceModal || expandedSource || (compactNavigation ? !navigationOpen : sidebarHidden)}
      aria-label="知识库导航" role={navigationVisible ? 'dialog' : undefined} aria-modal={navigationVisible || undefined}
      tabIndex={navigationVisible ? -1 : undefined}>
      <div className="mobile-sidebar-heading"><strong>mini-ima</strong>
        <button className="icon-button close-navigation" aria-label="关闭知识库导航" onClick={() => setNavigationOpen(false)}><X size={20} /></button>
      </div>
      <button className="sidebar-new-conversation" disabled={startup || (!!busy && busy !== 'ask')} onClick={() => { newQuestion(); setNavigationOpen(false); }}><Plus size={19} />新建对话</button>
      <div className="primary-nav" role="tablist" aria-label="知识库工作区" aria-orientation="vertical" onKeyDown={navigateTabs}>
        <button id="tab-ask" role="tab" aria-label="问答" aria-controls="panel-ask" aria-selected={tab === 'ask'} tabIndex={tab === 'ask' ? 0 : -1}
          className={tab === 'ask' ? 'selected' : ''} onClick={() => { changeTab('ask'); setNavigationOpen(false); }}><MessageCircleMore size={21} />AI 问答</button>
        <button id="tab-search" role="tab" aria-label="搜索" aria-controls="panel-search" aria-selected={tab === 'search'} tabIndex={tab === 'search' ? 0 : -1}
          className={tab === 'search' ? 'selected' : ''} onClick={() => { changeTab('search'); setNavigationOpen(false); }}><Search size={21} />全局搜索</button>
        <button id="tab-documents" role="tab" aria-label={`文档 ${documents.length}`} aria-controls="panel-documents" aria-selected={tab === 'documents'} tabIndex={tab === 'documents' ? 0 : -1}
          className={tab === 'documents' ? 'selected' : ''} onClick={() => { changeTab('documents'); setNavigationOpen(false); }}><Archive size={21} />知识库</button>
        <button id="tab-trash" role="tab" aria-label="回收站" aria-controls="panel-trash" aria-selected={tab === 'trash'} tabIndex={tab === 'trash' ? 0 : -1}
          className={tab === 'trash' ? 'selected' : ''} onClick={() => { changeTab('trash'); setNavigationOpen(false); }}><Trash2 size={21} />回收站</button>
      </div>
      <div className="history-heading sidebar-label">历史对话<span>{historyLoading && <Loader2 size={14} className="spin" />}</span></div>
      <div className="history-search"><Search size={15} /><input aria-label="搜索历史对话" placeholder="搜索对话标题" maxLength={200} disabled={startup}
        value={historyQuery} onChange={event => searchHistory(event.target.value)} />
        {historyQuery && <button className="icon-button" aria-label="清空历史搜索" onClick={() => searchHistory('')}><X size={14} /></button>}</div>
      <nav className="conversation-history" aria-label="历史对话">
        {history.map(item => <div className={`history-row ${activeId === item.id ? 'selected' : ''}`} key={item.id}>
          <button className="history-open" aria-current={activeId === item.id ? 'true' : undefined} title={item.title} onClick={() => void openConversation(item.id)}><MessageSquare size={16} /><span><strong>{item.title}</strong><small>{item.knowledge_base_name}</small></span></button>
          <button className="icon-button history-rename" title="重命名" aria-label={`重命名对话：${item.title}`} disabled={!!busy || conversationLoading}
            onClick={event => { modalTrigger.current = event.currentTarget; setRenameTarget(item); setRenameError(null); }}><Pencil size={14} /></button>
          <button className="icon-button history-delete" aria-label={`删除对话：${item.title}`} disabled={!!busy} onClick={() => void deleteConversation(item)}><Trash2 size={14} /></button>
        </div>)}
        {!history.length && !historyLoading && <p className="sidebar-empty">{historyQuery ? '未找到匹配的对话' : '新问题会保存在这里'}</p>}
        {historyMore && <button className="history-more text-button" disabled={historyLoading} onClick={() => void loadHistory(history.length)}>加载更多对话</button>}
      </nav>
      <div className="sidebar-label">我的知识库 <button className="icon-button" aria-label="新建知识库" title="新建知识库" disabled={!!busy || startup} onClick={openNew}><Plus size={19} /></button></div>
      <nav className="library-list" aria-label="知识库列表">
        {bases.map((kb, index) => <button key={kb.id} title={kb.name} aria-current={selected === kb.id ? 'page' : undefined}
          className={`library-item library-color-${index % 5} ${selected === kb.id ? 'active' : ''}`} onClick={() => selectBase(kb.id)}>
          <FileText size={19} /><span>{kb.name}</span>{selected === kb.id && <small>{documents.length}</small>}
        </button>)}
        {!startup && !bases.length && <p className="sidebar-empty">暂无知识库</p>}
      </nav>
      <details className="recent-documents"><summary className="sidebar-label">最近文档<ChevronDown size={15} /></summary>
        {documents.slice(0, 3).map(doc => <button key={doc.id} className="recent-document" title={doc.filename} onClick={event => {
          changeTab('documents'); setNavigationOpen(false); void previewDocument(doc, event.currentTarget);
        }}><span className={`recent-file ${doc.source_type === 'markdown' ? 'is-markdown' : ''}`}><FileText size={21} /></span>
          <span><strong>{doc.filename}</strong><small>{date(doc.created_at)}</small></span></button>)}
        {!documents.length && <p className="sidebar-empty">暂无文档</p>}
        <button className="recent-more" onClick={() => { changeTab('documents'); setNavigationOpen(false); }}><MoreHorizontal size={20} />更多...</button>
      </details>
      <div className="sidebar-bottom">
        {compactNavigation && <button className="sidebar-settings" disabled={!settings || !!busy} onClick={openSettings}>
          <Settings2 size={18} />模型与设置<ChevronRight size={16} />
        </button>}
      </div>
    </aside>
    <main className="workspace" inert={modalOpen || sourceModal || navigationVisible}>
      <div className={`workspace-content ${!overlaySource && !sourceHidden ? 'with-source' : ''}`}>
      <div className="editor-pane" inert={expandedSource}>
      <header className="workspace-header">
        <h1 className="sr-only">{base?.name || '构建你的知识空间'}</h1>
        {tab === 'ask' && <button className="text-button export-conversation" disabled={!conversation?.messages.length || !!currentGeneration || exporting || conversationLoading || conversation.messages.some(item => item.status === 'pending')}
          onClick={() => void exportCurrentConversation()}><FileDown size={17} />{exporting ? '正在导出…' : '导出对话'}</button>}
        <ConversationTabs windows={windows} activeKey={tab === 'ask' ? activeWindowKey : ''}
          pendingKey={pendingTurn?.windowKey} disabled={startup || (!!busy && busy !== 'ask')} onSwitch={switchWindow} onClose={closeWindow} onNew={newQuestion}
          closedDrafts={closedWindows.filter(window => bases.some(kb => kb.id === window.kb)).length} onRestoreDraft={restoreDraft} />
        <div className="header-actions">
          <label className="base-selector">知识库：<select aria-label="当前知识库" value={selected} onChange={event => selectBase(event.target.value)}>
            {!bases.length && <option value="">暂无知识库</option>}{bases.map(kb => <option value={kb.id} key={kb.id}>{kb.name}</option>)}
          </select><ChevronDown size={15} /></label>
          <button className="icon-button refresh-button" aria-label="刷新知识库" title="刷新 CLI 导入的数据"
            disabled={!!busy || startup} onClick={refresh}><History size={21} /></button>
          {base && tab === 'documents' && <button className="icon-button delete-button" aria-label="删除当前知识库" title="删除当前知识库"
            disabled={!!busy} onClick={deleteBase}><Trash2 size={18} /></button>}
          {!overlaySource && <button ref={sourceToggle} className="icon-button source-toggle" aria-label={sourceHidden ? '展开来源栏' : '收起来源栏'} title={sourceHidden ? '展开来源栏' : '收起来源栏'}
            aria-expanded={!sourceHidden} onClick={() => setSourceHidden(!sourceHidden)}>{sourceHidden ? <PanelRightOpen size={19} /> : <PanelRightClose size={19} />}</button>}
        </div>
      </header>

      {error && <div className="workspace-notice notice error" role="alert">
        <AlertCircle size={18} /><span>{error}</span>
        <button className="icon-button" aria-label="关闭错误" onClick={() => setError(null)}><X size={18} /></button>
        {!settings && <button className="text-button" onClick={initialize}>重试</button>}
      </div>}
      {message && <div className="workspace-notice notice success" role="status">
        <Check size={18} /><span>{message}</span>
        <button className="icon-button" aria-label="关闭提示" onClick={() => setMessage(null)}><X size={18} /></button>
      </div>}

      {startup ? <div className="center-state"><Loader2 size={24} className="spin" /><p>正在打开你的知识空间…</p></div>
        : tab === 'trash' ? <div className="content-column trash-column"><TrashView items={trash} loading={trashLoading} busy={!!busy}
          onRestore={item => void trashAction('restore', item)} onPurge={item => void trashAction('purge', item)} onEmpty={() => void trashAction('empty')} /></div>
        : !base ? <div className="welcome-state">
          <div className="welcome-art"><BookOpen size={34} /></div>
          <h2>让你的资料，成为答案。</h2>
          <p>创建知识库，导入笔记与文档。<br />用自然语言搜索，找到资料里的线索。</p>
          <button className="primary-button" onClick={openNew}><Plus size={18} />创建第一个知识库</button>
          <div className="welcome-features">
            <span><FileText size={17} />TXT / Markdown</span>
            <span><Search size={17} />语义搜索</span>
            <span><Sparkles size={17} />有来源的问答</span>
          </div>
        </div> : <>
            <div className="content-column" ref={contentRef}>
              {tab === 'documents' && <section className="documents-view" id="panel-documents" role="tabpanel" aria-labelledby="tab-documents">
                <div className="section-heading">
                  <div><h2>知识库文档</h2><p>{documents.length} 个文档 · {documents.reduce((sum, d) => sum + d.chunk_count, 0)} 个知识片段</p></div>
                  <button className="primary-button" disabled={!!busy} onClick={importDocuments}>
                    {busy === 'import' ? <Loader2 size={18} className="spin" /> : <Upload size={18} />}导入文档
                  </button>
                </div>
                {imports.length > 0 && <div className="import-progress" aria-label="导入进度">
                  <div className="progress-heading">{busy === 'import' ? '正在处理文档' : '本次导入'}
                    <span>{imports.filter(item => item.status !== 'pending').length} / {imports.length}</span>
                  </div>
                  <div className="progress-track" role="progressbar" aria-label="文档处理进度" aria-valuemin={0}
                    aria-valuemax={imports.length} aria-valuenow={imports.filter(item => item.status !== 'pending').length}>
                    <div style={{ width: `${imports.filter(item => item.status !== 'pending').length / imports.length * 100}%` }} />
                  </div>
                  {imports.map((item, i) => <div className="import-result" key={i}>
                    {item.status === 'pending' ? <Loader2 size={16} className="spin" /> : item.status === 'failed' ? <AlertCircle size={16} /> : <Check size={16} />}
                    <span title={item.path}>{filename(item.path)}</span>
                    <span className={item.status === 'failed' ? 'failure' : ''}>
                      {item.status === 'pending' ? '处理中' : item.status === 'imported' ? '已导入' : item.status === 'duplicate' ? '重复，已跳过' : item.message}
                    </span>
                  </div>)}
                </div>}
                {docsLoading ? <div className="document-skeleton" aria-label="加载文档" aria-busy="true">
                  {[0, 1, 2].map(item => <div key={item} aria-hidden="true"><span /><span /><span /></div>)}
                </div> : documents.length ? <div className="document-table">
                  <div className="document-table-header"><span>文档名称</span><span>状态</span><span>知识片段</span><span>导入日期</span></div>
                  {documents.map(doc => <button className={`document-row ${source?.document_id === doc.id ? 'is-selected' : ''}`} aria-current={source?.document_id === doc.id ? 'true' : undefined} key={doc.id} onClick={event => previewDocument(doc, event.currentTarget)}
                    title={doc.error || '查看文档片段'}>
                    <div className={`document-name ${doc.source_type === 'markdown' ? 'markdown-file' : ''}`}>
                      <div className="file-icon"><FileText size={22} /></div>
                      <div><strong>{doc.filename}</strong>
                        <small>{doc.source_type === 'markdown' ? 'Markdown 文档' : '纯文本'}{doc.error && ` · ${doc.error}`}</small>
                      </div>
                    </div>
                    <span className={`status-badge ${doc.status === 'ready' ? 'ready' : 'failed'}`}>
                      {doc.status === 'ready' ? <Check size={13} /> : <AlertCircle size={13} />}{doc.status === 'ready' ? '可用' : '失败'}
                    </span>
                    <span className="chunk-count">{doc.chunk_count}</span><span className="document-date">{date(doc.created_at)}</span>
                  </button>)}
                </div> : <div className="empty-documents">
                  <Layers size={32} /><h3>还没有文档</h3>
                  <p>点击右上方“导入文档”，选择你的第一份资料。<br />支持 TXT、MD 和 Markdown，可一次选择多个文件。</p>
                </div>}
                <div className="quiet-note"><Database size={15} />资料保存在本机，重复内容会自动跳过。</div>
              </section>}

              {tab === 'search' && <section className="search-view" id="panel-search" role="tabpanel" aria-labelledby="tab-search">
                <div className="section-heading"><div><h2>从资料中找到线索</h2><p>输入一个问题或概念，按语义查找相关片段。</p></div></div>
                <form className="search-form" onSubmit={runQuery}>
                  <label htmlFor="knowledge-search">搜索内容</label>
                  <div className="search-input-row"><Search size={20} />
                    <input id="knowledge-search" aria-label="语义搜索" value={query} onChange={e => setQuery(e.target.value)}
                      placeholder="搜索知识库中的内容…" disabled={!!busy} />
                    <button className="primary-button" disabled={!!busy || !query.trim()}>
                      {busy === 'search' ? <Loader2 size={18} className="spin" /> : '搜索'}
                    </button>
                  </div>
                </form>
                {matches === null ? <div className="query-empty">
                  <div className="query-illustration"><Search size={25} /></div>
                  <h3>关键词之外，还有更多关联</h3><p>不必记住原文，用你自己的话描述想找的内容。</p>
                  <div className="query-suggestions">
                    {['这份资料的核心概念是什么？', '有哪些值得关注的细节？'].map(q => <button key={q} disabled={!!busy}
                      onClick={() => runQuery(undefined, q)}>{q}<ChevronRight size={15} /></button>)}
                  </div>
                </div> : <div className="search-results">
                  <div className="results-caption">找到 {matches.length} 个相关片段</div>
                  {matches.map((item, i) => <button className="result-card" key={item.id} onClick={event => openSource(item, event.currentTarget)}>
                    <div className="result-topline"><span className="result-number">{String(i + 1).padStart(2, '0')}</span>
                      <span className="result-filename"><FileText size={16} />{item.filename}</span>
                      <span className="similarity">相似度 {item.score?.toFixed(3)}</span>
                    </div>
                    <h3>{item.source_metadata.heading_path.at(-1) || '文档片段'}</h3><p>{item.content.slice(0, 320)}</p>
                    <div className="result-footer"><span>{location(item)}</span><span>查看来源<ChevronRight size={15} /></span></div>
                  </button>)}
                  {!matches.length && <div className="empty-documents"><p>没有可检索的文档。请先导入资料。</p></div>}
                </div>}
              </section>}

              {tab === 'ask' && <ChatWorkspace conversation={conversation} loading={conversationLoading}
                generation={currentGeneration} onStop={() => void stopGeneration()}
                pendingQuestion={pendingTurn?.windowKey === activeWindowKey ? pendingTurn.request.question : null}
                baseName={base.name} query={query} onQuery={changeQuery} busy={!!busy} webSearch={webSearch} onWebSearch={changeWebSearch}
                questionRef={questionRef} answerRef={answerRef} onSend={runQuery} onImport={importDocuments}
                onRetry={retryQuestion} onSource={openSource} onCopy={text => {
                  void navigator.clipboard.writeText(text).then(() => setMessage('回答已复制。')).catch(() => setError('无法复制，请手动选择文本。'));
                }} />}
            </div>
        </>}
      <footer className="workspace-footer">
        <span>{settings?.effective.embedding_model ? `${settings.effective.embedding_model} · ${settings.effective.embedding_dimension} 维` : '向量模型待配置'}</span>
        <span title={settings?.home}><Database size={14} />本地存储{busy && <span className="busy-status"><Loader2 size={13} className="spin" />正在处理…</span>}</span>
      </footer>
      </div>
      {!overlaySource && !sourceHidden && <SourceDrawer source={source} sources={relatedSources} modal={false} returnFocusTo={sourceTrigger.current} onClose={() => setSource(null)} onCollapse={collapseSource} onSelect={setSource} onExpandedChange={setExpandedSource}
        onOpenWeb={url => { void request('web.open', { url }).catch(e => setError(errorMessage(e))); }} />}
      </div>
    </main>
    {source && overlaySource && <div className="source-backdrop" onClick={event => { if (event.target === event.currentTarget) setSource(null); }}>
      <SourceDrawer source={source} sources={relatedSources} modal returnFocusTo={sourceTrigger.current} onClose={() => setSource(null)} onSelect={setSource} onExpandedChange={setExpandedSource}
        onOpenWeb={url => { void request('web.open', { url }).catch(e => setError(errorMessage(e))); }} />
    </div>}
    <UpdateBanner updates={updates} disabled={!!busy || startup || modalOpen} onDetails={() => {
      modalTrigger.current = document.activeElement as HTMLElement; setSettingsOpen(true);
    }} />
    {settingsOpen && settings && <SettingsDialog returnFocusTo={modalTrigger.current} snapshot={settings} updates={updates}
      streamingEnabled={streamingEnabled} onStreamingChange={enabled => { setStreamingEnabled(enabled); writeWorkspace(homeRef.current, { streamingEnabled: enabled }); }}
      onClose={() => setSettingsOpen(false)} onSaved={setSettings} onBusy={state => setBusy(state ? 'settings' : null)} />}
    {newOpen && <NewKnowledgeBaseDialog returnFocusTo={modalTrigger.current} name={newName} busy={!!busy} error={error} onName={setNewName} onClose={() => setNewOpen(false)} onSubmit={createBase} />}
    {renameTarget && <RenameConversationDialog title={renameTarget.title} busy={busy === 'rename'} error={renameError} returnFocusTo={modalTrigger.current}
      onClose={() => setRenameTarget(null)} onSubmit={title => void renameConversation(title)} />}
  </div>;
}
