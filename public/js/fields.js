// English labels and groupings for the Portuguese column names and category
// values stored in the database.

export const TYPE_GROUPS = [
  { id: 'primary', label: 'Primary care', color: '#2a78d6' },
  { id: 'hospital', label: 'Hospitals', color: '#eb6834' },
  { id: 'emergency', label: 'Emergency & urgent care', color: '#1baf7a' },
  { id: 'specialised', label: 'Specialised & mental health', color: '#eda100' },
  { id: 'diagnostic', label: 'Diagnostics & therapy support', color: '#e87ba4' },
];

export const FACILITY_TYPES = {
  'Centro de Saúde/UBS': { label: 'Primary care centre (UBS)', group: 'primary' },
  'Posto de Saúde': { label: 'Health post', group: 'primary' },
  'Polo Academia da Saúde': { label: 'Health Academy hub', group: 'primary' },
  'Hospital Geral': { label: 'General hospital', group: 'hospital' },
  'Hospital Especializado': { label: 'Specialised hospital', group: 'hospital' },
  'Unidade Mista': { label: 'Mixed unit', group: 'hospital' },
  'Pronto Atendimento (UPA)': { label: 'Urgent care unit (UPA)', group: 'emergency' },
  'Pronto Socorro Geral': { label: 'General emergency room', group: 'emergency' },
  'Pronto Socorro Especializado': { label: 'Specialised emergency room', group: 'emergency' },
  'Policlínica': { label: 'Polyclinic', group: 'specialised' },
  'Clínica/Centro de Especialidade': { label: 'Specialty clinic', group: 'specialised' },
  'Centro de Atenção Psicossocial (CAPS)': { label: 'Psychosocial care centre (CAPS)', group: 'specialised' },
  'Unidade de Apoio Diagnose e Terapia (SADT Isolado)': { label: 'Diagnostic & therapy support unit (SADT)', group: 'diagnostic' },
};

const GROUP_BY_ID = Object.fromEntries(TYPE_GROUPS.map((group) => [group.id, group]));

export function typeInfo(type) {
  const info = FACILITY_TYPES[type] || { label: type || 'Unknown type', group: 'specialised' };
  return { ...info, color: GROUP_BY_ID[info.group].color, groupLabel: GROUP_BY_ID[info.group].label };
}

export const MANAGEMENT = {
  Municipal: 'Municipal',
  Estadual: 'State',
  Dupla: 'Dual (municipal and state)',
};

export const CLIENTELE_FLOW = {
  'Atendimento de Demanda Espontânea': 'Walk-in demand',
  'Atendimento de Demanda Referenciada': 'Referred demand',
  'Atendimento de Demanda Espontânea e Referenciada': 'Walk-in and referred demand',
};

// CNES service-shift codes (CO_TURNO_ATENDIMENTO)
export const SHIFTS = {
  1: 'Mornings only',
  2: 'Afternoons only',
  3: 'Mornings and afternoons',
  4: 'Mornings, afternoons and evenings',
  5: 'Intermittent shifts',
  6: 'Continuous, 24 hours a day',
  7: 'Evenings only',
};

export const COORD_STATUS = {
  missing: 'The CNES registry has no coordinates for this facility.',
  placeholder: 'The CNES registry only holds a generic municipal reference point for this facility, not its real position.',
  out_of_region: 'The registered coordinates fall outside the São Paulo Metropolitan Region.',
};

/** Sentence describing how a geocoded position was obtained, or null for registry coordinates. */
export function positionNote(row) {
  const precision = formatNumber(row.coord_precision_m);
  switch (row.coord_source) {
    case 'cnefe_address':
      return 'Position taken from the census address registry (CNEFE 2022) for this exact street address, because the CNES coordinate was missing or unusable.';
    case 'cnefe_corrected':
      return `Position corrected. The coordinate in the CNES registry was ${formatDistance(row.coord_shift_m)} away from this facility's own street address in the census address registry (CNEFE 2022), so the address position is used instead.`;
    case 'cnefe_street':
      return `Approximate position: the nearest house number on the same street in the census address registry (CNEFE 2022). Expected to be within about ${precision} m.`;
    case 'cnefe_cep':
      return `Approximate position: the centre of this facility's postcode (CEP) in the census address registry (CNEFE 2022). The facility is within ${precision} m of this point.`;
    default:
      return null;
  }
}

export const APPROXIMATE_SOURCES = new Set(['cnefe_street', 'cnefe_cep']);

// [column with all beds, column with SUS beds, label]
export const ICU_BEDS = [
  ['UTI_ADULTO_EXIST', 'UTI_ADULTO_SUS', 'Adult ICU'],
  ['UTI_PEDIATRICO_EXIST', 'UTI_PEDIATRICO_SUS', 'Paediatric ICU'],
  ['UTI_NEONATAL_EXIST', 'UTI_NEONATAL_SUS', 'Neonatal ICU'],
  ['UTI_CORONARIANA_EXIST', 'UTI_CORONARIANA_SUS', 'Coronary ICU'],
  ['UTI_QUEIMADO_EXIST', 'UTI_QUEIMADO_SUS', 'Burns ICU'],
];

