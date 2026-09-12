-- Cross-row ownership/retry invariants which cannot be expressed as CHECK constraints.
BEGIN;

CREATE OR REPLACE FUNCTION enforce_attempt_integrity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    assignment_owner uuid;
    session_owner uuid;
    parent challenge_attempts%ROWTYPE;
BEGIN
    SELECT user_id INTO assignment_owner FROM challenge_assignments WHERE id = NEW.assignment_id;
    IF assignment_owner IS NULL OR assignment_owner <> NEW.user_id THEN
        RAISE EXCEPTION 'attempt user must own its assignment' USING ERRCODE = '23514';
    END IF;

    IF NEW.session_id IS NOT NULL THEN
        SELECT user_id INTO session_owner FROM sessions WHERE id = NEW.session_id;
        IF session_owner IS NULL OR session_owner <> NEW.user_id THEN
            RAISE EXCEPTION 'attempt user must own its session' USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.retry_of_attempt_id IS NOT NULL THEN
        SELECT * INTO parent FROM challenge_attempts WHERE id = NEW.retry_of_attempt_id;
        IF parent.id IS NULL
           OR parent.user_id <> NEW.user_id
           OR parent.assignment_id <> NEW.assignment_id
           OR parent.comparison_group_id <> NEW.comparison_group_id
           OR parent.status <> 'completed'
           OR NEW.ordinal <> parent.ordinal + 1 THEN
            RAISE EXCEPTION 'retry must immediately follow a completed attempt for the same user, assignment, and comparison group'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER challenge_attempts_integrity_trigger
BEFORE INSERT OR UPDATE OF user_id, assignment_id, session_id, comparison_group_id, retry_of_attempt_id, ordinal, status
ON challenge_attempts
FOR EACH ROW EXECUTE FUNCTION enforce_attempt_integrity();

COMMIT;
