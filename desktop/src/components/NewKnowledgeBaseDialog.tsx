import { Loader2, Plus, X } from 'lucide-react';
import { useDialog } from './useDialog';

export default function NewKnowledgeBaseDialog({ name, busy, error, onName, onClose, onSubmit, returnFocusTo }: {
  name: string; busy: boolean; error: string | null; onName: (name: string) => void;
  onClose: () => void; onSubmit: (event: React.FormEvent) => void;
  returnFocusTo?: HTMLElement | null;
}) {
  const dialog = useDialog<HTMLFormElement>(onClose, busy, returnFocusTo);
  return <div className="modal-backdrop">
    <form ref={dialog} className="create-dialog" role="dialog" aria-modal="true" aria-labelledby="new-title" tabIndex={-1} onSubmit={onSubmit}>
      <header className="dialog-header">
        <div><h2 id="new-title">给知识一个家</h2></div>
        <button className="icon-button" type="button" disabled={busy} aria-label="关闭新建" onClick={onClose}><X size={20} /></button>
      </header>
      <div className="create-body">
        <label htmlFor="new-kb-name">知识库名称</label>
        <input id="new-kb-name" data-initial-focus aria-label="知识库名称" value={name} disabled={busy}
          onChange={event => onName(event.target.value)} placeholder="例如：计算机网络、阅读笔记…" maxLength={100} />
        <p>使用当前配置的向量模型。导入的文档与 CLI 共用。</p>
        {error && <div className="notice error" role="alert">{error}</div>}
      </div>
      <footer className="dialog-footer">
        <button className="secondary-button" type="button" disabled={busy} onClick={onClose}>取消</button>
        <button className="primary-button" disabled={busy || !name.trim()}>
          {busy ? <Loader2 size={17} className="spin" /> : <Plus size={17} />}创建知识库
        </button>
      </footer>
    </form>
  </div>;
}
