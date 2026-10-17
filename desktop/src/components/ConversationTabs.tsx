import { Loader2, MessageSquare, Plus, RotateCcw, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { ConversationWindow } from '../types';

export default function ConversationTabs({ windows, activeKey, pendingKey, disabled, onSwitch, onClose, onNew, closedDrafts, onRestoreDraft }: {
  windows: ConversationWindow[]; activeKey: string; pendingKey?: string; disabled: boolean;
  onSwitch: (window: ConversationWindow) => void; onClose: (key: string) => void; onNew: () => void;
  closedDrafts: number; onRestoreDraft: () => void;
}) {
  const navigation = useRef<HTMLElement>(null);
  useEffect(() => { navigation.current?.querySelector('[aria-pressed="true"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' }); }, [activeKey]);
  return <div className="conversation-tabs">
    <nav ref={navigation} className="conversation-window-list" aria-label="对话窗口">
      {windows.map(window => <div className={`conversation-tab ${window.key === activeKey ? 'active' : ''}`} key={window.key}>
        <button className="conversation-tab-select" aria-label={`切换对话：${window.title}`} aria-pressed={window.key === activeKey}
          title={window.title} disabled={disabled} onClick={() => onSwitch(window)}>
          {pendingKey === window.key ? <Loader2 size={16} className="spin" /> : <MessageSquare size={16} />}<strong>{window.title}</strong>
        </button>
        <button className="icon-button" aria-label={`关闭对话窗口：${window.title}`} title="关闭窗口，未发送草稿和已保存记录均保留"
          disabled={disabled} onClick={() => onClose(window.key)}><X size={14} /></button>
      </div>)}
    </nav>
    <button className="icon-button new-question" aria-label="新建对话" title="新建对话" disabled={disabled} onClick={onNew}><Plus size={20} /></button>
    {closedDrafts > 0 && <button className="text-button restore-draft" aria-label="恢复上次关闭的草稿" title="恢复上次关闭的草稿，已关闭的草稿在重启后仍可恢复"
      disabled={disabled} onClick={onRestoreDraft}><RotateCcw size={15} />恢复草稿 ({closedDrafts})</button>}
  </div>;
}
