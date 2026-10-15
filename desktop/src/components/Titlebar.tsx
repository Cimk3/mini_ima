import { useState } from 'react';
import { Search, Settings, Minus, Square, X, Sun, Moon, PanelLeftOpen, PanelLeftClose } from 'lucide-react';
import { windowAction } from '../bridge';
import logo from '../assets/reference-logo.png';

export default function Titlebar({ onSettings, onQuery, disabled, compact, theme, onTheme, locked, sidebarHidden, onSidebar, sidebarTriggerRef, sidebarExpanded }: {
  onSettings: (event: React.MouseEvent<HTMLButtonElement>) => void;
  onQuery: (text: string) => void;
  disabled: boolean;
  compact: boolean;
  theme: 'light' | 'dark';
  onTheme: () => void;
  locked: boolean;
  sidebarHidden: boolean;
  onSidebar: () => void;
  sidebarTriggerRef: React.RefObject<HTMLButtonElement | null>;
  sidebarExpanded: boolean;
}) {
  const [text, setText] = useState('');
  return <header className="titlebar" onMouseDown={event => {
    if (event.button === 0 && !(event.target as HTMLElement).closest('button, input, form, select')) void windowAction('drag');
  }} onDoubleClick={event => {
    if (!(event.target as HTMLElement).closest('button, input, form, select')) void windowAction('maximize');
  }}>
    <button ref={sidebarTriggerRef} className="icon-button sidebar-toggle" disabled={locked} aria-label={compact ? '打开知识库导航' : sidebarHidden ? '展开侧边栏' : '隐藏侧边栏'} aria-controls="knowledge-navigation" aria-expanded={sidebarExpanded} onClick={onSidebar}>{sidebarHidden || compact ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}</button>
    <div className="brand" inert={locked}><div className="brand-mark"><img src={logo} alt="" draggable={false} /></div>
      <div><strong>mini-ima</strong><span>你的个人知识工作台</span></div>
    </div>
    <form className="global-search" inert={locked} onSubmit={event => { event.preventDefault(); if (text.trim()) { onQuery(text.trim()); setText(''); } }}>
      <button type="submit" aria-label="提交顶部搜索" disabled={disabled || !text.trim()}><Search size={21} /></button>
      <input aria-label="搜索知识库或直接提问" placeholder="搜索你的知识库，或直接提问..." value={text} disabled={disabled}
        onChange={event => setText(event.target.value)} onKeyDown={event => {
          if (event.key === 'Enter' && event.nativeEvent.isComposing) event.preventDefault();
        }} />
    </form>
    <div className="titlebar-actions">
      {!compact && <button className="icon-button settings-trigger" aria-label="模型与设置" disabled={disabled || locked} onClick={onSettings}><Settings size={22} /></button>}
      <button className="theme-toggle icon-button" aria-label={theme === 'light' ? '切换深色模式' : '切换浅色模式'} title={theme === 'light' ? '切换深色模式' : '切换浅色模式'} disabled={locked} onClick={onTheme}>{theme === 'light' ? <Moon size={21} /> : <Sun size={21} />}</button>
      <div className="window-controls">
        <button aria-label="最小化窗口" onClick={() => void windowAction('minimize')}><Minus size={18} /></button>
        <button aria-label="最大化或还原窗口" onClick={() => void windowAction('maximize')}><Square size={14} /></button>
        <button className="close-window" aria-label="关闭窗口" onClick={() => void windowAction('close')}><X size={19} /></button>
      </div>
    </div>
  </header>;
}
