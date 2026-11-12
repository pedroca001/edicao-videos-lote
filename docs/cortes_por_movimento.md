> Escopo deste documento: receita Vids de 40 s, quatro cenas de 10 s. Para Flow de 32 s e hooks de 4 s, veja [operação](operacao.md) e [hooks de 4 s](hooks_4s.md). As janelas Vids não são cortes fixos nem se transferem automaticamente para Flow.

# Como encurtar os videos de receita do Google Vids preservando os movimentos

## 1. Estrutura da fonte que voce vai editar

Os MP4s finais do gerador têm 40 segundos, com quatro etapas consecutivas de aproximadamente dez segundos. A camera e o ambiente permanecem os mesmos, em uma receita vista em primeira pessoa.

| Tempo na fonte final | Etapa | Acao esperada | Repouso que vale procurar |
|---|---|---|---|
| 0 a 10s | 1: imagem animada | Mexer a mistura amarela com fouet; parar, repousar o fouet e soltar a mao | Principalmente o encerramento, perto de 8 a 10s |
| 10 a 20s | 2: primeira extensao | Pegar bicarbonato, despejar, devolver embalagem e soltar | Antes de pegar, se existir espera; depois de devolver e soltar |
| 20 a 30s | 3: segunda extensao | Pegar mel, adicionar, devolver; pegar metade de limao, espremer e devolver | Antes de iniciar ou depois de concluir as duas adicoes |
| 30 a 40s | 4: terceira extensao | Mexer novamente, parar, pegar a tigela com as duas maos e apresentar | Pausa entre mexer e pegar; sustentacao final com tigela ja posicionada |

Essa ordem vem do preset atual do Vids. Os modelos podem deslocar o inicio/fim de uma acao ou executar o gesto de outra forma. O perfil automatico usa os horarios como limites de busca e medidas locais para escolher pontos. Isso nao confirma semanticamente cada gesto; a amostra visual e as excecoes tratam a incerteza.

O gerador baixa resultados brutos de 10/20/20/20 segundos. A montagem de origem usa o resultado 2 inteiro, seguido somente dos dez segundos novos dos resultados 3 e 4: **20 + 10 + 10 = 40s**. As partes repetidas dos dois ultimos resultados ja foram retiradas. O editor recebe esse MP4 pronto e NAO deve retirar novamente os primeiros dez segundos das etapas 3 e 4.

## 2. Regra principal de corte

**Conserve os movimentos uteis completos e retire o excesso de espera entre eles.**

Os tres pontos prioritarios para buscar tempo removivel sao as emendas da fonte em **10s, 20s e 30s**. Comece procurando nos intervalos **8 a 12s, 18 a 22s e 28 a 32s**. Essas janelas sao regioes de busca, nao autorizacao para apagar quatro segundos automaticamente.

Procure o instante em que a acao anterior terminou e a proxima ainda nao comecou. Um bom intervalo tem maos/fouet praticamente parados, objetos apoiados e estado da receita consistente antes e depois da retirada. Ele pode ficar antes da emenda, depois dela ou atravessar a emenda.

Uma emenda entre etapas nao garante repouso. Se a mao ja estiver alcancando um produto, ou se o mel estiver caindo, proteja esse trecho mesmo que esteja exatamente em 20s. Se nao houver pausa numa emenda, use outra regiao com repouso real.

## 3. O que preservar

Trate como intervalos protegidos:

- Mao alcancando, segurando, levantando e reposicionando um ingrediente. Evitar produto aparecer magicamente na mao ou voltar sozinho para a mesa.
- Despejo do bicarbonato e o momento em que o po entra na tigela.
- Mel saindo do bico e entrando na mistura. O fio pode ser fino e lento: pouco movimento numerico nao significa pausa.
- Espremida do limao e retorno dele ao apoio.
- Pegada do fouet, parte util da mistura, parada e soltura.
- Pegada da tigela, levantamento e chegada a pose de apresentacao.
- Uma apresentacao final reconhecivel, normalmente preservando pelo menos aproximadamente 1 a 2 segundos quando a duracao permitir.

Nao cortar uma mao no meio do trajeto somente porque esse trecho fica entre duas amostras com pouco movimento. Nao remover uma acao inteira porque as poses de inicio e fim parecem semelhantes: por exemplo, o frasco pode sair da mesa, despejar mel e voltar ao mesmo lugar.

