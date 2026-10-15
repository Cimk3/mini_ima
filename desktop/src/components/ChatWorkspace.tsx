import type { RefObject } from 'react';
import { BookOpen, ChevronDown, ChevronRight, Copy, Globe, Loader2, Paperclip, RefreshCw, Send, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import assistantIcon from '../assets/reference-assistant.png';
import type { ChatMessage, ConversationDetail, Source } from '../types';

export default function ChatWorkspace({ conversation, pendingQuestion, loading, baseName, query, onQuery, busy,
  questionRef, answerRef, onSend, onImport, onRetry, onSource, onCopy, webSearch, onWebSearch }: {
  conversation: ConversationDetail | null; pendingQuestion: string | null; loading: boolean; baseName: string;
  query: string; onQuery: (text: string) => void; busy: boolean;
  questionRef: RefObject<HTMLTextAreaElement | null>; answerRef: RefObject<HTMLDivElement | null>;
  onSend: (event?: React.FormEvent, suggestion?: string) => void; onImport: () => void;
  onRetry: (requestId: string) => void; onSource: (source: Source, trigger: HTMLElement, sources: Source[]) => void;
  onCopy: (text: string) => void;
  webSearch: boolean; onWebSearch: (enabled: boolean) => void;
}) {
  const messages = conversation?.messages || [];
  const pendingSaved = messages.some(message => message.role === 'user' && message.status === 'pending');
  function renderMessage(message: ChatMessage) {
    if (message.role === 'user') return <div className="chat-turn-user" key={message.id}>
      <div className="user-question"><span className="sr-only">你的问题</span><h2>{message.content}</h2></div>
      {!!message.web_search && <span className="web-search-badge"><Globe size={12} />已联网搜索</span>}
      {(message.status === 'failed' || message.status === 'interrupted') && <div className="turn-error" role="status">
        <span>{message.error || '处理未完成，可重试这个问题。'}</span>
        {message.request_id && <button className="text-button" disabled={busy} onClick={() => onRetry(message.request_id!)}><RefreshCw size={15} />重试问题</button>}
      </div>}
      {message.status === 'pending' && <div className="turn-pending" role="status"><Loader2 size={17} className="spin" />{message.web_search ? '正在联网搜索并整理资料…' : '正在参考知识库回答…'}</div>}
    </div>;
    return <div className="chat-turn-answer" key={message.id}>
      <div className="assistant-message"><div className="assistant-avatar"><img src={assistantIcon} alt="" /></div><div className="answer-card">
        <article className="answer-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml
          components={{ img: () => null, a: ({ children }) => <span>{children}</span> }}>{message.content}</ReactMarkdown></article>
        {!!message.citations.length && <div className="answer-sources"><div className="sources-label"><BookOpen size={18} />参考来源<ChevronDown size={15} /></div>
          {message.citations.map(source => <button key={source.id} title={source.filename} aria-label={`[${source.citation_number}] ${source.filename}`}
            onClick={event => onSource(source, event.currentTarget, message.citations)}>
            <span className="citation-file-icon"><BookOpen size={21} /></span><span className="citation-description"><span className="citation-filename">{source.citation_number}. {source.filename}</span>
              <small>{source.source_metadata.kind === 'web' ? `网页 · ${source.source_metadata.url}` : `行 ${source.source_metadata.line_start}–${source.source_metadata.line_end} · ${source.source_metadata.heading_path.join(' / ') || '文档片段'}`}</small></span>
            {source.score !== undefined && <span className="source-score">{Math.round(Math.max(0, Math.min(1, source.score)) * 100)}%</span>}
          </button>)}
        </div>}
      </div></div>
      <div className="answer-bottom"><button className="text-button" onClick={() => onCopy(message.content)}><Copy size={16} />复制回答</button><span className="saved-answer-note">已保存在本机</span></div>
    </div>;
  }
  return <section className="ask-view" id="panel-ask" role="tabpanel" aria-labelledby="tab-ask">
    {loading ? <div className="conversation-loading" role="status"><Loader2 className="spin" size={22} />正在读取对话…</div>
      : !messages.length && !pendingQuestion ? <div className="ask-intro"><h2>和你的知识，聊一聊。</h2>
        <p>基于「{baseName}」中的资料回答，每一条引用，都能追溯到真实来源。</p>
        <div className="ask-suggestions">{['总结这份资料的主要内容', '有哪些关键概念需要理解？', '帮我梳理资料中的核心观点'].map(question =>
          <button key={question} disabled={busy} onClick={() => onSend(undefined, question)}><Sparkles size={17} />{question}<ChevronRight size={16} /></button>)}</div>
      </div> : <div className="answer-area conversation-messages" ref={answerRef} aria-label="对话消息">
        {messages.map(renderMessage)}
        {pendingQuestion && !pendingSaved && <><div className="user-question"><span className="sr-only">你的问题</span><h2>{pendingQuestion}</h2></div>
          <div className="turn-pending" role="status"><Loader2 size={17} className="spin" />{webSearch ? '正在联网搜索并整理资料…' : '正在参考知识库回答…'}</div></>}
      </div>}
    <form className="ask-composer" onSubmit={onSend}>
      <label className="sr-only" htmlFor="knowledge-question">知识库问题</label>
      <textarea ref={questionRef} id="knowledge-question" aria-label="知识库问题" value={query} onChange={event => onQuery(event.target.value)}
        disabled={busy || loading} placeholder={messages.length ? '继续提问，或开始一个新的问题...' : '提问，搜索知识库中的内容...'} rows={2}
        onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); onSend(); } }} />
      <div className="composer-bottom"><div className="composer-tools">
        <button type="button" disabled={busy} onClick={onImport}><Paperclip size={19} />添加文件</button>
        <button type="button" aria-pressed={webSearch} disabled={busy} onClick={() => onWebSearch(!webSearch)} title="开启后，将当前问题发送至 Bing（备用 DuckDuckGo），结合网页摘要回答"><Globe size={19} />联网搜索{webSearch && <span className="web-search-dot" />}</button>
      </div><button className="send-button" aria-label="发送问题" disabled={busy || loading || !query.trim()}>{busy ? <Loader2 size={20} className="spin" /> : <Send size={22} />}</button></div>
    </form>
    <p className="composer-note sr-only">Enter 发送 · Shift + Enter 换行。同一对话可以连续追问。</p>
  </section>;
}
