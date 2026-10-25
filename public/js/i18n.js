// Interface language (Portuguese by default, English optional) and small persisted
// preferences. Switching language reloads the page, so every module can read `lang`
// once at load time.

function readStored(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function store(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage unavailable (private window): the choice lasts for this page only
  }
}

// A ?lang=en or ?lang=pt link sets the language too, so a page can be shared in either
const requested = new URLSearchParams(location.search).get('lang');
if (requested === 'en' || requested === 'pt') store('lang', requested);

export const lang = (requested === 'en' || requested === 'pt' ? requested : readStored('lang')) === 'en' ? 'en' : 'pt';
export const locale = lang === 'pt' ? 'pt-BR' : 'en-US';

export function setLang(value) {
  store('lang', value);
  location.reload();
}

export function getPref(key) {
  return readStored(key) === '1';
}

export function setPref(key, on) {
  store(key, on ? '1' : '0');
}

/** Value of a `{pt, en}` pair in the current language. */
export function pick(entry) {
  return typeof entry === 'string' ? entry : entry[lang];
}

const STRINGS = {
  'brand': { pt: 'CulturaEduca · Camada de saúde', en: 'CulturaEduca · Health layer' },
  'lang.label': { pt: 'Idioma', en: 'Language' },

  // Map page
  'map.title': { pt: 'Camada de Saúde CulturaEduca · Região Metropolitana de São Paulo', en: 'CulturaEduca Health Layer · São Paulo Metropolitan Region' },
  'map.heading': { pt: 'Unidades de saúde da Região Metropolitana de São Paulo', en: 'Health facilities of the São Paulo Metropolitan Region' },
  'map.intro': { pt: 'Cada ponto é uma unidade de saúde do cadastro nacional (CNES). Selecione uma para ver leitos, profissionais, equipamentos e internações.', en: 'Each point is a health facility from the national registry (CNES). Select one to see its beds, workforce, equipment and admissions.' },
  'map.loading': { pt: 'Carregando unidades…', en: 'Loading facilities…' },
  'map.loadError': { pt: 'Não foi possível carregar as unidades: {message}', en: 'Could not load facilities: {message}' },
  'map.status.shown': { pt: '{shown} unidades no mapa.', en: '{shown} facilities on the map.' },
  'map.status.private': { pt: '{count} unidades privadas sem vínculo com o SUS estão ocultas pelo filtro.', en: '{count} private facilities with no SUS link are hidden by the filter.' },
  'map.status.geocoded': { pt: 'Das unidades exibidas, {geocoded} foram posicionadas pelo endereço porque o cadastro não tinha coordenada utilizável ({approximate} com posição aproximada, em pontos vazados) e {corrected} tiveram a coordenada do cadastro substituída pela posição do endereço.', en: 'Of those shown, {geocoded} were placed from their street address because the registry had no usable coordinate ({approximate} approximate, drawn as hollow points) and {corrected} had their registry coordinate replaced by the address position.' },
  'map.status.unlocated': { pt: '{count} não puderam ser localizadas e só aparecem na busca.', en: '{count} could not be placed and can only be found through search.' },
  'search.label': { pt: 'Buscar unidades', en: 'Search facilities' },
  'search.placeholder': { pt: 'Buscar por nome da unidade ou código CNES', en: 'Search by facility name or CNES code' },
  'search.none': { pt: 'Nenhuma unidade encontrada.', en: 'No facility matches.' },
  'search.notOnMap': { pt: 'sem posição no mapa', en: 'not on map' },
  'search.private': { pt: 'privada, sem SUS', en: 'private, no SUS' },
  'filters.title': { pt: 'Filtros', en: 'Filters' },
  'filters.types': { pt: 'Tipo de unidade (CNES)', en: 'Facility type (CNES)' },
  'filters.publicOnly': { pt: 'Mostrar apenas unidades públicas ou com vínculo com o SUS', en: 'Show only public facilities and those with a SUS link' },
  'filters.hollow': { pt: 'Ponto vazado: posição aproximada', en: 'Hollow point: approximate position' },
  'panel.back': { pt: '← Todas as unidades', en: '← All facilities' },
  'panel.loading': { pt: 'Carregando {name}…', en: 'Loading {name}…' },
  'panel.more': { pt: 'Mais informações', en: 'More info' },
  'panel.notFound': { pt: 'Unidade não encontrada.', en: 'Facility not found.' },
  'panel.loadError': { pt: 'Não foi possível carregar esta unidade: {message}', en: 'Could not load this facility: {message}' },
  'panel.notOnMap': { pt: 'Não aparece no mapa.', en: 'Not shown on the map.' },
  'panel.hiddenPrivate': { pt: 'Unidade privada sem vínculo com o SUS: fica oculta no mapa enquanto o filtro "apenas públicas ou SUS" estiver ligado.', en: 'Private facility with no SUS link: hidden on the map while the "public or SUS only" filter is on.' },

  // Facility record
  'tile.beds': { pt: 'Leitos', en: 'Beds' },
  'tile.icu': { pt: 'Leitos de UTI', en: 'ICU beds' },
  'tile.physicians': { pt: 'Médicos', en: 'Physicians' },
  'tile.nurses': { pt: 'Enfermeiros', en: 'Nurses' },
  'tile.admissions': { pt: 'Internações', en: 'Admissions' },
  'tile.stay': { pt: 'Permanência média', en: 'Mean stay' },
  'tile.susNote': { pt: '{count} SUS', en: '{count} SUS' },
  'tile.days': { pt: '{value} dias', en: '{value} d' },
  'profile.title': { pt: 'Perfil', en: 'Profile' },
  'profile.cnes': { pt: 'Código CNES', en: 'CNES code' },
  'profile.legalName': { pt: 'Razão social', en: 'Legal name' },
  'profile.type': { pt: 'Tipo de unidade', en: 'Facility type' },
  'profile.sector': { pt: 'Esfera jurídica', en: 'Legal sphere' },
  'profile.sus': { pt: 'Atende pelo SUS', en: 'Provides SUS services' },
  'profile.management': { pt: 'Gestão', en: 'Management' },
  'profile.flow': { pt: 'Fluxo de clientela', en: 'Patient flow' },
  'profile.hours': { pt: 'Turno de atendimento', en: 'Opening hours' },
  'yes': { pt: 'Sim', en: 'Yes' },
  'no': { pt: 'Não', en: 'No' },
  'notReported': { pt: 'Não informado', en: 'Not reported' },
  'noData': { pt: 'sem dados', en: 'no data' },
  'noneRecorded': { pt: 'Nenhum registro.', en: 'None recorded.' },
  'topShown': { pt: 'Exibindo os {shown} maiores de {total}.', en: 'Top {shown} of {total} shown.' },
  'icu.title': { pt: 'Leitos de UTI por tipo', en: 'ICU beds by type' },
  'icu.empty': { pt: 'Nenhum leito de UTI cadastrado.', en: 'No ICU beds registered.' },
  'workforce.title': { pt: 'Profissionais por especialidade', en: 'Workforce by specialty' },
  'workforce.hint': { pt: 'Profissionais com vínculo ativo com a unidade, contados uma vez cada; inclui residentes e vínculos não SUS. {cnes}.', en: 'Professionals with an active link to this facility, counted once each; includes residents and non-SUS links. {cnes}.' },
  'workforce.empty': { pt: 'Nenhum profissional dessas especialidades cadastrado nesta unidade.', en: 'No professionals in these specialties are registered for this facility.' },
  'equipment.title': { pt: 'Equipamentos por categoria', en: 'Equipment by category' },
  'equipment.hint': { pt: 'Unidades de equipamento cadastradas. {cnes}.', en: 'Units of equipment registered. {cnes}.' },
  'equipment.empty': { pt: 'Nenhum equipamento cadastrado.', en: 'No equipment registered.' },
  'admissions.title': { pt: 'Internações por causa', en: 'Admissions by cause' },
  'admissions.hint': { pt: 'Internações hospitalares pelo SUS, por capítulo da CID-10. {sih} (19 meses); os últimos seis meses estão sujeitos a atualização.', en: 'SUS hospital admissions by ICD-10 chapter. {sih} (19 months); the last six months are subject to update.' },
  'admissions.empty': { pt: 'Sem internações pelo SUS registradas: a unidade não interna, ou não fatura pelo SUS.', en: 'No SUS hospital admissions recorded: this is not an inpatient unit, or it does not bill SUS.' },

  // Position notes
  'position.address': { pt: 'Posição obtida do cadastro de endereços do Censo (CNEFE 2022) para este mesmo endereço, porque a coordenada do CNES estava ausente ou inutilizável.', en: 'Position taken from the census address registry (CNEFE 2022) for this exact street address, because the CNES coordinate was missing or unusable.' },
  'position.corrected': { pt: 'Posição corrigida. A coordenada do CNES estava a {distance} do endereço desta unidade no cadastro de endereços do Censo (CNEFE 2022); por isso é usada a posição do endereço.', en: "Position corrected. The coordinate in the CNES registry was {distance} away from this facility's own street address in the census address registry (CNEFE 2022), so the address position is used instead." },
  'position.street': { pt: 'Posição aproximada: o número mais próximo na mesma rua, no cadastro de endereços do Censo (CNEFE 2022). Erro esperado de até cerca de {precision} m.', en: 'Approximate position: the nearest house number on the same street in the census address registry (CNEFE 2022). Expected to be within about {precision} m.' },
  'position.cep': { pt: 'Posição aproximada: o centro do CEP desta unidade no cadastro de endereços do Censo (CNEFE 2022). A unidade está a no máximo {precision} m deste ponto.', en: "Approximate position: the centre of this facility's postcode (CEP) in the census address registry (CNEFE 2022). The facility is within {precision} m of this point." },
  'status.missing': { pt: 'O CNES não tem coordenadas para esta unidade.', en: 'The CNES registry has no coordinates for this facility.' },
  'status.placeholder': { pt: 'O CNES só tem um ponto genérico do município para esta unidade, não a posição real.', en: 'The CNES registry only holds a generic municipal reference point for this facility, not its real position.' },
  'status.out_of_region': { pt: 'As coordenadas cadastradas caem fora da Região Metropolitana de São Paulo.', en: 'The registered coordinates fall outside the São Paulo Metropolitan Region.' },
  'status.unknown': { pt: 'Esta unidade não tem coordenadas utilizáveis.', en: 'This facility has no usable coordinates.' },

  // Facility page
  'page.back': { pt: '← Voltar ao mapa', en: '← Back to map' },
  'page.title': { pt: 'Unidade · Camada de Saúde CulturaEduca', en: 'Facility · CulturaEduca Health Layer' },
  'page.loading': { pt: 'Carregando unidade…', en: 'Loading facility…' },
  'page.noneSelected': { pt: 'Nenhuma unidade selecionada. Volte ao mapa e escolha uma.', en: 'No facility selected. Go back to the map and pick one.' },
  'page.unknownCnes': { pt: 'Nenhuma unidade com o código CNES {cnes}.', en: 'No facility with CNES code {cnes}.' },
  'page.noSurroundings': { pt: 'Não é possível analisar o entorno.', en: 'The surroundings cannot be analysed.' },
  'sur.title': { pt: 'Entorno', en: 'Surroundings' },
  'sur.location': { pt: 'Localizada em {place} · setor censitário {tract}', en: 'Located in {place} · census tract {tract}' },
  'sur.radius': { pt: 'Raio ao redor da unidade', en: 'Radius around the facility' },
  'sur.publicOnly': { pt: 'Considerar apenas unidades públicas ou com vínculo com o SUS', en: 'Count only public facilities and those with a SUS link' },
  'sur.radiusLimit': { pt: 'Raios abaixo de {radius} estão desativados, pois seriam menores que o dobro dessa incerteza.', en: 'Radii below {radius} are disabled, since they would be smaller than twice this uncertainty.' },
  'sur.loadError': { pt: 'Não foi possível carregar o entorno: {message}', en: 'Could not load the surroundings: {message}' },
  'sur.residents': { pt: 'Moradores (est.)', en: 'Residents (est.)' },
  'sur.tracts': { pt: '{count} setores censitários · Censo 2022', en: '{count} census tracts · 2022 Census' },
  'sur.households': { pt: 'Domicílios (est.)', en: 'Households (est.)' },
  'sur.density': { pt: 'Moradores por km²', en: 'Residents per km²' },
  'sur.others': { pt: 'Outras unidades', en: 'Other facilities' },
  'sur.withinRadius': { pt: 'dentro do raio · CNES {period}', en: 'within the radius · CNES {period}' },
  'sur.per10k': { pt: '{value} por 10 mil moradores · CNES {period}', en: '{value} per 10,000 residents · CNES {period}' },
  'sur.mapTitle': { pt: 'Setores censitários dentro do raio', en: 'Census tracts within the radius' },
  'sur.indicator': { pt: 'Indicador exibido no mapa', en: 'Indicator shown on the map' },
  'sur.compare': { pt: 'Comparação com o contexto', en: 'Compared with its context' },
  'sur.within': { pt: 'Em {radius}', en: 'Within {radius}' },
  'sur.municipality': { pt: 'Município', en: 'Municipality' },
  'sur.region': { pt: 'Região metropolitana', en: 'Metropolitan region' },
  'sur.byType': { pt: 'Outras unidades por tipo', en: 'Other facilities by type' },
  'sur.byTypeHint': { pt: 'A cor da barra é a categoria usada no mapa. {cnes}.', en: 'Bar colour is the facility category used on the map. {cnes}.' },
  'sur.noOthers': { pt: 'Nenhuma outra unidade dentro deste raio.', en: 'No other facility within this radius.' },
  'sur.nearest': { pt: 'Unidades mais próximas', en: 'Nearest facilities' },
  'sur.nearestHint': { pt: 'Distância em linha reta. {cnes}.', en: 'Straight-line distance. {cnes}.' },
  'sur.nearestOf': { pt: 'As {shown} mais próximas de {total}, em linha reta. {cnes}.', en: 'Closest {shown} of {total}, straight-line distance. {cnes}.' },
  'sur.hiddenPrivate': { pt: '{count} unidades privadas sem vínculo com o SUS dentro do raio não estão incluídas.', en: '{count} private facilities with no SUS link within the radius are not included.' },
  'sur.col.facility': { pt: 'Unidade', en: 'Facility' },
  'sur.col.type': { pt: 'Tipo', en: 'Type' },
  'sur.col.distance': { pt: 'Distância', en: 'Distance' },
  'sur.col.beds': { pt: 'Leitos', en: 'Beds' },
  'ind.noSewage': { pt: 'Domicílios sem ligação à rede de esgoto', en: 'Households not on the sewage network' },
  'ind.precarious': { pt: 'Domicílios com esgotamento precário', en: 'Households with precarious sewage disposal' },
  'ind.noGarbage': { pt: 'Domicílios sem coleta de lixo', en: 'Households without garbage collection' },
  'ind.crowding': { pt: 'Moradores por domicílio', en: 'Residents per household' },
  'ind.primaryDistance': { pt: 'Distância mediana até a unidade básica pública mais próxima', en: 'Median distance to the nearest public primary care unit' },
  'ter.scope.radius': { pt: 'Calculado para o raio de {radius} · {census}', en: 'Computed for the {radius} radius · {census}' },
  'ter.scope.municipality': { pt: 'Dado do município inteiro: {name}', en: 'Whole-municipality figure: {name}' },
  'ter.alsoReaches': { pt: 'O raio também alcança {names}; os indicadores abaixo são apenas de {home}.', en: 'The radius also reaches {names}; the indicators below are for {home} only.' },
  'ter.capitalNote': { pt: 'Na capital, estes indicadores valem para a cidade inteira, de 11,45 milhões de habitantes; o distrito, acima, é a escala mais próxima disponível.', en: 'For the capital these indicators cover the whole city of 11.45 million people; the district, above, is the closest scale available.' },
  'ter.capitalNoteNoDistrict': { pt: 'Na capital, estes indicadores valem para a cidade inteira, de 11,45 milhões de habitantes; dengue e leptospirose não são publicadas por distrito.', en: 'For the capital these indicators cover the whole city of 11.45 million people; dengue and leptospirosis are not published by district.' },
  'ter.scope.district': { pt: 'Dado do distrito: {name} · SMS-SP', en: 'District figure: {name} · SMS-SP' },
  'ter.cityWithDistricts': { pt: 'Cidade de São Paulo', en: 'São Paulo city' },
  'ter.cityReferenceLegend': { pt: 'Traço: valor da cidade de São Paulo (mesma fonte)', en: 'Tick: value for São Paulo city (same source)' },
  'ter.referenceLegend': { pt: 'Traço: valor da região metropolitana', en: 'Tick: value for the metropolitan region' },
  'ter.cases': { pt: '{count} casos', en: '{count} cases' },
  'ter.loadError': { pt: 'Não foi possível carregar os indicadores municipais: {message}', en: 'Could not load the municipal indicators: {message}' },
  'ter.env.title': { pt: 'Saneamento e doenças relacionadas ao ambiente', en: 'Sanitation and environment-related diseases' },
  'ter.env.dengue': { pt: 'Dengue: casos prováveis por 100 mil habitantes, por ano', en: 'Dengue: probable cases per 100,000 inhabitants, by year' },
  'ter.env.dengueHint': { pt: 'Por município de residência e ano dos primeiros sintomas (SINAN). 2026 não é mostrado por estar incompleto.', en: 'By municipality of residence and year of first symptoms (SINAN). 2026 is left out because it is incomplete.' },
  'ter.env.lepto': { pt: 'Leptospirose: casos confirmados por 100 mil habitantes, média anual 2022–2025', en: 'Leptospirosis: confirmed cases per 100,000 inhabitants, annual mean 2022–2025' },
  'ter.env.leptoHint': { pt: '{count} casos confirmados em {name} nos quatro anos (SINAN).', en: '{count} confirmed cases in {name} over the four years (SINAN).' },
  'ter.resp.title': { pt: 'Adensamento domiciliar e tuberculose', en: 'Household crowding and tuberculosis' },
  'ter.resp.crowded': { pt: 'Moradores em setores entre os 10% mais adensados da região ({threshold} ou mais por domicílio)', en: 'Residents in tracts among the 10% most crowded in the region ({threshold} or more per household)' },
  'ter.resp.tb': { pt: 'Tuberculose: casos confirmados por 100 mil habitantes, média anual 2022–2025', en: 'Tuberculosis: confirmed cases per 100,000 inhabitants, annual mean 2022–2025' },
  'ter.resp.tbHint': { pt: 'Casos contados pelo município onde a pessoa mora (SINAN/TBWEB), por ano de diagnóstico.', en: 'Cases counted by the municipality where the person lives (SINAN/TBWEB), by year of diagnosis.' },
  'ter.resp.tbDistrictHint': { pt: '{count} casos de residentes do distrito em 2022–2025 (TBWEB, SMS-SP, por ano de incidência). Pessoas sem residência fixa, cerca de 13% dos casos da cidade, não têm distrito e ficam fora destas duas taxas.', en: '{count} cases among district residents in 2022–2025 (TBWEB, SMS-SP, by year of incidence). People with no fixed residence, about 13% of the city\'s cases, have no district and are left out of both rates.' },
  'ter.access.title': { pt: 'Acesso à atenção básica pública', en: 'Access to public primary care' },
  'ter.access.bands': { pt: 'Moradores do raio por distância até a unidade básica pública mais próxima', en: 'Residents of the radius by distance to the nearest public primary care unit' },
  'ter.access.bandsHint': { pt: 'Estimativa. Distância em linha reta de cada endereço residencial (CNEFE 2022) até a UBS ou posto de saúde público mais próximo ({cnes}). Setores apenas parcialmente dentro do raio entram com todos os seus endereços.', en: 'Estimate. Straight-line distance from each residential address (CNEFE 2022) to the nearest public health centre or health post ({cnes}). Tracts only partly inside the radius count with all their addresses.' },
  'ter.access.upto500': { pt: 'Até 500 m', en: 'Up to 500 m' },
  'ter.access.upto1000': { pt: '500 m a 1 km', en: '500 m to 1 km' },
  'ter.access.upto2000': { pt: '1 a 2 km', en: '1 to 2 km' },
  'ter.access.over2000': { pt: 'Mais de 2 km', en: 'Over 2 km' },
  'ter.access.far': { pt: 'Moradores a mais de 1 km de uma unidade básica pública', en: 'Residents more than 1 km from a public primary care unit' },
  'ter.mat.title': { pt: 'Saúde materno-infantil', en: 'Maternal and child health' },
  'ter.mat.teen': { pt: 'Nascidos vivos de mães com menos de 20 anos', en: 'Live births to mothers under 20' },
  'ter.mat.preterm': { pt: 'Nascidos vivos prematuros (menos de 37 semanas)', en: 'Preterm live births (under 37 weeks)' },
  'ter.mat.districtHint': { pt: '{count} nascidos vivos de mães residentes no distrito. SINASC municipal (SMS-SP), 2022 a 2024 somados.', en: '{count} live births to mothers resident in the district. Municipal SINASC (SMS-SP), 2022 to 2024 pooled.' },
  'ter.mat.hint': { pt: '{count} nascidos vivos de mães residentes no município. SINASC, 2022 a 2024 somados.', en: '{count} live births to mothers resident in the municipality. SINASC, 2022 to 2024 pooled.' },
  'ter.mort.title': { pt: 'Mortalidade prematura (30 a 69 anos)', en: 'Premature mortality (ages 30 to 69)' },
  'ter.mort.causes': { pt: 'Participação de cada causa entre os óbitos com causa definida', en: 'Share of each cause among deaths with a defined cause' },
  'ter.mort.hint': { pt: '{count} óbitos de residentes de 30 a 69 anos com causa definida, de {total} no total, por capítulo da CID-10. SIM, 2022 a 2024 somados.', en: '{count} deaths of residents aged 30 to 69 with a defined cause, out of {total}, by ICD-10 chapter. SIM, 2022 to 2024 pooled.' },
  'ter.mort.districtHint': { pt: '{count} óbitos com causa definida de residentes de {name}, 30 a 69 anos. SIM municipal (SMS-SP/PRO-AIM), 2022 a 2024 somados. A prefeitura investiga óbitos de causa mal definida, por isso estes números não se comparam diretamente com os do DATASUS, abaixo.', en: '{count} deaths with a defined cause of {name} residents aged 30 to 69. Municipal SIM (SMS-SP/PRO-AIM), 2022 to 2024 pooled. The city investigates deaths with ill-defined causes, so these figures are not directly comparable with the DATASUS ones below.' },
  'ter.mort.illDefined': { pt: 'Óbitos sem causa definida (qualidade do registro)', en: 'Deaths without a defined cause (recording quality)' },
  'ter.mort.illDefinedHint': { pt: 'Capítulo XVIII da CID-10: sintomas e causas mal definidas. Quanto maior, menos se sabe do que de fato causou os óbitos. Ficam fora das participações acima, que supõem que esses óbitos se distribuem como os demais; essa correção ainda subestima um pouco as causas externas.', en: 'ICD-10 chapter XVIII: symptoms and ill-defined causes. The higher it is, the less is known about what actually caused the deaths. They are left out of the shares above, which assume these deaths are distributed like the rest; that correction still slightly understates external causes.' },
  'ter.mort.illDefinedFlag': { pt: 'Atenção: {share}% dos óbitos em {name} não têm causa definida. O perfil de causas deste município é pouco confiável.', en: 'Caution: {share}% of deaths in {name} have no defined cause. The cause profile for this municipality is unreliable.' },
  'ter.mort.cap.ix': { pt: 'Aparelho circulatório', en: 'Circulatory system' },
  'ter.mort.cap.ii': { pt: 'Neoplasias (câncer)', en: 'Neoplasms (cancer)' },
  'ter.mort.cap.x': { pt: 'Aparelho respiratório', en: 'Respiratory system' },
  'ter.mort.cap.xx': { pt: 'Causas externas (violência e acidentes)', en: 'External causes (violence and accidents)' },
  'ter.mort.cap.xi': { pt: 'Aparelho digestivo', en: 'Digestive system' },
  'ter.mort.cap.i': { pt: 'Doenças infecciosas e parasitárias', en: 'Infectious and parasitic diseases' },
  'ter.mort.other': { pt: 'Demais causas', en: 'Other causes' },
  'period.cnes': { pt: 'CNES, competência de agosto de 2026', en: 'CNES, reference month August 2026' },
  'period.sih': { pt: 'SIH/SUS, janeiro de 2025 a julho de 2026', en: 'SIH/SUS, January 2025 to July 2026' },
  'period.sihShort': { pt: 'jan/2025 a jul/2026', en: 'Jan 2025 to Jul 2026' },
  'period.cnesShort': { pt: 'ago/2026', en: 'Aug 2026' },
  'period.census': { pt: 'Censo Demográfico 2022', en: '2022 Demographic Census' },
  'figures.sources': { pt: 'Leitos e profissionais: {cnes}. Internações e permanência média: {sih}; os últimos seis meses estão sujeitos a atualização.', en: 'Beds and workforce: {cnes}. Admissions and mean stay: {sih}; the last six months are subject to update.' },
  'icu.hint': { pt: 'Leitos existentes e, deles, os disponíveis ao SUS. {cnes}.', en: 'Existing beds and, of those, the ones available to SUS. {cnes}.' },
  'sur.censusNote': { pt: 'Censo 2022', en: '2022 Census' },
  'sur.mapHint': { pt: 'Dados por setor censitário: {census}. Distância à atenção básica: endereços do CNEFE 2022 e unidades do {cnes}.', en: 'Data by census tract: {census}. Distance to primary care: CNEFE 2022 addresses and facilities from {cnes}.' },
  'ter.precariousHint': { pt: 'Fossa rudimentar ou buraco, vala, rio, lago, córrego ou mar, outra forma, ou sem banheiro. Não inclui fossa séptica.', en: 'Rudimentary pit or hole, ditch, river, lake, stream or sea, other form, or no bathroom. Septic tanks are not included.' },
  'ramp.under': { pt: 'menos de {value}', en: 'under {value}' },
  'ramp.range': { pt: '{low} a {high}', en: '{low} to {high}' },
  'ramp.over': { pt: '{value} ou mais', en: '{value} or more' },
  'ramp.noHouseholds': { pt: 'sem dados', en: 'no data' },
  'tract.name': { pt: 'Setor censitário {code}', en: 'Census tract {code}' },
  'tract.empty': { pt: 'Sem domicílios ocupados', en: 'No occupied households' },
  'tract.people': { pt: '{residents} moradores · {households} domicílios', en: '{residents} residents · {households} households' },
  'tract.share': { pt: '{share} da área está dentro do raio', en: '{share} of its area is inside the radius' },
};

/** Translated string for `key`, with `{name}` placeholders filled from `vars`. */
export function t(key, vars = {}) {
  const template = STRINGS[key]?.[lang] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? vars[name] : match));
}

/** Translate the static HTML of the page and wire up the language switch. */
export function applyStaticTranslations() {
  document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en';
  for (const node of document.querySelectorAll('[data-i18n]')) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll('[data-i18n-html]')) node.innerHTML = t(node.dataset.i18nHtml);
  for (const node of document.querySelectorAll('[data-i18n-placeholder]')) node.placeholder = t(node.dataset.i18nPlaceholder);
  for (const node of document.querySelectorAll('[data-i18n-aria]')) node.setAttribute('aria-label', t(node.dataset.i18nAria));
  for (const button of document.querySelectorAll('[data-lang]')) {
    const active = button.dataset.lang === lang;
    button.setAttribute('aria-pressed', String(active));
    if (!active) button.addEventListener('click', () => setLang(button.dataset.lang));
  }
}
