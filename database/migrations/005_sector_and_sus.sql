-- 005_sector_and_sus.sql
--
-- Two attributes that separate the public health network from private providers:
--   esfera_juridica  legal sphere, from the first digit of the CNES legal nature code
--   atende_sus       the facility declares services provided under the SUS agreement
-- Both are produced by limpeza.py.
--
-- Idempotent.

begin;

alter table public.infraestrutura_saude add column if not exists esfera_juridica text;
alter table public.infraestrutura_saude add column if not exists atende_sus boolean;

comment on column public.infraestrutura_saude.esfera_juridica is
    'Administração Pública (legal nature 1xxx), Entidade Empresarial (2xxx), Entidade sem Fins Lucrativos (3xxx), Pessoa Física (4xxx).';
comment on column public.infraestrutura_saude.atende_sus is
    'True when CNES lists at least one service provided under agreement 01 (SUS) for the facility.';

commit;

notify pgrst, 'reload schema';
