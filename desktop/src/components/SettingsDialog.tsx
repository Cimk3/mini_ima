import { useState } from 'react';
import { Eye, EyeOff, X, Check, Loader2, SlidersHorizontal, Wifi } from 'lucide-react';
import { request, errorMessage } from '../bridge';
import type { SettingsSnapshot, ConnectionResult } from '../types';
import { useDialog } from './useDialog';
import UpdateSection from './UpdateSection';
import type { UpdateController } from '../hooks/useUpdates';

export function formValues(snapshot: SettingsSnapshot) {
  const s = snapshot.saved;
  return { base_url: s.base_url, chat_model: s.chat_model, api_key: '',
    embedding_base_url: s.embedding_base_url || 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    embedding_model: s.embedding_model || 'qwen3.7-text-embedding', embedding_dimension: s.embedding_dimension || 1024,
    embedding_api_key: '', embedding_batch_size: s.embedding_model ? s.embedding_batch_size : 20,
    timeout: s.timeout, max_retries: s.max_retries, chunk_tokens: s.chunk_tokens, chunk_overlap: s.chunk_overlap,
    retrieval_engine: s.retrieval_engine, min_score: s.min_score, context_tokens: s.context_tokens };
}

export default function SettingsDialog({ snapshot, onClose, onSaved, onBusy, returnFocusTo, updates, streamingEnabled = true, onStreamingChange }: {
  snapshot: SettingsSnapshot; onClose: () => void; onSaved: (snapshot: SettingsSnapshot) => void; onBusy: (busy: boolean) => void;
  returnFocusTo?: HTMLElement | null;
  updates?: UpdateController;
  streamingEnabled?: boolean; onStreamingChange?: (enabled: boolean) => void;
}) {
  const [form, setForm] = useState(() => formValues(snapshot));
  const [showChatKey, setShowChatKey] = useState(true);
  const [showEmbeddingKey, setShowEmbeddingKey] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; good: boolean } | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const locked = !!busy || !!updates?.busy;
  const unsaved = JSON.stringify(form) !== JSON.stringify(formValues(snapshot));
  const dialog = useDialog<HTMLElement>(onClose, locked, returnFocusTo);
  const change = (name: keyof typeof form, value: string | number) => { setForm(old => ({ ...old, [name]: value })); setMessage(null); };

  async function save(test?: 'chat' | 'embedding') {
    setBusy(test || 'save'); onBusy(true); setMessage(null);
    try {
      const saved = await request<SettingsSnapshot>('settings.update', { values: form });
      onSaved(saved); setForm(formValues(saved));
      if (test) {
        const result = await request<ConnectionResult>('connections.test', { kind: test });
        setMessage({ text: test === 'chat' ? '问答连接成功，模型返回了有效文本。' : `向量连接成功，输出维度 ${result.dimension}。`, good: true });
      } else setMessage({ text: '设置已保存，CLI 与桌面版共用这份配置。', good: true });
    } catch (error) { setMessage({ text: errorMessage(error), good: false }); }
    finally { setBusy(null); onBusy(false); }
  }

  async function preset() {
    try {
      const p = await request<SettingsSnapshot['saved']>('settings.qwen');
      setForm(old => ({ ...old, embedding_model: p.embedding_model, embedding_base_url: p.embedding_base_url,
        embedding_dimension: p.embedding_dimension, embedding_batch_size: p.embedding_batch_size }));
      setMessage(null);
    } catch (error) { setMessage({ text: errorMessage(error), good: false }); }
  }

  async function diagnose() {
    setBusy('doctor'); onBusy(true); setMessage(null);
    try {
      const result = await request<{ integrity: string; foreign_key_errors: number }>('doctor');
      if (result.integrity !== 'ok' || result.foreign_key_errors) throw new Error('数据库完整性检查未通过。');
      setMessage({ text: '本地检查通过：数据库完整，检索组件可用。', good: true });
    } catch (error) { setMessage({ text: errorMessage(error), good: false }); }
    finally { setBusy(null); onBusy(false); }
  }

  return <div className="modal-backdrop"><section ref={dialog} className="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title" tabIndex={-1}>
    <header className="dialog-header"><div><h2 id="settings-title">模型与连接</h2><p>配置你的 AI，让本地知识库开始工作。</p></div>
      <button className="icon-button" aria-label="关闭设置" disabled={locked} onClick={onClose}><X size={20} /></button></header>
    <div className="settings-body"><fieldset className="settings-fields" disabled={locked}>
      {snapshot.overrides.length > 0 && <div className="notice">部分设置由环境变量控制：{snapshot.overrides.join('、')}。保存文件后，环境变量仍优先。</div>}
      <section className="provider-card"><div className="provider-heading"><div className="provider-avatar deepseek">D</div><div><h3>DeepSeek</h3><p>知识库问答</p></div><span className={`status-badge ${snapshot.saved.api_key_configured ? 'ready' : 'pending'}`}>{snapshot.saved.api_key_configured ? '已配置' : '待配置'}</span></div>
        {onStreamingChange && <label className="streaming-preference"><input type="checkbox" checked={streamingEnabled} onChange={event => onStreamingChange(event.target.checked)} />流式显示回答<small>逐步显示正文；兼容性不佳时可关闭。修改后自动保存。</small></label>}
        <div className="field-grid"><label>服务地址<input data-initial-focus value={form.base_url} onChange={e => change('base_url', e.target.value)} /></label><label>问答模型<input value={form.chat_model} onChange={e => change('chat_model', e.target.value)} /></label></div>
        <label className="key-label">API Key<div className="key-input"><input aria-label="DeepSeek API Key" autoComplete="off" spellCheck={false} type={showChatKey ? 'text' : 'password'} value={form.api_key} placeholder={snapshot.saved.api_key_configured ? '已配置，留空保留现有 Key' : '输入 DeepSeek API Key'} onChange={e => change('api_key', e.target.value)} /><button type="button" className="icon-button" aria-label={showChatKey ? '隐藏 API Key' : '显示 API Key'} aria-pressed={!showChatKey} onClick={() => setShowChatKey(!showChatKey)}>{showChatKey ? <Eye size={18} /> : <EyeOff size={18} />}</button></div></label>
        <button className="secondary-button connection-button" disabled={!!busy} onClick={() => save('chat')}>{busy === 'chat' ? <Loader2 className="spin" size={17} /> : <Wifi size={17} />}保存并测试问答连接</button>
      </section>
      <section className="provider-card"><div className="provider-heading"><div className="provider-avatar qwen">Q</div><div><h3>Qwen Embedding</h3><p>文档向量与语义检索</p></div><span className={`status-badge ${snapshot.saved.embedding_api_key_configured ? 'ready' : 'pending'}`}>{snapshot.saved.embedding_api_key_configured ? '已配置' : '待配置'}</span></div>
        <div className="field-grid"><label>服务地址<input value={form.embedding_base_url} onChange={e => change('embedding_base_url', e.target.value)} /></label><label>向量模型<input value={form.embedding_model} onChange={e => change('embedding_model', e.target.value)} /></label></div>
        <div className="field-grid embedding-fields"><label>向量维度<input type="number" min={1} value={form.embedding_dimension} onChange={e => change('embedding_dimension', Number(e.target.value))} /></label><button className="preset-button" disabled={!!busy} onClick={preset}>使用 Qwen3.7 默认配置</button></div>
        <label className="key-label">API Key<div className="key-input"><input aria-label="Qwen API Key" autoComplete="off" spellCheck={false} type={showEmbeddingKey ? 'text' : 'password'} value={form.embedding_api_key} placeholder={snapshot.saved.embedding_api_key_configured ? '已配置，留空保留现有 Key' : '输入向量服务 API Key'} onChange={e => change('embedding_api_key', e.target.value)} /><button type="button" className="icon-button" aria-label={showEmbeddingKey ? '隐藏向量 API Key' : '显示向量 API Key'} aria-pressed={!showEmbeddingKey} onClick={() => setShowEmbeddingKey(!showEmbeddingKey)}>{showEmbeddingKey ? <Eye size={18} /> : <EyeOff size={18} />}</button></div></label>
        <button className="secondary-button connection-button" disabled={!!busy} onClick={() => save('embedding')}>{busy === 'embedding' ? <Loader2 className="spin" size={17} /> : <Wifi size={17} />}保存并测试向量连接</button>
      </section>
      <button className="advanced-toggle" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}><SlidersHorizontal size={17} />{advanced ? '收起高级设置' : '高级设置'}</button>
      {advanced && <div className="advanced-fields field-grid"><label>分块大小<input type="number" value={form.chunk_tokens} onChange={e => change('chunk_tokens', Number(e.target.value))} /></label><label>分块重叠<input type="number" value={form.chunk_overlap} onChange={e => change('chunk_overlap', Number(e.target.value))} /></label><label>相似度阈值<input type="number" step="0.05" value={form.min_score} onChange={e => change('min_score', Number(e.target.value))} /></label><label>超时（秒）<input type="number" value={form.timeout} onChange={e => change('timeout', Number(e.target.value))} /></label><label>有限重试次数<input type="number" min={0} max={5} value={form.max_retries} onChange={e => change('max_retries', Number(e.target.value))} /></label><label>检索引擎<select value={form.retrieval_engine} onChange={e => change('retrieval_engine', e.target.value)}><option value="cpp">C++ ExactIndex</option><option value="numpy">NumPy</option></select></label></div>}
    </fieldset>{updates && <>{unsaved && <p className="notice">请先保存模型设置，再检查或安装更新。</p>}<UpdateSection updates={updates} disabled={!!busy || unsaved} /></>}</div>
    {message && <div role="status" className={`settings-status notice ${message.good ? 'success' : 'error'}`}>{message.good && <Check size={16} />}{message.text}</div>}
    <footer className="dialog-footer"><span>新输入的 Key 默认可见，留空保留原值。</span><div className="dialog-actions"><button className="secondary-button" disabled={locked} onClick={diagnose}>{busy === 'doctor' && <Loader2 className="spin" size={17} />}本地检查</button><button className="primary-button" disabled={locked} onClick={() => save()}>{busy === 'save' && <Loader2 className="spin" size={17} />}保存设置</button></div></footer>
  </section></div>;
}
