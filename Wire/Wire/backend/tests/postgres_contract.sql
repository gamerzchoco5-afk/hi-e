BEGIN;
SET LOCAL ROLE wire_main_backend;
SET LOCAL search_path=wire_identity,wire_main,wire_security;
DO $$
DECLARE a text:=gen_random_uuid()::text; b text:=gen_random_uuid()::text; client text:=gen_random_uuid()::text;
BEGIN
  PERFORM set_config('wire.test_a',a,true);
  PERFORM set_config('wire.test_b',b,true);
  INSERT INTO users(id,username,email,display_name,date_of_birth,bio,pronouns,password_hash,email_verified,disabled,timed_out_until,avatar_version,message_requests,show_activity,created_at)
  VALUES(a,'qa_'||substr(replace(a,'-',''),1,12),a||'@example.invalid','QA account','2000-01-01','','','test-only-not-a-real-credential',true,false,0,0,true,true,extract(epoch from now())::int),
        (b,'qa_'||substr(replace(b,'-',''),1,12),b||'@example.invalid','QA account','2000-01-01','','','test-only-not-a-real-credential',true,false,0,0,true,true,extract(epoch from now())::int);
  INSERT INTO posts(author_id,parent_id,kind,title,body,client_id,created_at) VALUES(a,null,'note','','Contract test',client,extract(epoch from now())::int);
  BEGIN
    INSERT INTO posts(author_id,parent_id,kind,title,body,client_id,created_at) VALUES(a,null,'note','','Duplicate',client,extract(epoch from now())::int);
    RAISE EXCEPTION 'Idempotency unique constraint did not reject a duplicate';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;
END $$;
RESET ROLE;
SET LOCAL ROLE wire_chat_backend;
SET LOCAL search_path=wire_identity,wire_chat,wire_main,wire_security;
DO $$
DECLARE a text:=current_setting('wire.test_a'); b text:=current_setting('wire.test_b'); c text:=gen_random_uuid()::text;
BEGIN
  BEGIN
    PERFORM password_hash FROM wire_identity.users LIMIT 1;
    RAISE EXCEPTION 'Chat role unexpectedly read password hashes';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  BEGIN
    PERFORM body FROM wire_main.posts LIMIT 1;
    RAISE EXCEPTION 'Chat role unexpectedly read social posts';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  INSERT INTO conversations(id,user_a,user_b,starter_id,accepted,read_a,read_b,updated_at)
  VALUES(c,least(a,b),greatest(a,b),a,true,0,0,extract(epoch from now())::int);
  INSERT INTO messages(conversation_id,sender_id,client_id,body,deleted,created_at)
  VALUES(c,a,gen_random_uuid()::text,'Contract test',false,extract(epoch from now())::int);
  IF (SELECT count(*) FROM messages WHERE conversation_id=c)<>1 THEN
    RAISE EXCEPTION 'Chat role could not persist its message';
  END IF;
END $$;
RESET ROLE;
SET LOCAL ROLE wire_main_backend;
SET LOCAL search_path=wire_identity,wire_main,wire_security;
DELETE FROM users WHERE id IN (current_setting('wire.test_a'),current_setting('wire.test_b'));
RESET ROLE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM wire_chat.conversations WHERE starter_id=current_setting('wire.test_a')) THEN
  RAISE EXCEPTION 'Account deletion did not cascade into chat';
 END IF;
END $$;
ROLLBACK;
