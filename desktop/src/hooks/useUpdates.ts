import { useEffect, useRef, useState } from 'react';
import { confirmAction, errorMessage, getUpdateInfo, installUpdate, prepareUpdate, request } from '../bridge';
import { APP_VERSION } from '../version';
import type { ReleaseUpdate, UpdateInfo, UpdateProgress } from '../types';

export function useUpdates(startup: boolean, locked: boolean, onBusy: (busy: boolean) => void) {
  const [info, setInfo] = useState<UpdateInfo>({ current_version: APP_VERSION, can_install: false });
  const [release, setRelease] = useState<ReleaseUpdate | null>(null);
  const [phase, setPhase] = useState<'idle' | 'checking' | 'downloading' | 'installing' | 'error'>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const [progress, setProgress] = useState<UpdateProgress>({ phase: 'idle', received: 0, total: 0 });
  const [dismissed, setDismissed] = useState(false);
  const [previous, setPrevious] = useState<string | null>(null);
  const inFlight = useRef(false);
  const automatic = useRef(false);
  const lockedRef = useRef(locked);
  lockedRef.current = locked;

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const result = await getUpdateInfo();
        if (alive && result?.current_version) { setInfo(result); setPrevious(result.previous_result?.message || null); }
      } catch { /* Offline/development startup still works without an update check. */ }
    })();
    return () => { alive = false; };
  }, []);

  async function check(silent = false) {
    if (inFlight.current || lockedRef.current) return;
    inFlight.current = true; setPhase('checking');
    if (!silent) setMessage(null);
    try {
      const result = await request<ReleaseUpdate>('updates.check');
      if (!result?.current_version) throw new Error('未收到有效的版本信息，请重试。');
      setRelease(result); setInfo(result); setDismissed(false);
      setMessage(result.available ? result.reason || `发现新版本 ${result.latest_version}。` : '当前已是最新版本。');
      setPhase('idle');
    } catch (error) { setPhase(silent ? 'idle' : 'error'); setMessage(errorMessage(error)); }
    finally { inFlight.current = false; }
  }

  useEffect(() => {
    if (startup || locked || automatic.current) return;
    const timer = window.setTimeout(() => { automatic.current = true; void check(true); }, 1500);
    return () => window.clearTimeout(timer);
  }, [startup, locked]);

  useEffect(() => {
    if (phase !== 'downloading') return;
    let alive = true, pending = false;
    const timer = window.setInterval(async () => {
      if (pending) return;
      pending = true;
      try { const status = await request<UpdateProgress>('updates.status'); if (alive && status) setProgress(status); }
      catch { /* The final download response provides an actionable error. */ }
      finally { pending = false; }
    }, 800);
    return () => { alive = false; window.clearInterval(timer); };
  }, [phase]);

  async function update() {
    if (lockedRef.current || inFlight.current || !release?.available || !release.downloadable || !info.can_install) return;
    if (!await confirmAction(`下载并更新到 ${release.latest_version}？下载完成后应用会退出并自动重启，请先保存当前设置。`)) return;
    if (lockedRef.current || inFlight.current) return;
    inFlight.current = true; onBusy(true); setMessage(null); setPhase('downloading');
    try {
      await prepareUpdate(release.latest_version);
      setPhase('installing');
      // A final status read can still be in flight; allow it to finish before the native handoff.
      await request<UpdateProgress>('updates.status');
      await installUpdate();
    } catch (error) { setPhase('error'); setMessage(errorMessage(error)); onBusy(false); inFlight.current = false; }
  }

  const busy = phase === 'downloading' || phase === 'installing';
  return { info, release, phase, progress, message, busy, previous, dismissed,
    check: () => check(), update, dismiss: () => setDismissed(true), dismissPrevious: () => setPrevious(null) };
}

export type UpdateController = ReturnType<typeof useUpdates>;
