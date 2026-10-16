import { Download, Loader2, RefreshCw, X } from 'lucide-react';
import type { UpdateController } from '../hooks/useUpdates';

export default function UpdateSection({ updates, disabled }: { updates: UpdateController; disabled: boolean }) {
  const { info, release, phase, progress, message, busy } = updates;
  const percent = progress.total ? Math.min(100, Math.round(progress.received * 100 / progress.total)) : null;
  return <section className="update-section" aria-labelledby="update-title"><div className="update-heading"><div><h3 id="update-title">版本与更新</h3><p>当前版本 {info.current_version}</p></div>
    <button className="secondary-button" disabled={disabled || busy || phase === 'checking'} onClick={() => void updates.check()}>
      {phase === 'checking' ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}检查新版本</button></div>
    {message && <p role="status" className={phase === 'error' ? 'update-error' : ''}>{message}</p>}
    {release?.available && <><p>新版本 {release.latest_version}{release.size ? ` · ${(release.size / 1024 / 1024).toFixed(1)} MB` : ''}</p>
      {release.notes && <div className="update-notes">{release.notes}</div>}
      {!info.can_install && <p>开发预览仅检查版本，请在发布版中安装更新。</p>}
      {release.reason && <p>{release.reason}</p>}
      <button className="primary-button" disabled={disabled || busy || phase === 'checking' || !info.can_install || !release.downloadable} onClick={() => void updates.update()}>
        <Download size={16} />下载并重启更新</button></>}
    {busy && <div role="status" className="update-progress"><Loader2 size={16} className="spin" />
      {phase === 'installing' ? '正在退出并安装更新…' : progress.phase === 'verifying' ? '正在校验更新包…' : `正在下载更新包${percent === null ? '…' : ` ${percent}%`}`}
      {phase === 'downloading' && percent !== null && <progress aria-label="更新下载进度" value={percent} max={100} />}</div>}
    <small>启动后自动检测正式版；由你选择是否更新。配置和知识库保留在本机。</small>
  </section>;
}

export function UpdateBanner({ updates, disabled, onDetails }: { updates: UpdateController; disabled: boolean; onDetails: () => void }) {
  if (updates.previous) return <aside className="update-banner" role="status"><span>{updates.previous}</span><button className="icon-button" aria-label="关闭更新结果" onClick={updates.dismissPrevious}><X size={16} /></button></aside>;
  if (!updates.release?.available || updates.dismissed || updates.busy) return null;
  return <aside className="update-banner" role="status"><span>发现新版本 {updates.release.latest_version}</span>
    <button className="text-button" disabled={disabled} onClick={onDetails}>查看更新</button><button className="text-button" onClick={updates.dismiss}>稍后</button></aside>;
}
