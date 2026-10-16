import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import ChatWorkspace from '../components/ChatWorkspace';
import type { ConversationDetail } from '../types';

test('reading earlier messages is preserved until return-to-latest is selected', () => {
  const answerRef = createRef<HTMLDivElement>();
  const conversation: ConversationDetail = { id: 'one', title: 'Question', knowledge_base_id: 'kb', knowledge_base_name: '资料',
    created_at: '', updated_at: '', message_count: 1, messages: [{ id: 'answer', conversation_id: 'one', role: 'assistant',
      content: '旧回答', position: 0, status: 'completed', request_id: null, reply_to: null, error: null, citations: [] }] };
  const props = { conversation, pendingQuestion: null, loading: false, baseName: '资料', query: '', onQuery: vi.fn(), busy: false,
    questionRef: createRef<HTMLTextAreaElement>(), answerRef, onSend: vi.fn(), onImport: vi.fn(), onRetry: vi.fn(), onSource: vi.fn(),
    onCopy: vi.fn(), webSearch: false, onWebSearch: vi.fn() };
  const view = render(<ChatWorkspace {...props} />);
  const element = answerRef.current!;
  const scroll = vi.fn(); element.scrollTo = scroll;
  Object.defineProperties(element, { scrollHeight: { value: 1000 }, clientHeight: { value: 200 } });
  element.scrollTop = 100; fireEvent.scroll(element);
  view.rerender(<ChatWorkspace {...props} conversation={{ ...conversation, updated_at: 'new' }} />);
  expect(scroll).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '回到最新' }));
  expect(scroll).toHaveBeenCalledWith({ top: 1000 });
});
