-- 003_corrected_coordinates.sql
--
-- Adds the coordinate source 'cnefe_corrected': the CNES coordinate was replaced
-- by the CNEFE 2022 address because the two differ although street, number and CEP
-- match exactly (rule and threshold in seed.py). The original CNES values stay in
-- NU_LATITUDE / NU_LONGITUDE. Applied by database/seeders/seed.py.
--
-- Idempotent.

begin;

alter table public.infraestrutura_saude drop constraint if exists infraestrutura_saude_coord_source_check;
alter table public.infraestrutura_saude add constraint infraestrutura_saude_coord_source_check
    check (coord_source in ('cnes', 'cnefe_address', 'cnefe_street', 'cnefe_cep', 'cnefe_corrected'));

alter table public.infraestrutura_saude add column if not exists coord_shift_m integer;
comment on column public.infraestrutura_saude.coord_shift_m is
    'For coord_source = cnefe_corrected: distance in metres between the discarded CNES coordinate and the CNEFE address now used.';

commit;

notify pgrst, 'reload schema';
