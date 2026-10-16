import { invoke } from '@tauri-apps/api/core';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { open, confirm } from '@tauri-apps/plugin-dialog';
import { previewRequest } from './preview';
import { APP_VERSION } from './version';
import type { UpdateInfo } from './types';

const preview = import.meta.env.DEV && new URLSearchParams(window.location.search).has('preview');

export async function getUpdateInfo(): Promise<UpdateInfo> {
  if (preview) return { current_version: APP_VERSION, can_install: false };
  return invoke<UpdateInfo>('update_info');
}

export async function prepareUpdate(version: string): Promise<{ version: string }> {
  if (preview) throw new Error('开发预览不安装更新。');
  return invoke('prepare_update', { version });
}

export async function installUpdate(): Promise<void> {
  if (preview) throw new Error('开发预览不安装更新。');
  return invoke('install_update');
}

export async function request<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  if (preview) return previewRequest(method, params) as Promise<T>;
  return invoke<T>('backend_request', { method, params });
}

export async function chooseFiles(): Promise<string[]> {
  const selection = await open({ multiple: true, directory: false, title: '导入到知识库',
    filters: [{ name: '文本与 Markdown', extensions: ['txt', 'md', 'markdown'] }] });
  return selection ? (Array.isArray(selection) ? selection : [selection]) : [];
}

export function confirmAction(message: string): Promise<boolean> {
  if (preview) return Promise.resolve(window.confirm(message));
  return confirm(message, { title: 'Mini-ima', kind: 'warning', okLabel: '确认', cancelLabel: '取消' });
}

/** Custom titlebar controls still use Tauri's native close-request lifecycle. */
export async function windowAction(action: 'minimize' | 'maximize' | 'close' | 'drag'): Promise<void> {
  if (preview || !(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) return;
  const appWindow = getCurrentWindow();
  if (action === 'minimize') await appWindow.minimize();
  else if (action === 'maximize') await appWindow.toggleMaximize();
  else if (action === 'close') await appWindow.close();
  else await appWindow.startDragging();
}

export async function handleWindowClose(isBusy: () => boolean): Promise<() => void> {
  if (preview || !(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) return () => {};
  const appWindow = getCurrentWindow();
  return appWindow.onCloseRequested(async event => {
    if (!isBusy()) return;
    event.preventDefault();
    if (await confirmAction('仍有任务正在处理。退出将中断当前任务，是否退出？')) await appWindow.destroy();
  });
}

export function errorMessage(error: unknown): string {
  return typeof error === 'string' ? error : error instanceof Error ? error.message : '操作失败，请重试。';
}