Se o roteiro falado mencionar explicitamente um ingrediente, manter a sua acao visivel e numa ordem compativel com a fala. Nao e necessario sincronizar toda palavra com todo gesto quando a narracao for generica, mas a reducao nao deve inverter a receita.

## 4. Ordem de preferencia para ganhar tempo

1. Pausas reais junto de 10s, 20s e 30s, apos concluir uma acao e antes da proxima.
2. Outras esperas reais dentro das etapas, como produto ja devolvido e mao parada, ou fouet repousado antes de pegar a tigela.
3. Excesso da pose inicial e da sustentacao final, conservando a leitura do inicio e o encerramento util.
4. Se as pausas nao bastarem, reduzir repeticao de uma acao longa e ciclica, como mexer, escolhendo poses compativeis; conservar o inicio e o fim reconheciveis.
5. Como alternativa para preservar uma acao continua, acelerar levemente um trecho visual selecionado. Recalcular sua duracao e conferir o resultado. Nao aplicar aceleracao uniforme como primeira resposta a uma voz curta.
6. Cortar durante uma acao importante apenas como ultimo recurso. Preferir uma emenda de menor mudanca entre as poses e registrar a excecao.

O numero de segmentos deve resultar dos intervalos escolhidos. Nao forcar sete segmentos, intervalos igualmente espacados ou a mesma distribuicao percentual de cortes em todos os videos.

## 5. Como localizar os intervalos no editor

Calcule primeiro:

```text
tempo_a_remover = duracao_visual_original - duracao_da_narracao_final
```

Para uma fonte de 40s e narracao de 35s, sao cinco segundos. Para uma narracao de 30s, sao dez. Isso nao significa que existam cinco ou dez segundos de repouso disponiveis.

Analise a fonte antes de colocar legendas, zooms ou transicoes. Esses elementos podem contaminar a medida de movimento.

### Analise visual e de movimento

- Meça mudanca temporal principalmente nas regioes das maos, fouet, tigela e produtos. Movimento de pessoas, carros, telas ou luzes no fundo nao deve sozinho impedir um corte num primeiro plano em repouso.
- Use uma estimativa local de movimento, por exemplo fluxo optico ou diferenca de quadros com tratamento de variacao de iluminacao. O tamanho/resolucao da amostra e o limiar devem ser calibrados; nao existe um numero universal que sirva para todas as fontes.
- Como ponto de partida de engenharia, amostrar cerca de 5 a 8 quadros por segundo para encontrar candidatos. Nas bordas escolhidas, conferir mais densamente ou frame a frame. Isso e sugestao de implementacao, nao parametro ja validado.
- Busque repouso sustentado por aproximadamente 0,4 a 0,8 segundo, ajustando quando necessario. Um unico par de frames parecidos nao basta.
- Na amostra e na revisao de excecoes, confira o significado da acao: a mao pode parar enquanto segura produto sobre a tigela. O automatico restringe pausas internas nas etapas de adicao e mantem confianca heuristica, sem afirmar reconhecimento de objetos.
- O programa compara poses imediatamente antes/depois de cada retirada e recorrencia no interior das mexidas. Inspecione visualmente esses pontos somente na amostra e nas excecoes tratadas. As maos devem saltar pouco, os produtos continuar no mesmo estado e nenhuma adicao essencial desaparecer.

Movimento e recorrencia sustentam decisoes automaticas heuristicas. Nao representam aprovacao semantica. Preservar essa distincao nos metadados (`visual_reviewed: false`). Casos sem plano dentro das regras viram excecoes listadas; nao chamar Codex ou abrir navegador automaticamente. Os demais continuam, mantendo a atribuicao de audios/estilos.

### Escolha e orcamento de cortes

Cada candidato deve registrar inicio/fim na fonte, quantidade de frames removiveis, regiao, acao, motivo e confianca da verificacao. Ordenar primeiro por preservacao das acoes e continuidade, depois por proximidade das emendas. Penalizar saltos de mao/produto e fragmentacao excessiva.

Pode encurtar uma pausa parcialmente: nao e necessario retirar toda a regiao detectada. Deixar uma pequena margem de repouso junto ao fim da acao e ao inicio da seguinte ajuda a manter naturalidade. A margem deve ser ajustada ao video, nao subtraida cegamente.

