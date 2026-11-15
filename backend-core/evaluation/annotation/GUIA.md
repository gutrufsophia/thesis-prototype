# Guia de anotação

Este guia acompanha a avaliação humana dos textos "Leitura do território", gerados automaticamente para a página de cada unidade de saúde. São 20 unidades sorteadas da amostra de avaliação (`../sample.csv`), de 2 a 3 por tipo de situação. Cada pessoa anota as 20 sozinha, sem conversar com a outra até as duas terminarem.

Tempo estimado: de 4 a 6 minutos por unidade, perto de 1h30 no total. Dá para parar e voltar: o progresso fica salvo no navegador.

## Como abrir

1. Abra `annotate.html` no navegador (Chrome, Firefox ou Edge) com dois cliques no arquivo. Não precisa de internet.
2. Digite um identificador curto (suas iniciais) e use sempre o mesmo. Ele define a ordem das unidades, que é diferente para cada pessoa, e a chave onde o progresso fica salvo.
3. Ao terminar, ou ao trocar de computador, clique em **Exportar anotações** e guarde o arquivo `anotacao_<identificador>.json`. Para continuar em outro computador, use **Importar**.

As anotações não guardam nome, e-mail nem dado pessoal, só o identificador.

## Etapa 1 · O que é mais importante

Aparecem 10 informações sobre a unidade, cada uma com seus números. Escolha **as 3** que um leitor da página mais precisaria saber. Pense em alguém da comunidade, da educação ou da gestão que quer entender o território em volta da unidade.

O texto ainda não aparece nesta etapa, para que a escolha seja só sua. Ao clicar em **Confirmar e ver o texto**, a escolha fica travada.

## Etapa 2 · Erros no texto

Cada frase do texto vem com um quadro **Dados para conferir**, com os dados que ela usa. Esses dados foram recalculados a partir dos dados brutos, separados do sistema que escreveu o texto.

- Se a frase bate com o quadro, marque **Conferida: sem erros**.
- Se não bate, abra **Registrar um erro nesta frase**, copie o trecho errado, escolha a categoria e escreva a correção. Uma frase pode ter mais de um erro; registre cada um separadamente.

Diferença de arredondamento não é erro: "cerca de 32.000" para 31.970 está certo, assim como "entre os 6%" para "maior que em 94,3%".

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

## Dúvidas frequentes

- **O texto deixou de fora algo que eu acho importante.** Isso não é erro na etapa 2, a menos que deixe uma frase enganosa (CONTEXTO). A etapa 1 já mede o que você considera importante.
- **Posso voltar a uma unidade?** Sim, pelos botões Anterior e Próxima. A etapa 1 fica travada depois de confirmada; a etapa 2 pode ser revista até você concluir a unidade.
