CREATE SCHEMA wire_identity;CREATE SCHEMA wire_main;CREATE SCHEMA wire_chat;CREATE SCHEMA wire_security;

CREATE ROLE wire_main_backend NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;CREATE ROLE wire_chat_backend NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;


CREATE TABLE wire_security.rate_buckets (
	key VARCHAR(64) NOT NULL, 
	bucket INTEGER NOT NULL, 
	count INTEGER NOT NULL, 
	expires_at INTEGER NOT NULL, 
	PRIMARY KEY (key, bucket)
)

;

CREATE INDEX ix_rate_buckets_expires_at ON wire_security.rate_buckets (expires_at);

ALTER TABLE wire_security.rate_buckets ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_security.rate_buckets TO wire_main_backend USING (true) WITH CHECK (true);

CREATE POLICY chat_server_access ON wire_security.rate_buckets TO wire_chat_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_identity.users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(24) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	display_name VARCHAR(40) NOT NULL, 
	date_of_birth DATE NOT NULL, 
	bio VARCHAR(300) NOT NULL, 
	pronouns VARCHAR(30) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	email_verified BOOLEAN NOT NULL, 
	disabled BOOLEAN NOT NULL, 
	timed_out_until INTEGER NOT NULL, 
	avatar_version INTEGER NOT NULL, 
	message_requests BOOLEAN NOT NULL, 
	show_activity BOOLEAN NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE UNIQUE INDEX ix_users_email ON wire_identity.users (email);

CREATE UNIQUE INDEX ix_users_username ON wire_identity.users (username);

ALTER TABLE wire_identity.users ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_identity.users TO wire_main_backend USING (true) WITH CHECK (true);

CREATE POLICY chat_server_access ON wire_identity.users TO wire_chat_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_identity.avatars (
	user_id VARCHAR(36) NOT NULL, 
	content BYTEA NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE
)

;

