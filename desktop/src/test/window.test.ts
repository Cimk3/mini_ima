import { beforeEach, afterEach, expect, test, vi } from 'vitest';
import { handleWindowClose, windowAction } from '../bridge';

const native = vi.hoisted(() => ({ minimize: vi.fn(), toggleMaximize: vi.fn(), close: vi.fn(), startDragging: vi.fn(), destroy: vi.fn(), onCloseRequested: vi.fn(), confirm: vi.fn() }));
vi.mock('@tauri-apps/api/window', () => ({ getCurrentWindow: () => native }));
vi.mock('@tauri-apps/plugin-dialog', () => ({ open: vi.fn(), confirm: native.confirm }));

beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal('__TAURI_INTERNALS__', {}); });
afterEach(() => vi.unstubAllGlobals());

test('custom close requests native closing rather than bypassing the busy guard', async () => {
  await windowAction('close');
  expect(native.close).toHaveBeenCalledOnce();
  expect(native.destroy).not.toHaveBeenCalled();
});

test('titlebar minimize, maximize and dragging use the current native window', async () => {
  await windowAction('minimize'); await windowAction('maximize'); await windowAction('drag');
  expect(native.minimize).toHaveBeenCalledOnce();
  expect(native.toggleMaximize).toHaveBeenCalledOnce();
  expect(native.startDragging).toHaveBeenCalledOnce();
});

test('closing from the custom titlebar still confirms an active task', async () => {
  await handleWindowClose(() => true);
  const closeHandler = native.onCloseRequested.mock.calls[0][0];
  const event = { preventDefault: vi.fn() };
  native.confirm.mockResolvedValueOnce(false);
  await closeHandler(event);
  expect(event.preventDefault).toHaveBeenCalledOnce();
  expect(native.destroy).not.toHaveBeenCalled();
  native.confirm.mockResolvedValueOnce(true);
  await closeHandler(event);
  expect(native.destroy).toHaveBeenCalledOnce();
});
