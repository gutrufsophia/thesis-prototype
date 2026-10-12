// Labels, groupings and formatters for the column names and category values stored
// in the database. Every label exists in Portuguese and English.

import { locale, pick, t } from './i18n.js';

export const TYPE_GROUPS = [
  { id: 'primary', label: { pt: 'Atenção básica', en: 'Primary care' }, color: '#2a78d6' },
  { id: 'hospital', label: { pt: 'Hospitais', en: 'Hospitals' }, color: '#eb6834' },
  { id: 'emergency', label: { pt: 'Urgência e emergência', en: 'Emergency & urgent care' }, color: '#1baf7a' },
  { id: 'specialised', label: { pt: 'Especializada e saúde mental', en: 'Specialised & mental health' }, color: '#eda100' },
  { id: 'diagnostic', label: { pt: 'Diagnose e terapia', en: 'Diagnostics & therapy support' }, color: '#e87ba4' },
];

// Keyed by the value of tipo_equipamento (the CNES facility type), in display order
export const FACILITY_TYPES = {
  'Centro de Saúde/UBS': { pt: 'Centro de Saúde / UBS', en: 'Primary care centre (UBS)', group: 'primary' },
  'Posto de Saúde': { pt: 'Posto de Saúde', en: 'Health post', group: 'primary' },
  'Polo Academia da Saúde': { pt: 'Polo Academia da Saúde', en: 'Health Academy hub', group: 'primary' },
  'Hospital Geral': { pt: 'Hospital Geral', en: 'General hospital', group: 'hospital' },
  'Hospital Especializado': { pt: 'Hospital Especializado', en: 'Specialised hospital', group: 'hospital' },
  'Unidade Mista': { pt: 'Unidade Mista', en: 'Mixed unit', group: 'hospital' },
  'Pronto Atendimento (UPA)': { pt: 'Pronto Atendimento (UPA)', en: 'Urgent care unit (UPA)', group: 'emergency' },
  'Pronto Socorro Geral': { pt: 'Pronto Socorro Geral', en: 'General emergency room', group: 'emergency' },
  'Pronto Socorro Especializado': { pt: 'Pronto Socorro Especializado', en: 'Specialised emergency room', group: 'emergency' },
  'Policlínica': { pt: 'Policlínica', en: 'Polyclinic', group: 'specialised' },
  'Clínica/Centro de Especialidade': { pt: 'Clínica / Centro de Especialidade', en: 'Specialty clinic', group: 'specialised' },
  'Centro de Atenção Psicossocial (CAPS)': { pt: 'Centro de Atenção Psicossocial (CAPS)', en: 'Psychosocial care centre (CAPS)', group: 'specialised' },
  'Unidade de Apoio Diagnose e Terapia (SADT Isolado)': { pt: 'Apoio à Diagnose e Terapia (SADT)', en: 'Diagnostic & therapy support unit (SADT)', group: 'diagnostic' },
};

const GROUP_BY_ID = Object.fromEntries(TYPE_GROUPS.map((group) => [group.id, group]));

export function typeInfo(type) {
  const info = FACILITY_TYPES[type] || { pt: type || t('notReported'), en: type || t('notReported'), group: 'specialised' };
  const group = GROUP_BY_ID[info.group];
  return { label: pick(info), group: info.group, color: group.color, groupLabel: pick(group.label) };
}

const MANAGEMENT = {
  Municipal: { pt: 'Municipal', en: 'Municipal' },
  Estadual: { pt: 'Estadual', en: 'State' },
  Dupla: { pt: 'Dupla (municipal e estadual)', en: 'Dual (municipal and state)' },
};

const CLIENTELE_FLOW = {
  'Atendimento de Demanda Espontânea': { pt: 'Demanda espontânea', en: 'Walk-in demand' },
  'Atendimento de Demanda Referenciada': { pt: 'Demanda referenciada', en: 'Referred demand' },
  'Atendimento de Demanda Espontânea e Referenciada': { pt: 'Demanda espontânea e referenciada', en: 'Walk-in and referred demand' },
};

// CNES service-shift codes (CO_TURNO_ATENDIMENTO)
const SHIFTS = {
  1: { pt: 'Somente pela manhã', en: 'Mornings only' },
  2: { pt: 'Somente à tarde', en: 'Afternoons only' },
  3: { pt: 'Manhã e tarde', en: 'Mornings and afternoons' },
  4: { pt: 'Manhã, tarde e noite', en: 'Mornings, afternoons and evenings' },
  5: { pt: 'Turnos intermitentes', en: 'Intermittent shifts' },
  6: { pt: 'Contínuo, 24 horas por dia', en: 'Continuous, 24 hours a day' },
  7: { pt: 'Somente à noite', en: 'Evenings only' },
};

