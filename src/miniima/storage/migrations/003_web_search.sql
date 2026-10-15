ALTER TABLE messages ADD COLUMN web_search INTEGER NOT NULL DEFAULT 0 CHECK (web_search IN (0, 1));
