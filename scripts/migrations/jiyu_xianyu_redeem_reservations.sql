BEGIN;

CREATE TABLE IF NOT EXISTS public.xianyu_redeem_reservations (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_hash character(64) NOT NULL UNIQUE,
  redeem_code_id bigint NOT NULL UNIQUE REFERENCES public.redeem_codes(id) ON DELETE RESTRICT,
  denomination numeric(20,8) NOT NULL,
  plan_id character varying(120) NOT NULL DEFAULT '',
  reserved_at timestamp with time zone NOT NULL DEFAULT NOW(),
  updated_at timestamp with time zone NOT NULL DEFAULT NOW(),
  CONSTRAINT xianyu_redeem_reservations_order_hash_format
    CHECK (order_hash ~ '^[a-f0-9]{64}$'),
  CONSTRAINT xianyu_redeem_reservations_denomination
    CHECK (denomination IN (1, 10, 30, 50, 100, 300, 500, 1000))
);

COMMENT ON TABLE public.xianyu_redeem_reservations IS
  'Idempotent Xianyu order-to-Sub2API redeem-code reservations; stores no order ID or code plaintext.';

CREATE OR REPLACE FUNCTION public.jiyu_xianyu_reserve_redeem_code(
  p_order_hash text,
  p_denomination numeric,
  p_plan_id text DEFAULT ''
)
RETURNS TABLE (
  redeem_code_id bigint,
  code text,
  type text,
  value numeric,
  status text,
  reserved_at timestamp with time zone,
  idempotent boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $function$
DECLARE
  reservation public.xianyu_redeem_reservations%ROWTYPE;
  redeem public.redeem_codes%ROWTYPE;
BEGIN
  IF p_order_hash !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'INVALID_ORDER_HASH';
  END IF;
  IF p_denomination NOT IN (1, 10, 30, 50, 100, 300, 500, 1000) THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'UNSUPPORTED_DENOMINATION';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_hash, 0));

  SELECT * INTO reservation
  FROM public.xianyu_redeem_reservations
  WHERE order_hash = p_order_hash;

  IF FOUND THEN
    IF reservation.denomination <> p_denomination THEN
      RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'ORDER_DENOMINATION_MISMATCH';
    END IF;
    SELECT * INTO redeem FROM public.redeem_codes WHERE id = reservation.redeem_code_id;
    RETURN QUERY SELECT redeem.id, redeem.code::text, redeem.type::text, redeem.value,
      redeem.status::text, reservation.reserved_at, TRUE;
    RETURN;
  END IF;

  SELECT candidate.* INTO redeem
  FROM public.redeem_codes AS candidate
  WHERE candidate.type = 'balance'
    AND candidate.value = p_denomination
    AND candidate.status = 'unused'
    AND (candidate.expires_at IS NULL OR candidate.expires_at > NOW())
    AND NOT EXISTS (
      SELECT 1 FROM public.xianyu_redeem_reservations AS existing
      WHERE existing.redeem_code_id = candidate.id
    )
  ORDER BY candidate.id
  FOR UPDATE OF candidate SKIP LOCKED
  LIMIT 1;

  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NO_AVAILABLE_REDEEM_CODE';
  END IF;

  INSERT INTO public.xianyu_redeem_reservations (
    order_hash, redeem_code_id, denomination, plan_id
  ) VALUES (
    p_order_hash, redeem.id, p_denomination, LEFT(COALESCE(p_plan_id, ''), 120)
  ) RETURNING * INTO reservation;

  RETURN QUERY SELECT redeem.id, redeem.code::text, redeem.type::text, redeem.value,
    redeem.status::text, reservation.reserved_at, FALSE;
END;
$function$;

CREATE OR REPLACE FUNCTION public.jiyu_xianyu_remap_redeem_reservation(
  p_old_order_hash text,
  p_new_order_hash text
)
RETURNS TABLE (
  redeem_code_id bigint,
  code text,
  type text,
  value numeric,
  status text,
  reserved_at timestamp with time zone,
  idempotent boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $function$
DECLARE
  reservation public.xianyu_redeem_reservations%ROWTYPE;
  conflict_reservation public.xianyu_redeem_reservations%ROWTYPE;
  redeem public.redeem_codes%ROWTYPE;
BEGIN
  IF p_old_order_hash !~ '^[a-f0-9]{64}$' OR p_new_order_hash !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'INVALID_ORDER_HASH';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(LEAST(p_old_order_hash, p_new_order_hash), 0));
  PERFORM pg_advisory_xact_lock(hashtextextended(GREATEST(p_old_order_hash, p_new_order_hash), 0));

  SELECT * INTO reservation
  FROM public.xianyu_redeem_reservations
  WHERE order_hash = p_old_order_hash;
  SELECT * INTO conflict_reservation
  FROM public.xianyu_redeem_reservations
  WHERE order_hash = p_new_order_hash;

  IF reservation.id IS NULL THEN
    IF conflict_reservation.id IS NULL THEN
      RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'RESERVATION_NOT_FOUND';
    END IF;
    reservation := conflict_reservation;
    SELECT * INTO redeem FROM public.redeem_codes WHERE id = reservation.redeem_code_id;
    RETURN QUERY SELECT redeem.id, redeem.code::text, redeem.type::text, redeem.value,
      redeem.status::text, reservation.reserved_at, TRUE;
    RETURN;
  END IF;

  IF conflict_reservation.id IS NOT NULL AND conflict_reservation.id <> reservation.id THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'TARGET_ORDER_ALREADY_RESERVED';
  END IF;

  UPDATE public.xianyu_redeem_reservations
  SET order_hash = p_new_order_hash, updated_at = NOW()
  WHERE id = reservation.id
  RETURNING * INTO reservation;
  SELECT * INTO redeem FROM public.redeem_codes WHERE id = reservation.redeem_code_id;
  RETURN QUERY SELECT redeem.id, redeem.code::text, redeem.type::text, redeem.value,
    redeem.status::text, reservation.reserved_at, p_old_order_hash = p_new_order_hash;
END;
$function$;

REVOKE ALL ON TABLE public.xianyu_redeem_reservations FROM PUBLIC;
REVOKE ALL ON FUNCTION public.jiyu_xianyu_reserve_redeem_code(text, numeric, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.jiyu_xianyu_remap_redeem_reservation(text, text) FROM PUBLIC;

COMMIT;
