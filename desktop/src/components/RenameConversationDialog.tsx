import { useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { useDialog } from './useDialog';

export default function RenameConversationDialog({ title, busy, error, onClose, onSubmit, returnFocusTo }: {
  title: string; busy: boolean; error: string | null; onClose: () => void;
  onSubmit: (title: string) => void; returnFocusTo: HTMLElement | null;
}) {
  const [name, setName] = useState(title);
  const dialog = useDialog<HTMLElement>(onClose, busy, returnFocusTo);
  return <div className="modal-backdrop"><section ref={dialog} className="create-dialog" role="dialog" aria-modal="true" aria-labelledby="rename-title" tabIndex={-1}>
    <header className="dialog-header"><h2 id="rename-title">重命名对话</h2><button className="icon-button" aria-label="关闭重命名" disabled={busy} onClick={onClose}><X size={20} /></button></header>
    <form onSubmit={event => { event.preventDefault(); if (name.trim()) onSubmit(name.trim()); }}>
      <div className="rename-body"><label>对话标题<input data-initial-focus aria-label="对话标题" value={name} maxLength={100} disabled={busy}
        onChange={event => setName(event.target.value)} onFocus={event => event.target.select()} /></label>
        {error && <p className="notice error" role="alert">{error}</p>}</div>
      <footer className="dialog-footer"><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>取消</button>
        <button className="primary-button" disabled={busy || !name.trim()}>{busy && <Loader2 size={16} className="spin" />}保存标题</button></footer>
    </form>
  </section></div>;
}
