-- Tuberculosis by municipality of residence (was: of notification). Values from
-- indicadores_municipais_rmsp.csv, query tb_res in database/tabnet/fetch_tabnet.py.

update public.indicadores_municipio m
set tuberculose_2022 = v.t22, tuberculose_2023 = v.t23, tuberculose_2024 = v.t24, tuberculose_2025 = v.t25
from (values
    ('350390', 30, 39, 21, 38),
    ('350570', 168, 128, 174, 176),
    ('350660', 9, 10, 12, 8),
    ('350900', 43, 43, 43, 33),
    ('350920', 31, 22, 35, 34),
    ('351060', 291, 315, 312, 377),
    ('351300', 92, 129, 137, 131),
    ('351380', 226, 275, 248, 244),
    ('351500', 122, 151, 194, 136),
    ('351510', 32, 29, 34, 37),
    ('351570', 80, 109, 106, 109),
    ('351630', 81, 103, 104, 85),
    ('351640', 141, 182, 207, 129),
    ('351830', 6, 6, 13, 3),
    ('351880', 604, 694, 800, 884),
    ('352220', 100, 91, 102, 106),
    ('352250', 189, 170, 159, 161),
    ('352310', 149, 153, 148, 207),
    ('352500', 46, 45, 57, 40),
    ('352620', 13, 14, 21, 18),
    ('352850', 25, 24, 31, 22),
    ('352940', 175, 219, 215, 186),
    ('353060', 208, 216, 202, 217),
    ('353440', 376, 351, 344, 382),
    ('353980', 46, 58, 55, 45),
    ('353910', 5, 13, 21, 12),
    ('354330', 24, 26, 33, 29),
    ('354410', 13, 12, 9, 16),
    ('354500', 1, 4, 3, 4),
    ('354680', 17, 26, 31, 32),
    ('354730', 52, 37, 52, 67),
    ('354780', 259, 271, 256, 244),
    ('354870', 280, 316, 328, 294),
    ('354880', 25, 43, 24, 36),
    ('354995', 4, 5, 12, 8),
    ('355030', 8459, 9369, 9772, 9346),
    ('355250', 141, 139, 153, 145),
    ('355280', 149, 140, 170, 167),
    ('355645', 13, 21, 31, 15)
) as v(cd, t22, t23, t24, t25)
where m.cd_municipio6 = v.cd;

comment on table public.indicadores_municipio is
    'Municipal health outcomes, RMSP. dengue_*: probable cases by residence and year of first symptoms. lepto_*: confirmed cases by residence. tuberculose_*: confirmed cases by municipality of residence and year of diagnosis (SINAN/TBWEB). nasc_*: live births by mother''s residence, 2022-2026 pooled. obitos_*: deaths at ages 30-69 by residence and ICD-10 chapter, 2022-2026 pooled.';