Se a soma das pausas boas for insuficiente, informar quantos segundos faltam e aplicar a ordem de alternativas da secao 4. Nunca apresentar uma janela como pausa apenas para fechar a conta da duracao.

## 6. Exemplo hipotetico: 40s para 35s

Suponha que a inspecao de UM video confirme repouso e continuidade nestes intervalos:

| Retirada na fonte | Duracao removida | Justificativa hipotetica |
|---|---|---|
| 8,75 a 10,50s | 1,75s | Fouet ja repousado; a mao ainda nao comecou a pegar bicarbonato |
| 18,75 a 20,50s | 1,75s | Bicarbonato ja devolvido; mel ainda nao esta sendo pego |
| 28,50 a 30,00s | 1,50s | Mel e limao ja devolvidos; proxima mexida ainda nao iniciou |
| Total | 5,00s | Fonte de 40s passa a 35s |

Os intervalos preservados, na ordem original, seriam:

```text
[0,00; 8,75) + [10,50; 18,75) + [20,50; 28,50) + [30,00; 40,00)
```

A 24fps, num arquivo realmente normalizado a esse FPS e com 960 frames, isso corresponde a:

```json
{
  "fps": 24,
  "source_frames": 960,
  "target_frames": 840,
  "keep_intervals": [
    {"start_frame": 0, "end_frame": 210},
    {"start_frame": 252, "end_frame": 450},
    {"start_frame": 492, "end_frame": 684},
    {"start_frame": 720, "end_frame": 960}
  ],
  "transitions": "hard_cut_after_endpoint_review",
  "example_only": true
}
```

Inicio inclusivo, fim exclusivo. A soma e 840 frames = 35s. Os pontos sao apenas um exemplo matematico. Se o bicarbonato comecar a ser pego em 10,1s no arquivo real, essa primeira retirada invade a acao e deve ser alterada.

## 7. Quando o audio e muito menor

Os audios dos lotes anteriores chegaram a aproximadamente 23,75s, 30,58s e 27,33s. Reduzir 40s para essas duracoes exige retirar cerca de 16,25s, 9,42s e 12,67s, respectivamente. As tres emendas podem nao conter todo esse tempo de espera.

Nesses casos, encontre primeiro todas as pausas reais. Depois preserve pelo menos uma leitura clara das quatro acoes, reduzindo mexidas repetitivas quando houver uma emenda natural, ou acelerando moderadamente trechos apropriados. Não eliminar despejos, espremidas e a apresentacao final para manter um padrao fixo de cortes.

Preservar somente repouso na fonte pode impedir atingir o alvo. O editor deve expor essa limitacao e escolher a menor alteracao necessaria, em vez de cortar movimentos silenciosamente. Cada fonte precisa de seu proprio plano, mesmo quando varias usam a mesma narracao.

## 8. Aplicacao no FFmpeg

O FFmpeg executa os intervalos escolhidos. A escolha depende da analise anterior.

- Trabalhar por frames quando a fonte estiver em FPS constante conhecido. Se ela for variavel, planejar por timestamps ou normalizar primeiro e manter o mapeamento; nao multiplicar segundos por um FPS presumido.
- Para cada intervalo preservado, usar `trim` e zerar os timestamps com `setpts=PTS-STARTPTS`.
- Concatenar os intervalos na ordem original com `concat`.
- Colocar as legendas depois da nova timeline visual estar formada. Seus tempos continuam ligados a narracao final.
- Se o som original da receita for substituido pela narracao, remover/cortar apenas o visual e usar a narracao continua. Nao aplicar nela os cortes visuais. Se houver som ambiente mantido, esse som deve acompanhar os respectivos segmentos visuais, separado da voz.
- Reencodar para materializar cortes precisos. Copia direta do stream com `-c:v copy` e busca por keyframe nao deve ser assumida como corte preciso no frame escolhido.
- Validar a duracao final com tolerancia de um frame e conferir decodificacao e emendas. Arredondar a timeline uma vez pelo total; distribuir eventual ajuste de um frame numa pausa, nao numa palavra da voz.