ALTER TABLE wire_identity.avatars ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_identity.avatars TO wire_main_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_main.blocks (
	blocker_id VARCHAR(36) NOT NULL, 
	blocked_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (blocker_id, blocked_id), 
	CONSTRAINT no_self_block CHECK (blocker_id <> blocked_id), 
	FOREIGN KEY(blocker_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE, 
	FOREIGN KEY(blocked_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_blocks_blocked_id ON wire_main.blocks (blocked_id);

ALTER TABLE wire_main.blocks ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_main.blocks TO wire_main_backend USING (true) WITH CHECK (true);

CREATE POLICY chat_server_access ON wire_main.blocks TO wire_chat_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_chat.conversations (
	id VARCHAR(36) NOT NULL, 
	user_a VARCHAR(36) NOT NULL, 
	user_b VARCHAR(36) NOT NULL, 
	starter_id VARCHAR(36) NOT NULL, 
	accepted BOOLEAN NOT NULL, 
	read_a INTEGER NOT NULL, 
	read_b INTEGER NOT NULL, 
	updated_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_a, user_b), 
	CONSTRAINT ordered_pair CHECK (user_a < user_b), 
	FOREIGN KEY(user_a) REFERENCES wire_identity.users (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_b) REFERENCES wire_identity.users (id) ON DELETE CASCADE, 
	FOREIGN KEY(starter_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_conversations_user_b ON wire_chat.conversations (user_b);

CREATE INDEX ix_conversations_user_a ON wire_chat.conversations (user_a);

CREATE INDEX ix_conversations_updated_at ON wire_chat.conversations (updated_at);

ALTER TABLE wire_chat.conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_chat.conversations TO wire_chat_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_identity.email_challenges (
	user_id VARCHAR(36) NOT NULL, 
	code_hash VARCHAR(64) NOT NULL, 
	expires_at INTEGER NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE
)

;

ALTER TABLE wire_identity.email_challenges ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_identity.email_challenges TO wire_main_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_main.follows (
	follower_id VARCHAR(36) NOT NULL, 
	followed_id VARCHAR(36) NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (follower_id, followed_id), 
	CONSTRAINT no_self_follow CHECK (follower_id <> followed_id), 
	FOREIGN KEY(follower_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE, 
	FOREIGN KEY(followed_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_follows_followed_id ON wire_main.follows (followed_id);

ALTER TABLE wire_main.follows ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_main.follows TO wire_main_backend USING (true) WITH CHECK (true);

CREATE POLICY chat_server_access ON wire_main.follows TO wire_chat_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_main.posts (
	id SERIAL NOT NULL, 
	author_id VARCHAR(36) NOT NULL, 
	parent_id INTEGER, 
	kind VARCHAR(10) NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	body TEXT NOT NULL, 
	created_at INTEGER NOT NULL, 
	client_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT post_client_unique UNIQUE (author_id, client_id), 
	CONSTRAINT valid_post_kind CHECK (kind IN ('note','article')), 
	FOREIGN KEY(author_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE, 
	FOREIGN KEY(parent_id) REFERENCES wire_main.posts (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_posts_author_id ON wire_main.posts (author_id);

CREATE INDEX ix_posts_parent_id ON wire_main.posts (parent_id);

CREATE INDEX ix_posts_feed ON wire_main.posts (parent_id, id);

ALTER TABLE wire_main.posts ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_main.posts TO wire_main_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_identity.recovery_codes (
	code_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (code_hash), 
	FOREIGN KEY(user_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_recovery_codes_user_id ON wire_identity.recovery_codes (user_id);

ALTER TABLE wire_identity.recovery_codes ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_identity.recovery_codes TO wire_main_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_identity.sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	expires_at INTEGER NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (token_hash), 
	FOREIGN KEY(user_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_sessions_user_id ON wire_identity.sessions (user_id);

CREATE INDEX ix_sessions_expires_at ON wire_identity.sessions (expires_at);

ALTER TABLE wire_identity.sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_identity.sessions TO wire_main_backend USING (true) WITH CHECK (true);

CREATE POLICY chat_server_access ON wire_identity.sessions TO wire_chat_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_main.bookmarks (
	user_id VARCHAR(36) NOT NULL, 
	post_id INTEGER NOT NULL, 
	PRIMARY KEY (user_id, post_id), 
	FOREIGN KEY(user_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE, 
	FOREIGN KEY(post_id) REFERENCES wire_main.posts (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_bookmarks_post_id ON wire_main.bookmarks (post_id);

ALTER TABLE wire_main.bookmarks ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_main.bookmarks TO wire_main_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_chat.chat_reports (
	conversation_id VARCHAR(36) NOT NULL, 
	reporter_id VARCHAR(36) NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (conversation_id, reporter_id), 
	FOREIGN KEY(conversation_id) REFERENCES wire_chat.conversations (id) ON DELETE CASCADE, 
	FOREIGN KEY(reporter_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_chat_reports_reporter_id ON wire_chat.chat_reports (reporter_id);

ALTER TABLE wire_chat.chat_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_chat.chat_reports TO wire_chat_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_main.likes (
	user_id VARCHAR(36) NOT NULL, 
	post_id INTEGER NOT NULL, 
	PRIMARY KEY (user_id, post_id), 
	FOREIGN KEY(user_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE, 
	FOREIGN KEY(post_id) REFERENCES wire_main.posts (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_likes_post_id ON wire_main.likes (post_id);

ALTER TABLE wire_main.likes ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_main.likes TO wire_main_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_chat.messages (
	id SERIAL NOT NULL, 
	conversation_id VARCHAR(36) NOT NULL, 
	sender_id VARCHAR(36) NOT NULL, 
	client_id VARCHAR(36) NOT NULL, 
	body TEXT NOT NULL, 
	deleted BOOLEAN NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (sender_id, client_id), 
	FOREIGN KEY(conversation_id) REFERENCES wire_chat.conversations (id) ON DELETE CASCADE, 
	FOREIGN KEY(sender_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_messages_page ON wire_chat.messages (conversation_id, id);

CREATE INDEX ix_messages_sender ON wire_chat.messages (sender_id);

ALTER TABLE wire_chat.messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_chat.messages TO wire_chat_backend USING (true) WITH CHECK (true);


CREATE TABLE wire_main.reports (
	reporter_id VARCHAR(36) NOT NULL, 
	post_id INTEGER NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (reporter_id, post_id), 
	FOREIGN KEY(reporter_id) REFERENCES wire_identity.users (id) ON DELETE CASCADE, 
	FOREIGN KEY(post_id) REFERENCES wire_main.posts (id) ON DELETE CASCADE
)

;

ALTER TABLE wire_main.reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY server_access ON wire_main.reports TO wire_main_backend USING (true) WITH CHECK (true);

ALTER TABLE wire_identity.users ADD CONSTRAINT username_format CHECK(username ~ '^[a-z0-9_]{3,24}$'), ADD CONSTRAINT normalized_email CHECK(email=lower(email)), ADD CONSTRAINT dob_past CHECK(date_of_birth<CURRENT_DATE);

ALTER TABLE wire_main.posts ADD CONSTRAINT post_size CHECK(length(body) BETWEEN 1 AND 10000 AND (kind<>'note' OR length(body)<=500));

ALTER TABLE wire_chat.messages ADD CONSTRAINT message_size CHECK((deleted AND body='') OR (NOT deleted AND length(body) BETWEEN 1 AND 2000));

ALTER TABLE wire_identity.avatars ADD CONSTRAINT avatar_size CHECK(octet_length(content)<=160000);

GRANT USAGE ON SCHEMA wire_identity,wire_main,wire_security TO wire_main_backend;

GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA wire_identity,wire_main,wire_security TO wire_main_backend;

GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA wire_identity,wire_main,wire_security TO wire_main_backend;

GRANT USAGE ON SCHEMA wire_identity,wire_main,wire_security,wire_chat TO wire_chat_backend;

GRANT SELECT (id,username,display_name,disabled,timed_out_until,email_verified,message_requests,show_activity,avatar_version) ON wire_identity.users TO wire_chat_backend;

GRANT SELECT ON wire_identity.sessions,wire_main.blocks,wire_main.follows TO wire_chat_backend;

GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA wire_chat,wire_security TO wire_chat_backend;

GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA wire_chat,wire_security TO wire_chat_backend;

REVOKE ALL ON SCHEMA wire_identity,wire_main,wire_chat,wire_security FROM PUBLIC,anon,authenticated;

REVOKE ALL ON ALL TABLES IN SCHEMA wire_identity,wire_main,wire_chat,wire_security FROM PUBLIC,anon,authenticated;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA wire_identity,wire_main,wire_chat,wire_security FROM PUBLIC,anon,authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA wire_identity,wire_main,wire_chat,wire_security REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

CREATE INDEX ix_chat_starter ON wire_chat.conversations(starter_id);





CREATE INDEX ix_reports_post ON wire_main.reports(post_id);



GRANT wire_main_backend, wire_chat_backend TO postgres WITH INHERIT FALSE, SET TRUE;

ALTER ROLE wire_main_backend SET search_path=wire_identity,wire_main,wire_security;
ALTER ROLE wire_chat_backend SET search_path=wire_identity,wire_chat,wire_main,wire_security;
ALTER ROLE wire_main_backend SET statement_timeout='5s';
ALTER ROLE wire_chat_backend SET statement_timeout='5s';
ALTER ROLE wire_main_backend SET lock_timeout='2s';
ALTER ROLE wire_chat_backend SET lock_timeout='2s';
ALTER ROLE wire_main_backend SET idle_in_transaction_session_timeout='15s';
ALTER ROLE wire_chat_backend SET idle_in_transaction_session_timeout='15s';
