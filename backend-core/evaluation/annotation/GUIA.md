# Guia de anotação

Este guia acompanha a avaliação humana dos textos "Leitura do território", gerados automaticamente para a página de cada unidade de saúde. São 40 unidades sorteadas por estrato (`../sample.csv`). Cada pessoa anota as 40 sozinha, sem conversar com a outra anotadora até terminar.

Tempo estimado: de 6 a 9 minutos por unidade, cerca de 5 horas no total. Dá para parar e voltar: o progresso fica salvo no navegador.

## Como abrir

1. Abra `annotate.html` no navegador (Chrome, Firefox ou Edge), com dois cliques no arquivo. Não precisa de internet.
2. Digite um identificador curto (suas iniciais) e use sempre o mesmo. Ele define a ordem das unidades, que é diferente para cada anotadora, e a chave onde o progresso fica salvo.
3. Ao terminar, ou ao trocar de computador, clique em **Exportar anotações** e guarde o arquivo `anotacao_<identificador>.json`. Para continuar em outro computador, use **Importar**.

Não há nome, e-mail nem dado pessoal nas anotações, só o identificador.

## O que fazer em cada unidade

À esquerda fica a **ficha de dados** da unidade: cadastro, entorno de 1 km, comparação com unidades parecidas e, para UBS públicas, a área de atendimento estimada; dados do distrito (na capital) e do município. Tudo o que você precisa julgar está nela. Os números da ficha foram recalculados a partir dos dados brutos, de forma independente do sistema que escreve os textos.

As etapas 1 e 2 são feitas **antes de ver o texto**. O texto só aparece depois de confirmar as duas, e as respostas delas ficam travadas.

### Etapa 1 · Ressalvas

Para cada uma das 15 ressalvas, responda **Sim** ou **Não**: um texto cuidadoso sobre esta unidade, que citasse os números da ficha, precisaria fazer essa ressalva?

- Julgue pelos dados, não pelo que você acha que o texto vai dizer.
- "Sim" quando o dado da ficha torna a ressalva necessária para que um leitor não tire uma conclusão errada; "Não" quando ela seria irrelevante ou sem base nos dados.
- Não existe limiar oficial: use o seu julgamento. Se ficar em dúvida, escreva no comentário o que pesou.

Exemplos:

| Ressalva | Na ficha | Resposta provável |
|---|---|---|
| Ano de epidemia de dengue | 2024 com taxa muito maior que 2022, 2023 e 2025 | Sim |
| Muitos óbitos sem causa definida | 4,7% sem causa definida | Não |
| Muitos óbitos sem causa definida | 26,3% sem causa definida | Sim |
| Estimativa do raio imprecisa | 6 setores, 30% da população deles dentro do raio | Sim |

### Etapa 2 · O que é mais importante

Escolha **de 3 a 5** afirmações, entre as listadas, que um leitor da página desta unidade mais precisaria saber. Pense em alguém da comunidade, da educação ou da gestão que quer entender o território em volta da unidade. A ordem das afirmações é aleatória.

### Etapa 3 · Erros no texto

Leia o texto frase por frase e confira cada uma contra a ficha.

- Se a frase estiver correta, marque **Conferida, sem erros**.
- Se tiver um erro, copie o trecho errado, escolha a categoria, escreva a correção e clique em **Adicionar erro**. Uma frase pode ter mais de um erro; registre cada um separadamente.

Diferenças de arredondamento não são erro: "cerca de 1.700" para 1.655 está certo; "17,4%" para 17,36% também.

| Categoria | Quando usar | Exemplo |
|---|---|---|
| NUMERO | O número não bate com a ficha | "90,6% sem rede de esgoto", quando a ficha diz 9,6% |
| ESCALA | O número é verdadeiro, mas de outra escala | Taxa do município apresentada como do raio ou do distrito |
| NOME | Lugar, ano ou intervalo de anos errado | "entre 2022 e 2025" para dados de 2022 a 2024 |
| PALAVRA | Comparativo, direção ou termo que não corresponde aos dados | "acima de" quando o valor é menor; "dentro da faixa" fora dela |
| CONTEXTO | Correto, mas enganoso sem uma ressalva ou contexto que falta | Comparar contagens pequenas como se fossem taxas estáveis |
| NAO_VERIFICAVEL | Não dá para conferir com a ficha | Uma afirmação sem dado correspondente |
| OUTRO | Erro que não cabe acima (gramática não conta) | |

As categorias seguem Thomson & Reiter (2020), com a categoria ESCALA acrescentada para este trabalho.

## Dúvidas frequentes

- **Uma ressalva aparece no texto mas eu disse "Não" na etapa 1.** Tudo bem: as etapas medem coisas diferentes. Se ela for enganosa ou desnecessária, você pode registrar como CONTEXTO na etapa 3.
- **O texto omite algo que eu acho importante.** Omissão não é erro na etapa 3, a menos que torne uma frase enganosa (CONTEXTO). A etapa 2 já mede o que você considera importante.
- **Posso voltar a uma unidade?** Sim, pelos botões Anterior e Próxima. As etapas 1 e 2 ficam travadas depois de confirmadas; a etapa 3 pode ser revista até você concluir a unidade.