Documentacao oficial dos filtros: [trim](https://ffmpeg.org/ffmpeg-filters.html#trim), [setpts](https://ffmpeg.org/ffmpeg-filters.html#setpts_002c-asetpts), [concat](https://ffmpeg.org/ffmpeg-filters.html#concat).

### Transicoes

Preferir corte seco entre poses de repouso compativeis. Nao colocar transicao em toda emenda automaticamente. Crossfade pode mostrar maos/fouets duplicados e esconder a escolha ruim do intervalo.

Se uma emenda realmente precisar de transicao, usar uma curta e revisar a imagem. A sobreposicao encurta a timeline:

```text
duracao_final = soma(duracoes_preservadas_apos_ajuste_de_velocidade)
               - soma(duracoes_das_sobreposicoes)
```

Tres crossfades de 0,15s retiram mais 0,45s. O plano precisa compensar esse tempo; nao calcular 35s de segmentos e depois descobrir que a saida tem 34,55s. Referencia: [xfade](https://ffmpeg.org/ffmpeg-filters.html#xfade).

## 9. Verificacao e custo em escala

O programa verifica tecnicamente todos os arquivos: decode completo, contagem exata de frames, duracao, hash da voz AAC e copia SHA256. A revisao visual fica limitada a ate tres saidas sugeridas por lote, com narracoes/estilos diferentes quando possivel e prioridade aos planos de maior risco numerico. Inspecionar emendas e apresentacao nessa amostra; registrar se foi por quadros ou em velocidade normal. A amostra nao comprova todos os gestos do lote.

Quando mudar o algoritmo ou perfil, renderizar primeiro tres exemplos. Para lotes do mesmo perfil, nao repetir um processo de desenvolvimento nem montar manualmente 58 timelines. Excecoes devem ser agrupadas por causa/deficit, sem ampliar silenciosamente o consumo do Codex. A via manual continua disponivel quando necessaria para a entrega solicitada.

Analise, planejamento, transcricao e render locais nao usam tokens de LLM. Conversa, programacao e imagens inspecionadas pelo Codex usam o Codex. Medir tempo de planejamento separado de transcricao/render. Nao atribuir o tempo de desenvolvimento ao custo recorrente de cada lote.

## 10. Contrato do planejador automático

- `auto_planner.py` e o caminho padrao. `motion_planner.py` compartilha deteccao de repouso e alocador de frames com a via manual. `cut_review.py` e opcional.
- Perfil `vids_receita`: fonte de 39-41s, repouso sustentado com bordas proximas, prioridade nas emendas. Pausas internas nas etapas de adicao ficam protegidas fora das regioes de emenda.
- Recorrencia numerica somente dentro das mexidas previstas em 1-9s e 30,75-35,5s; pode localizar subintervalos menores. Pontos finais escolhidos por poses, sem afirmar que o modelo reconheceu fouet/ingrediente. Primeiro segundo e ultimos 1,5s protegidos.
- Depois de pausas e repeticoes, acelerar seletivamente trechos continuos ate 1,20x. Sem excecao automatica que remova uma acao importante. Sem deficit: renderizar; com deficit: listar e seguir os demais.
- `--profile conservative` para fontes sem a estrutura conhecida: pausas e velocidade, sem presumir etapas de mexida.
- `--review-mode auto --no-ui --sample-size 3` e o fluxo normal. `--review-exceptions` sem `--no-ui` abre somente pendencias; `--review-mode manual` habilita a revisao individual deliberada. JSON manual vinculado por fonte/plano continua aceito. CLI retorna 2 em lote parcial.
- `--plan-only` permite medir viabilidade sem renderizar. Planos/analises/ASS/transcricoes sao efemeros; somente MP4s finais ficam na entrega.

## 11. Montagem resumida opt-in

O perfil `vids_receita_resumida` permite elipses dentro dos gestos somente com autorização aplicável ao lote, preservando início, etapas e resultado. Não substitui o padrão de repouso/gestos completos. Usa cinco trechos ordenados, início de pelo menos 2 s, final de pelo menos 4,5 s e voz/visual 1x. As janelas e o movimento são heurísticos, sem reconhecimento de objetos. Omissões ficam registradas como `exception`, `verified: false`, sem aprovação visual individual.

Para quatro cenas Flow de 8 s ou cenas diferentes, consultar os limites dos perfis em [operação](operacao.md). Não aplicar as janelas Vids de 10 s a fontes Flow. Alongamento visual explícito depende da escolha do lote, usa `authorized_slowdown=true` e preserva voz inteira. O assistente conservador não ganha alongamento implícito.
