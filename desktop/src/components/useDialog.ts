import { useEffect, useRef } from 'react';

const focusable = 'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])';

/** Keep keyboard navigation inside an open dialog and return to its trigger on close. */
export function useDialog<T extends HTMLElement>(onClose: () => void, locked: boolean, returnFocusTo?: HTMLElement | null, active = true) {
  const ref = useRef<T>(null);
  const current = useRef({ onClose, locked, returnFocusTo });
  current.current = { onClose, locked, returnFocusTo };

  useEffect(() => {
    if (!active) return;
    const dialog = ref.current;
    if (!dialog) return;
    const previous = document.activeElement;
    const controls = () => Array.from(dialog.querySelectorAll<HTMLElement>(focusable))
      .filter(element => !element.closest('[hidden]') && (!element.closest('details:not([open])') || !!element.closest('summary')));
    const initial = dialog.querySelector<HTMLElement>('[data-initial-focus]') || controls()[0] || dialog;
    initial.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (!current.current.locked) current.current.onClose();
      } else if (event.key === 'Tab') {
        const items = controls();
        if (!items.length) { event.preventDefault(); dialog.focus(); return; }
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
          event.preventDefault(); first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      queueMicrotask(() => {
        // A drawer may hand focus directly to settings in the same render.
        if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
        // Chrome blurs the trigger as soon as its parent becomes inert.
        // Capture it in the opening action instead of relying on activeElement after mount.
        const target = current.current.returnFocusTo || previous;
        if (target instanceof HTMLElement && target.isConnected) target.focus();
      });
    };
  }, [active]);

  return ref;
}
