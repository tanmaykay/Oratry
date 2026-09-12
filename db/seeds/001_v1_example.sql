-- Development-only, deterministic example data. Requires 0001_v1_schema.sql.
BEGIN;

INSERT INTO users (id, email, display_name, accepted_terms_at) VALUES
  ('10000000-0000-0000-0000-000000000001', 'maya@example.test', 'Maya Patel', '2026-09-01 09:00:00+00'),
  ('10000000-0000-0000-0000-000000000002', 'leo@example.test', 'Leo Martin', '2026-09-02 09:00:00+00');
INSERT INTO user_preferences (user_id, preferred_language, analysis_consent_at, timezone) VALUES
  ('10000000-0000-0000-0000-000000000001', 'en', '2026-09-01 09:00:00+00', 'Asia/Kolkata'),
  ('10000000-0000-0000-0000-000000000002', 'en', '2026-09-02 09:00:00+00', 'Europe/Paris');

INSERT INTO vocabulary (id, term, normalized_term, language_code, definition, example_usage) VALUES
  ('20000000-0000-0000-0000-000000000001', 'concise', 'concise', 'en', 'Giving information clearly using few words.', 'Keep the conclusion concise.'),
  ('20000000-0000-0000-0000-000000000002', 'transition', 'transition', 'en', 'A link from one idea to the next.', 'Use a transition before your second point.'),
  ('20000000-0000-0000-0000-000000000003', 'nuance', 'nuance', 'en', 'A subtle distinction or variation.', 'Acknowledge the nuance in the opposing view.');

INSERT INTO challenges (id, challenge_family_id, version, title, prompt, preparation_guidance, target_skills, difficulty, target_duration_seconds, rubric_version) VALUES
  ('30000000-0000-0000-0000-000000000001', '31000000-0000-0000-0000-000000000001', 1, 'A useful local change', 'Describe one change your community should make and defend it.', 'Prepare a clear claim, two reasons, and a conclusion.', ARRAY['thinking','structure']::skill_code[], 1, 120, 'v1'),
  ('30000000-0000-0000-0000-000000000002', '31000000-0000-0000-0000-000000000002', 1, 'Explain a complex choice', 'Explain a difficult decision you made and what you learned.', 'Use a transition between context, decision, and reflection.', ARRAY['structure','fluency','language']::skill_code[], 2, 150, 'v1');
INSERT INTO challenge_vocabulary (challenge_id, vocabulary_id, is_required) VALUES
  ('30000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', false),
  ('30000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002', true);

INSERT INTO sessions (id, user_id, started_at, ended_at, client_platform) VALUES
  ('40000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '2026-09-03 10:00:00+00', '2026-09-03 10:08:00+00', 'web'),
  ('40000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', '2026-09-04 11:00:00+00', NULL, 'web');
INSERT INTO challenge_assignments (id, user_id, challenge_id, reason, sequence, status, assigned_at) VALUES
  ('50000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 'baseline', 1, 'in_progress', '2026-09-03 09:55:00+00'),
  ('50000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000002', 'baseline', 1, 'assigned', '2026-09-04 10:55:00+00');
INSERT INTO challenge_attempts (id, user_id, assignment_id, session_id, comparison_group_id, ordinal, status, created_at) VALUES
  ('60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '50000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000001', '61000000-0000-0000-0000-000000000001', 1, 'uploading', '2026-09-03 10:01:00+00');
INSERT INTO user_vocabulary (user_id, vocabulary_id, status, current_proficiency) VALUES
  ('10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'learning', 25);
INSERT INTO user_vocabulary_observations (user_vocabulary_id, proficiency, confidence, source, observed_at)
SELECT id, 25, 0.80, 'user_self_assessment', '2026-09-03 09:59:00+00' FROM user_vocabulary
 WHERE user_id = '10000000-0000-0000-0000-000000000001';

COMMIT;
