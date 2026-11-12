# Hook de 4 segundos com receita desde o início

Contrato usado nos últimos lotes Teste Hooks: uma abertura exclusiva de 4 s por receita de 32 s, quatro cenas de 8 s. Voz externa inteira, estilo fixo por vídeo, corte seco e sem zoom. O corpo é resumido conforme a autorização do lote, com visual 1x quando couber.

**Não existe perfil CLI de 4 s nesta versão.** `hook_recipe_plan` aceita uma fonte virtual de cerca de 38 s (6 s de hook + 32 s de receita). Seus únicos modos diretos são 6 s/corpo desde o início e 3 s/corpo adiantado 2 s. A adaptação abaixo usa a função existente, sem mudar seus defaults.

## Normalizar primeiro

Usar 720x1280, 24 fps constantes. Contar os quadros decodificados; medir a fronteira real do corpo. Não confiar apenas no remux H.264, que pode inserir quadro extra na junção. Se necessário, compor em formato sem perda (por exemplo FFV1) no scratch e conferir o primeiro frame do corpo por pixels contra o original normalizado.

Preparar a voz uma vez; usar sua duração normalizada e `N = ceil(duracao_da_voz * 24)` como total final. Um hook de 4 s deve ter exatamente 96 frames. Todas as fronteiras são início inclusivo/fim exclusivo.

## A. Hook separado de 8 s + corpo de 32 s

1. Normalizar e compor no scratch: 192 frames de hook + 768 de corpo = 960.
2. Criar somente para análise a sequência virtual `frames[0:144] + frames[192:960]`. São 912 frames: hook virtual de 6 s + corpo inteiro.
3. Chamar `hook_recipe_plan(virtual, N + 48, source_sha256=SHA, hook_seconds=6, recipe_advance_seconds=0)`.
4. No plano retornado, reduzir o primeiro clipe de `[0,144)` para `[0,96)`. Isso retira exatamente 48 frames, ficando N no total.
5. Para renderizar sobre a composição original de 960 frames, somar 48 aos limites `start_frame` e `end_frame` de todos os clipes do corpo. O primeiro trecho do corpo passa de 144 para 192, exatamente o começo da receita original.
6. Atualizar os campos de auditoria: total final N, hook de 4 s, avanço da receita 0, hash da composição efetivamente renderizada e referências/SHA separados de hook/corpo. Não reutilizar metadados de fonte virtual como se descrevessem a fonte real.

Pseudocódigo do mapeamento, não um executor completo:

```python
from condensed_planner import hook_recipe_plan
from edit_batch import timeline_frames

virtual = concatenate([frames[:144], frames[192:960]])
_, plan = hook_recipe_plan(virtual, N + 48, source_sha256=joined_sha,
                          hook_seconds=6, recipe_advance_seconds=0)
clips = plan['clips']
clips[0]['end_frame'] = 96
for clip in clips[1:]:
    clip['start_frame'] += 48
    clip['end_frame'] += 48
assert clips[1]['start_frame'] == 192
assert timeline_frames(clips) == N
```

`frames`, `concatenate`, N e os hashes são fornecidos pelo operador/helper do lote. Este trecho não normaliza mídia, prepara voz, cria jobs ou valida a entrega. Não copiá-lo como um comando pronto.

## B. Filme já unido de 38 s: hook de 6 s + corpo de 32 s

Conferir a fronteira real. Na composição normalizada de 912 frames, hook `[0,144)`, receita `[144,912)`. Chamar o mesmo planejador com N+48, abertura 6 s e avanço 0; reduzir apenas o clipe inicial a 96 frames. **Não somar 48 aos clipes do corpo neste caso.** O primeiro clipe do corpo começa em 144 na fonte e aparece no frame 96 da saída.

## C. Filme já unido de 40 s: hook de 8 s + corpo de 32 s

Se a fronteira medida for 192, usar a sequência virtual e o mapeamento +48 do caso A. Não aplicar a política Vids de quatro cenas de 10 s e não passar todos os 960 frames direto ao planejador de 38 s.

## Guardas antes de liberar o lote

- Aplicar a adaptação somente a essa estrutura confirmada, com autorização para resumir quando necessário. Outras estruturas são exceções.
- Fonte e voz originais permanecem intactas. Não inventar quadros ausentes no meio da receita. Pequeno ajuste de cauda só se medido, permitido e registrado; não assumir que qualquer arquivo tem exatamente 768 frames de corpo.
- O mapeamento acima é o caminho 1x usado nos lotes anteriores. Se N+48 não couber nos limites do planejador, expor déficit e obter/reusar a escolha concreta de alongamento. Não acrescentar slowdown/repetição silenciosamente ao pseudocódigo.
- Conferir 96 frames de abertura, corpo desde o primeiro frame e timeline de N frames. Inspecionar pilotos aproximadamente em 3,95/4,05 s, incluindo os quadros adjacentes reais à fronteira.
- Comparar por pixels o primeiro frame normalizado do corpo antes das legendas. Conferir visualmente também a saída com legendas. Assinar a composição por SHA e guardar os SHA dos originais na atribuição.
- Preparar até três pilotos com vozes/estilos diferentes, rever antes do restante, depois decode completo/frames/AAC/SHA de todos.

## Execução de planos

O editor aceita jobs explícitos com `id`, `source`, `style`, `clips`. Depois da normalização/mapeamento e validação, agrupar jobs pela voz e executar `run_pipeline.py`, que transcreve cada voz uma vez e chama `edit_batch.py`:

```sh
python -B run_pipeline.py \
  --task "/caminho/voz_normalizada.m4a" "/scratch/plano_da_voz.json" \
  --output "/caminho/nova_entrega" \
  --ffmpeg "/caminho/ffmpeg" \
  --model "/caminho/modelo_local" \
  --backend mlx --encoder h264_videotoolbox --workers 2
```

Resolver Python/FFmpeg/modelo pelo runtime instalado. Windows usa `faster_whisper`/`h264_nvenc`. Repetir `--task AUDIO PLANO` por voz, sem repetir a mesma voz em vários tasks. Os planos/composições externos ao scratch interno do pipeline também devem ser removidos pelo helper chamador ao terminar.

O plano JSON é uma lista de jobs, não o relatório de análise inteiro. Cada `source` precisa apontar para a composição normalizada real usada no mapeamento, viva até o fim do render. A integração por `run_job` pode ser usada por um helper para separar os três pilotos e reutilizar a transcrição, mantendo todas as verificações existentes.