export const EQUIPMENT = {
  equip_diagnostico_por_imagem: 'Diagnostic imaging',
  equip_equipamentos_por_metodos_graficos: 'Graphic methods (ECG, EEG)',
  equip_equipamentos_por_metodos_opticos: 'Optical methods (endoscopy)',
  equip_manutencao_da_vida: 'Life support',
  equip_odontologia: 'Dentistry',
  equip_dialise: 'Dialysis',
  equip_quimioterapia: 'Chemotherapy',
  equip_radioterapia: 'Radiotherapy',
  equip_reabilitacao: 'Rehabilitation',
  equip_audiologia: 'Audiology',
  equip_avaliacao_antropometrica_e_funcional: 'Anthropometric & functional assessment',
  equip_procedimentos_cirurgicos: 'Surgical procedures',
  equip_procedimentos_clinicos: 'Clinical procedures',
  equip_telessaude_por_imagem: 'Imaging telehealth',
  'equip_equipamentos_de_infra-estrutura': 'Infrastructure',
  equip_outros_equipamentos: 'Other equipment',
};

export const SPECIALTIES = {
  esp_clinico_geral: 'General practitioners',
  esp_medico_familia: 'Family physicians',
  esp_pediatra: 'Paediatricians',
  esp_ginecologista_obstetra: 'Gynaecologists / obstetricians',
  esp_cardiologista: 'Cardiologists',
  esp_endocrinologista: 'Endocrinologists',
  esp_infecto_pneumo: 'Infectious disease / pulmonology',
  esp_oncologista: 'Oncologists',
  esp_psiquiatra: 'Psychiatrists',
  esp_psicologo: 'Psychologists',
  esp_terapeuta_ocupacional: 'Occupational therapists',
};

// SIH admissions by ICD-10 chapter
export const ADMISSIONS = {
  internacoes_infecciosas_parasitarias: 'Infectious and parasitic diseases',
  internacoes_neoplasias_tumores: 'Neoplasms',
  internacoes_sangue_imunitarias: 'Blood and immune disorders',
  internacoes_endocrinas_nutricionais: 'Endocrine, nutritional and metabolic',
  internacoes_transtornos_mentais: 'Mental and behavioural disorders',
  internacoes_sistema_nervoso: 'Nervous system',
  internacoes_olho_anexos: 'Eye and adnexa',
  internacoes_ouvido_mastoide: 'Ear and mastoid',
  internacoes_aparelho_circulatorio: 'Circulatory system',
  internacoes_aparelho_respiratorio: 'Respiratory system',
  internacoes_aparelho_digestivo: 'Digestive system',
  internacoes_pele_tecido_subcutaneo: 'Skin and subcutaneous tissue',
  internacoes_osteomuscular_conjuntivo: 'Musculoskeletal and connective tissue',
  internacoes_aparelho_geniturinario: 'Genitourinary system',
  internacoes_gravidez_parto_puerperio: 'Pregnancy, childbirth and puerperium',
  internacoes_afeccoes_perinatais: 'Perinatal conditions',
  internacoes_malformacoes_congenitas: 'Congenital malformations',
  internacoes_sintomas_sinais_anormais: 'Symptoms and abnormal findings',
  internacoes_lesoes_envenenamentos: 'Injury and poisoning',
  internacoes_contatos_servicos_saude: 'Contact with health services',
};

const NUMBER = new Intl.NumberFormat('en-US');

export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '–';
  return Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatCount(value) {
  return value === null || value === undefined ? '–' : NUMBER.format(value);
}

export function formatPercent(value) {
  return value === null || value === undefined ? '–' : `${formatNumber(value, 1)}%`;
}

export function formatDistance(metres) {
  return metres < 1000 ? `${Math.round(metres)} m` : `${(metres / 1000).toFixed(1)} km`;
}

// The database stores these codes as integers, which drops leading zeros
export function formatCnes(cnes) {
  return String(cnes).padStart(7, '0');
}

export function formatCep(cep) {
  if (!cep) return '';
  const digits = String(cep).padStart(8, '0');
  return `${digits.slice(0, 5)}-${digits.slice(5)}`;
}

export function facilityName(row) {
  return (row.NO_FANTASIA || '').trim() || row.NO_RAZAO_SOCIAL || `CNES ${formatCnes(row.CO_CNES)}`;
}

export function facilityAddress(row) {
  const street = [row.NO_LOGRADOURO, row.NU_ENDERECO].filter(Boolean).join(', ');
  return [street, row.NO_BAIRRO, formatCep(row.CO_CEP)].filter(Boolean).join(' · ');
}
