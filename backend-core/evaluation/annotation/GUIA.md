# Guia de anotação

Este guia acompanha a avaliação humana dos textos "Leitura do território", gerados automaticamente para a página de cada unidade de saúde. Os textos não foram todos gerados pelo mesmo método; o guia não diz qual é qual, para não influenciar a anotação. São 10 unidades sorteadas da amostra de avaliação (`../sample.csv`), 1 ou 2 por tipo de situação. Cada pessoa anota as 10 sozinha, sem conversar com as outras até todas terminarem.

Tempo estimado: de 3 a 4,5 minutos por unidade, até cerca de 45 minutos no total. Dá para parar e voltar: o progresso fica salvo no navegador.

## Como abrir

1. Abra `annotate.html` no navegador (Chrome, Firefox ou Edge) com dois cliques no arquivo. Não precisa de internet.
2. Digite um identificador curto (suas iniciais) e use sempre o mesmo. Ele define a ordem das unidades, que é diferente para cada pessoa, e a chave onde o progresso fica salvo.
3. Ao terminar, ou ao trocar de computador, clique em **Exportar anotações** e guarde o arquivo `anotacao_<identificador>.json`. Para continuar em outro computador, use **Importar**.

As anotações não guardam nome, e-mail nem dado pessoal, só o identificador.

## Etapa 1 · Erros e relevância

Cada frase do texto vem com um quadro **Dados para conferir**, com os dados que ela usa. Esses dados foram recalculados a partir dos dados brutos, separados do sistema que escreveu o texto. Acima das frases, **Todos os dados desta unidade** reúne os dados de todas elas; use quando o quadro de uma frase estiver vazio ou não tiver o dado que ela cita.

- Se a frase bate com o quadro, marque **Conferida: sem erros**.
- Se não bate, abra **Registrar um erro nesta frase**, copie o trecho errado, escolha a categoria e escreva a correção. Uma frase pode ter mais de um erro; registre cada um separadamente.

Diferença de arredondamento não é erro: "cerca de 32.000" para 31.970 está certo, assim como "entre os 6%" para "maior que em 94,3%".

Em cada frase, escolha também uma das duas opções. A escolha é obrigatória e não depende de a frase ter erro.

- **Relevante:** quem lê a página perderia algo se a frase saísse do texto.
- **Poderia sair do texto:** a frase não acrescenta ao que o texto já disse, ou o dado pode ficar só nos cartões da página.

Pense em alguém da comunidade, da educação ou da gestão que quer entender o território em volta da unidade. Os avisos (por exemplo, "Não há dados de doença para áreas do tamanho do raio…") também são julgados: diga se o aviso ajuda quem lê ou se poderia sair.

| Categoria | Quando usar | Exemplo |
|---|---|---|
| NUMERO | O número não bate com o quadro | "90,6% sem rede de esgoto", quando o quadro diz 9,6% |
| ESCALA | O número existe, mas é de outra escala | O valor do município apresentado como do raio |
| NOME | Lugar, ano ou intervalo de anos errado | "entre 2022 e 2025" para dados de 2022 a 2024 |
| PALAVRA | Comparativo, direção ou termo que não corresponde aos dados | "acima de" quando o valor é menor |
| CONTEXTO | Correto, mas enganoso: falta um aviso, ou um aviso não faz sentido | Uma taxa calculada sobre pouquíssimos casos sem aviso nenhum |
| NAO_VERIFICAVEL | O quadro não traz o dado para conferir a afirmação | |
| OUTRO | Erro que não cabe acima (gramática não conta) | |

As categorias seguem Thomson & Reiter (2020), com a categoria ESCALA acrescentada para este trabalho.

Algumas frases são **avisos**, não dados: por exemplo, "Não há dados de doença para áreas do tamanho do raio: os números a seguir são do distrito". Elas vêm com um quadro azul **O que conferir nesta frase**. Num aviso, o que se confere é se ele vale para a unidade (no exemplo, se os números seguintes são mesmo do distrito), e não os valores do quadro de dados. Se o aviso não vale ou é enganoso, registre como CONTEXTO.

## Etapa 2 · O que ficou de fora

Depois das frases aparece uma lista de até 6 informações, cada uma com seus números, que o sistema calculou para a unidade mas não pôs no texto. Marque as que deveriam estar no texto, pensando no mesmo leitor; ou marque **Nenhuma**, se o texto não deixou de fora nada importante. Repare na escala de cada informação, indicada numa etiqueta ao lado do título: dados do município ou do distrito descrevem uma área bem maior que o entorno da unidade (a dengue "no município de São Paulo" é da cidade inteira, não do bairro). Uma das duas respostas é obrigatória para concluir a unidade.

## Dúvidas frequentes

- **O texto deixou de fora algo que eu acho importante.** Isso não é erro na etapa 1, a menos que deixe uma frase enganosa (CONTEXTO). Se a informação estiver na lista da etapa 2, marque-a lá.
- **Uma frase é relevante, mas tem erro.** As duas coisas são independentes: registre o erro e marque "Relevante".
- **Posso voltar a uma unidade?** Sim, pelos botões Anterior e Próxima. As duas etapas podem ser revistas até você concluir a unidade.