const LEGAL_SPHERE = {
  'Administração Pública': { pt: 'Administração pública', en: 'Public administration' },
  'Entidade Empresarial': { pt: 'Entidade empresarial (privada)', en: 'Private company' },
  'Entidade sem Fins Lucrativos': { pt: 'Entidade sem fins lucrativos', en: 'Non-profit entity' },
  'Pessoa Física': { pt: 'Pessoa física', en: 'Individual' },
};

function coded(map, value) {
  return value in map ? pick(map[value]) : t('notReported');
}

export const managementLabel = (value) => coded(MANAGEMENT, value);
export const flowLabel = (value) => coded(CLIENTELE_FLOW, value);
export const shiftLabel = (value) => coded(SHIFTS, value);
export const legalSphereLabel = (value) => coded(LEGAL_SPHERE, value);

export const APPROXIMATE_SOURCES = new Set(['cnefe_street', 'cnefe_cep']);

/** Why a facility has no position on the map. */
export function coordStatusNote(status) {
  return ['missing', 'placeholder', 'out_of_region'].includes(status) ? t(`status.${status}`) : t('status.unknown');
}

/** Sentence describing how a geocoded position was obtained, or null for registry coordinates. */
export function positionNote(row) {
  const precision = formatNumber(row.coord_precision_m);
  switch (row.coord_source) {
    case 'cnefe_address': return t('position.address');
    case 'cnefe_corrected': return t('position.corrected', { distance: formatDistance(row.coord_shift_m) });
    case 'cnefe_street': return t('position.street', { precision });
    case 'cnefe_cep': return t('position.cep', { precision });
    default: return null;
  }
}

// [column with all beds, column with SUS beds, label]
export const ICU_BEDS = [
  ['UTI_ADULTO_EXIST', 'UTI_ADULTO_SUS', { pt: 'UTI adulto', en: 'Adult ICU' }],
  ['UTI_PEDIATRICO_EXIST', 'UTI_PEDIATRICO_SUS', { pt: 'UTI pediátrica', en: 'Paediatric ICU' }],
  ['UTI_NEONATAL_EXIST', 'UTI_NEONATAL_SUS', { pt: 'UTI neonatal', en: 'Neonatal ICU' }],
  ['UTI_CORONARIANA_EXIST', 'UTI_CORONARIANA_SUS', { pt: 'UTI coronariana', en: 'Coronary ICU' }],
  ['UTI_QUEIMADO_EXIST', 'UTI_QUEIMADO_SUS', { pt: 'UTI de queimados', en: 'Burns ICU' }],
];

export const EQUIPMENT = {
  equip_diagnostico_por_imagem: { pt: 'Diagnóstico por imagem', en: 'Diagnostic imaging' },
  equip_equipamentos_por_metodos_graficos: { pt: 'Métodos gráficos (ECG, EEG)', en: 'Graphic methods (ECG, EEG)' },
  equip_equipamentos_por_metodos_opticos: { pt: 'Métodos ópticos (endoscopia)', en: 'Optical methods (endoscopy)' },
  equip_manutencao_da_vida: { pt: 'Manutenção da vida', en: 'Life support' },
  equip_odontologia: { pt: 'Odontologia', en: 'Dentistry' },
  equip_dialise: { pt: 'Diálise', en: 'Dialysis' },
  equip_quimioterapia: { pt: 'Quimioterapia', en: 'Chemotherapy' },
  equip_radioterapia: { pt: 'Radioterapia', en: 'Radiotherapy' },
  equip_reabilitacao: { pt: 'Reabilitação', en: 'Rehabilitation' },
  equip_audiologia: { pt: 'Audiologia', en: 'Audiology' },
  equip_avaliacao_antropometrica_e_funcional: { pt: 'Avaliação antropométrica e funcional', en: 'Anthropometric & functional assessment' },
  equip_procedimentos_cirurgicos: { pt: 'Procedimentos cirúrgicos', en: 'Surgical procedures' },
  equip_procedimentos_clinicos: { pt: 'Procedimentos clínicos', en: 'Clinical procedures' },
  equip_telessaude_por_imagem: { pt: 'Telessaúde por imagem', en: 'Imaging telehealth' },
  'equip_equipamentos_de_infra-estrutura': { pt: 'Infraestrutura', en: 'Infrastructure' },
  equip_outros_equipamentos: { pt: 'Outros equipamentos', en: 'Other equipment' },
};

