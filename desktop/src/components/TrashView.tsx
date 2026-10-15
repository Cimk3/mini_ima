import { ArchiveRestore, Loader2, Trash2 } from 'lucide-react';
import type { TrashItem } from '../types';

export default function TrashView({ items, loading, busy, onRestore, onPurge, onEmpty }: {
  items: TrashItem[]; loading: boolean; busy: boolean; onRestore: (item: TrashItem) => void;
  onPurge: (item: TrashItem) => void; onEmpty: () => void;
}) {
  return <section className="trash-view" id="panel-trash" role="tabpanel" aria-labelledby="tab-trash">
    <div className="section-heading"><div><h2>回收站</h2><p>知识库和对话会保留在这里，直到你恢复或彻底删除。</p></div>
      <button className="secondary-button danger-action" disabled={busy || !items.length} onClick={onEmpty}><Trash2 size={17} />清空回收站</button></div>
    {loading ? <div className="conversation-loading" role="status"><Loader2 className="spin" size={20} />正在读取回收站…</div>
      : items.length ? <div className="trash-list">{items.map(item => <div className="trash-item" key={`${item.kind}:${item.id}`}>
        <span className="trash-item-icon"><Trash2 size={21} /></span><div className="trash-item-copy"><h3>{item.title}</h3>
          <p>{item.kind === 'kb' ? '知识库' : '对话'} · {item.knowledge_base_name} · {new Date(item.deleted_at).toLocaleString('zh-CN')}</p></div>
        <div className="trash-item-actions"><button className="secondary-button" disabled={busy} onClick={() => onRestore(item)}><ArchiveRestore size={16} />恢复</button>
          <button className="text-button danger-action" disabled={busy} onClick={() => onPurge(item)}>彻底删除</button></div>
      </div>)}</div> : <div className="empty-documents"><Trash2 size={30} /><h3>回收站是空的</h3><p>删除的知识库和对话会出现在这里。</p></div>}
  </section>;
}
