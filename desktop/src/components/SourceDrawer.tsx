import { useEffect, useState } from 'react';
import { FileText, MoreHorizontal, ChevronLeft, ChevronRight, Maximize, Minimize, Search, X, PanelRightClose, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Source } from '../types';
import { useDialog } from './useDialog';

export default function SourceDrawer({ source, sources, modal, onClose, onCollapse, onOpenWeb, returnFocusTo, onSelect, onExpandedChange }: {
  source: Source | null;
  sources: Source[];
  modal: boolean;
  onClose: () => void;
  onCollapse?: () => void;
  onOpenWeb: (url: string) => void;
  onSelect: (source: Source) => void;
  onExpandedChange: (expanded: boolean) => void;
  returnFocusTo: HTMLElement | null;
}) {
  const [detail, setDetail] = useState(false);
  const [zoom, setZoom] = useState(100);
  const [expanded, setExpanded] = useState(false);
  const expand = (next: boolean) => { setExpanded(next); onExpandedChange(next); };
  const close = () => { expand(false); onClose(); };
  const panel = useDialog<HTMLElement>(() => { if (expanded) expand(false); else close(); }, false, returnFocusTo, modal || expanded);
  useEffect(() => () => onExpandedChange(false), [onExpandedChange]);
  const current = sources.findIndex(item => item.id === source?.id);
  const web = source?.source_metadata.kind === 'web';
  const url = source?.source_metadata.url;

  return <aside ref={panel} className={`source-drawer ${expanded ? 'is-expanded' : ''}`} aria-label="来源详情"
    role={modal || expanded ? 'dialog' : undefined} aria-modal={modal || expanded || undefined} tabIndex={modal || expanded ? -1 : undefined}>
    <div className="source-header"><strong>来源预览</strong><div className="source-view-tabs">
      <button aria-pressed={!detail} className={!detail ? 'selected' : ''} onClick={() => setDetail(false)}>相关片段 ({sources.length})</button>
      <button aria-pressed={detail} className={detail ? 'selected' : ''} onClick={() => setDetail(true)}>该文档详情</button>
    </div>
      {modal && <button className="icon-button" data-initial-focus aria-label="关闭来源" onClick={close}><X size={19} /></button>}
      {!modal && onCollapse && <button className="icon-button" aria-label="收起右侧来源栏" title="收起来源栏" onClick={() => { expand(false); onCollapse(); }}><PanelRightClose size={18} /></button>}
    </div>
    {!source ? <div className="source-empty"><Search size={31} /><h3>核对每一处来源</h3><p>点击文档、搜索结果或回答中的引用，在这里查看原文片段。</p></div> : <>
      <div className="source-file"><span className="source-file-icon"><FileText size={25} /></span><div className="source-file-name"><h3 title={source.filename}>{source.filename}</h3>
        <p><span>{web ? '联网搜索 · 网页摘要' : `行 ${source.source_metadata.line_start}–${source.source_metadata.line_end}`}</span>{source.citation_number ? ` · 引用 [${source.citation_number}]` : ''}</p></div>
        {web && url ? <button className="source-open-button web-open-button" onClick={() => onOpenWeb(url)}><ExternalLink size={14} />打开网页</button>
          : <button className="source-open-button" onClick={() => expand(!expanded)}>{expanded ? '返回工作区' : '放大预览'}</button>}
        {!modal && <button className="icon-button source-more" aria-label="关闭来源" title="关闭来源" onClick={close}><MoreHorizontal size={20} /></button>}
      </div>
      <div className="source-reading-area">
        {detail ? <dl className="source-metadata"><dt>{web ? '网页标题' : '文件名'}</dt><dd>{source.filename}</dd>
          {web ? <><dt>网页链接</dt><dd>{url}</dd><dt>检索时间</dt><dd>{source.source_metadata.retrieved_at ? new Date(source.source_metadata.retrieved_at).toLocaleString('zh-CN') : '未记录'}</dd><dt>存储方式</dt><dd>联网搜索 · 摘要快照</dd></>
            : <><dt>标题路径</dt><dd>{source.source_metadata.heading_path.join(' / ') || '文档片段'}</dd><dt>原文位置</dt><dd>行 {source.source_metadata.line_start}–{source.source_metadata.line_end}</dd><dt>存储方式</dt><dd>本地知识库 · 原始文档片段</dd></>}</dl>
          : <article className="source-page" lang={/[\u4e00-\u9fff]/.test(source.content) ? 'zh-CN' : 'en'} style={{ fontSize: `${16.5 * zoom / 100}px` }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={{ img: () => null, a: ({ children }) => <span>{children}</span> }}>{source.content}</ReactMarkdown>
          </article>}
      </div>
      <div className="source-pagination"><button className="icon-button" aria-label="上一个片段" disabled={current <= 0} onClick={() => onSelect(sources[current - 1])}><ChevronLeft size={20} /></button>
        <span>{Math.max(1, current + 1)} / {Math.max(1, sources.length)}</span>
        <button className="icon-button" aria-label="下一个片段" disabled={current < 0 || current >= sources.length - 1} onClick={() => onSelect(sources[current + 1])}><ChevronRight size={20} /></button>
        <label className="source-zoom"><span className="sr-only">预览缩放</span><select aria-label="预览缩放" value={zoom} onChange={event => setZoom(Number(event.target.value))}>{[80, 100, 120, 150].map(value => <option key={value} value={value}>{value}%</option>)}</select></label>
        <button className="icon-button" aria-label={expanded ? '还原来源预览' : '展开来源预览'} onClick={() => expand(!expanded)}>{expanded ? <Minimize size={19} /> : <Maximize size={19} />}</button>
      </div>
      {!detail && <div className="related-sources"><h3>相关片段</h3>{(sources.length ? sources : [source]).map((item, index) => <button key={item.id} className={item.id === source.id ? 'selected' : ''} onClick={() => onSelect(item)}>
        <span className="source-line-badge">{item.source_metadata.kind === 'web' ? '网页' : `行 ${item.source_metadata.line_start}`}</span><span className="related-source-copy"><strong>{item.source_metadata.heading_path.at(-1) || item.filename}</strong><small>{item.content.replace(/^#+\s*/gm, '').slice(0, 85)}</small></span>
        {item.score !== undefined ? <span className="source-score">{Math.round(Math.max(0, Math.min(1, item.score)) * 100)}%</span> : <span className="related-index">{index + 1}</span>}
      </button>)}</div>}
    </>}
  </aside>;
}