export const SPECIALTIES = {
  esp_clinico_geral: { pt: 'Clínicos gerais', en: 'General practitioners' },
  esp_medico_familia: { pt: 'Médicos de família', en: 'Family physicians' },
  esp_pediatra: { pt: 'Pediatras', en: 'Paediatricians' },
  esp_ginecologista_obstetra: { pt: 'Ginecologistas / obstetras', en: 'Gynaecologists / obstetricians' },
  esp_cardiologista: { pt: 'Cardiologistas', en: 'Cardiologists' },
  esp_endocrinologista: { pt: 'Endocrinologistas', en: 'Endocrinologists' },
  esp_infecto_pneumo: { pt: 'Infectologistas / pneumologistas', en: 'Infectious disease / pulmonology' },
  esp_oncologista: { pt: 'Oncologistas', en: 'Oncologists' },
  esp_psiquiatra: { pt: 'Psiquiatras', en: 'Psychiatrists' },
  esp_psicologo: { pt: 'Psicólogos', en: 'Psychologists' },
  esp_terapeuta_ocupacional: { pt: 'Terapeutas ocupacionais', en: 'Occupational therapists' },
};

// SIH admissions by ICD-10 chapter
export const ADMISSIONS = {
  internacoes_infecciosas_parasitarias: { pt: 'Doenças infecciosas e parasitárias', en: 'Infectious and parasitic diseases' },
  internacoes_neoplasias_tumores: { pt: 'Neoplasias', en: 'Neoplasms' },
  internacoes_sangue_imunitarias: { pt: 'Sangue e transtornos imunitários', en: 'Blood and immune disorders' },
  internacoes_endocrinas_nutricionais: { pt: 'Endócrinas, nutricionais e metabólicas', en: 'Endocrine, nutritional and metabolic' },
  internacoes_transtornos_mentais: { pt: 'Transtornos mentais e comportamentais', en: 'Mental and behavioural disorders' },
  internacoes_sistema_nervoso: { pt: 'Sistema nervoso', en: 'Nervous system' },
  internacoes_olho_anexos: { pt: 'Olho e anexos', en: 'Eye and adnexa' },
  internacoes_ouvido_mastoide: { pt: 'Ouvido e apófise mastoide', en: 'Ear and mastoid' },
  internacoes_aparelho_circulatorio: { pt: 'Aparelho circulatório', en: 'Circulatory system' },
  internacoes_aparelho_respiratorio: { pt: 'Aparelho respiratório', en: 'Respiratory system' },
  internacoes_aparelho_digestivo: { pt: 'Aparelho digestivo', en: 'Digestive system' },
  internacoes_pele_tecido_subcutaneo: { pt: 'Pele e tecido subcutâneo', en: 'Skin and subcutaneous tissue' },
  internacoes_osteomuscular_conjuntivo: { pt: 'Sistema osteomuscular e tecido conjuntivo', en: 'Musculoskeletal and connective tissue' },
  internacoes_aparelho_geniturinario: { pt: 'Aparelho geniturinário', en: 'Genitourinary system' },
  internacoes_gravidez_parto_puerperio: { pt: 'Gravidez, parto e puerpério', en: 'Pregnancy, childbirth and puerperium' },
  internacoes_afeccoes_perinatais: { pt: 'Afecções perinatais', en: 'Perinatal conditions' },
  internacoes_malformacoes_congenitas: { pt: 'Malformações congênitas', en: 'Congenital malformations' },
  internacoes_sintomas_sinais_anormais: { pt: 'Sintomas e achados anormais', en: 'Symptoms and abnormal findings' },
  internacoes_lesoes_envenenamentos: { pt: 'Lesões e envenenamentos', en: 'Injury and poisoning' },
  internacoes_contatos_servicos_saude: { pt: 'Contatos com serviços de saúde', en: 'Contact with health services' },
};

export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '–';
  return Number(value).toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatCount(value) {
  return formatNumber(value, 0);
}

export function formatPercent(value) {
  return value === null || value === undefined ? '–' : `${formatNumber(value, 1)}%`;
}

export function formatDistance(metres) {
  return metres < 1000 ? `${formatNumber(Math.round(metres))} m` : `${formatNumber(metres / 1000, 1)} km`;
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
