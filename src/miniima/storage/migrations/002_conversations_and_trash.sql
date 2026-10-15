ALTER TABLE knowledge_bases ADD COLUMN deleted_at TEXT;
ALTER TABLE conversations ADD COLUMN title TEXT NOT NULL DEFAULT '新对话';
ALTER TABLE conversations ADD COLUMN deleted_at TEXT;
ALTER TABLE messages ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'
    CHECK (status IN ('pending', 'completed', 'failed', 'interrupted'));
ALTER TABLE messages ADD COLUMN request_id TEXT;
ALTER TABLE messages ADD COLUMN reply_to TEXT;
ALTER TABLE messages ADD COLUMN error TEXT;
ALTER TABLE messages ADD COLUMN worker_pid INTEGER;

UPDATE conversations SET title = COALESCE((SELECT substr(content, 1, 30) FROM messages
    WHERE conversation_id = conversations.id AND role = 'user' ORDER BY created_at, rowid LIMIT 1), '新对话');
UPDATE messages SET position = (SELECT COUNT(*) - 1 FROM messages AS previous
    WHERE previous.conversation_id = messages.conversation_id
      AND (previous.created_at < messages.created_at
           OR (previous.created_at = messages.created_at AND previous.rowid <= messages.rowid)));
UPDATE messages SET reply_to = (SELECT preceding.id FROM messages AS preceding
    WHERE preceding.conversation_id = messages.conversation_id AND preceding.role = 'user'
      AND preceding.position < messages.position ORDER BY preceding.position DESC LIMIT 1)
    WHERE role = 'assistant';

CREATE UNIQUE INDEX messages_position ON messages(conversation_id, position);
CREATE UNIQUE INDEX messages_request ON messages(request_id) WHERE request_id IS NOT NULL;
CREATE UNIQUE INDEX messages_reply ON messages(reply_to) WHERE reply_to IS NOT NULL;
CREATE UNIQUE INDEX conversations_pending ON messages(conversation_id) WHERE status = 'pending';
CREATE INDEX conversations_recent ON conversations(deleted_at, updated_at DESC, id DESC);
