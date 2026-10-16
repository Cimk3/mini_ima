import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { useUpdates } from '../hooks/useUpdates';

const bridge = vi.hoisted(() => ({ request: vi.fn(), getUpdateInfo: vi.fn(), prepareUpdate: vi.fn(), installUpdate: vi.fn(), confirmAction: vi.fn() }));
vi.mock('../bridge', () => ({ ...bridge, errorMessage: (error: unknown) => String(error) }));
beforeEach(() => {
  vi.resetAllMocks();
  bridge.getUpdateInfo.mockResolvedValue({ current_version: '0.2.0', can_install: true });
  bridge.request.mockImplementation(async method => method === 'updates.check'
    ? { current_version: '0.2.0', latest_version: '0.3.0', available: true, downloadable: true, can_install: true }
    : { phase: 'ready', total: 100, received: 100 });
  bridge.prepareUpdate.mockResolvedValue({ version: '0.3.0' });
  bridge.installUpdate.mockResolvedValue(undefined);
});

test('update is optional and cancel does not download or install', async () => {
  bridge.confirmAction.mockResolvedValue(false);
  const hook = renderHook(() => useUpdates(false, false, vi.fn()));
  await act(async () => { await hook.result.current.check(); });
  expect(hook.result.current.release?.latest_version).toBe('0.3.0');
  await act(async () => { await hook.result.current.update(); });
  expect(bridge.prepareUpdate).not.toHaveBeenCalled();
  expect(bridge.installUpdate).not.toHaveBeenCalled();
});

test('accepted update downloads inside the app before handing off installation', async () => {
  bridge.confirmAction.mockResolvedValue(true); const busy = vi.fn();
  const hook = renderHook(() => useUpdates(false, false, busy));
  await act(async () => { await hook.result.current.check(); });
  await act(async () => { await hook.result.current.update(); });
  expect(bridge.prepareUpdate).toHaveBeenCalledOnce();
  expect(bridge.prepareUpdate).toHaveBeenCalledWith('0.3.0');
  expect(bridge.installUpdate).toHaveBeenCalledOnce();
  expect(bridge.prepareUpdate.mock.invocationCallOrder[0]).toBeLessThan(bridge.installUpdate.mock.invocationCallOrder[0]);
  expect(busy).toHaveBeenCalledWith(true);
});

test('failed verification keeps the app open and allows retry', async () => {
  bridge.confirmAction.mockResolvedValue(true); bridge.prepareUpdate.mockRejectedValue(new Error('校验失败'));
  const busy = vi.fn(); const hook = renderHook(() => useUpdates(false, false, busy));
  await act(async () => { await hook.result.current.check(); });
  await act(async () => { await hook.result.current.update(); });
  await waitFor(() => expect(hook.result.current.phase).toBe('error'));
  expect(bridge.installUpdate).not.toHaveBeenCalled();
  expect(busy).toHaveBeenLastCalledWith(false);
});
