---
name: edicao_videos_lote
description: Edita receitas Vids/Flow em lote com vozes prontas, hooks de abertura, cortes por movimento e duas legendas. Use para inventariar inéditos, atribuir pares exclusivos, editar localmente e preparar inclusão no pool sem repetir origens.
---

# Edição local de vídeos em lote

## Localizar o editor

Resolver o checkout deste repositório, ler `AGENTS.md`, `docs/operacao.md` e o guia da plataforma. Este SKILL está em `skills/edicao_videos_lote`; a raiz do checkout fica dois níveis acima. Se instalada fora daqui, localizar o checkout antes de executar.

Fonte canônica original: `<BRAIN_ROOT>/Skills/edicao_videos_lote/SKILL.md`; algoritmo original: `<CODIGO_ROOT>/local_video_editor`. Esta exportação portátil inclui um snapshot dos módulos e não depende do Brain para a operação documentada.

## Padrão

Processamento automático local, transcrição uma vez por voz, dois workers e inspeção visual de até três amostras. Não analisar vídeo a vídeo com LLM. Zero API paga no pipeline. Manter voz externa inteira e som original da receita removido.

Somente impacto_amarelo/0 e duas_linhas_lima/2, equilibrados, um estilo por vídeo. Cápsula menta/1 removida, sem reindexar os IDs.

## Fluxo

1. Confirmar acesso e fontes completas, ignorar `._*`/intermediários, ordenar naturalmente e deduplicar por SHA. Se editar só inéditos, reconciliar histórico/recibos/pool de ED e WL. Ausência de job/final não comprova ineditismo. Informar a contagem antes do render.
2. Identificar estrutura real: Vids40 sem hook; Flow32 sem hook; hook6+receita32; hook8+receita32, separados ou unidos. Duração sozinha não identifica a estrutura.
3. Congelar atribuições por fonte/hook/voz/estilo/SHA/destino em manifesto externo. Quantidades conforme pedido, divisão equilibrada das sobras, seed registrada. Um hook por receita sem repetição quando solicitado. Não substituir pares por matriz.
4. Resolver runtime/config da máquina. Mac M1+ usa instalador MLX/VideoToolbox; Windows requer CUDA/NVENC e modelo local existentes. Não distribuir configuração pessoal.
5. Escolher rota: fontes sem hook usam `batch_assistant.py`/`run_pipeline.py`. Vids40 usa `vids_receita`; outras estruturas começam em `conservative`. Resumo dentro dos gestos e alongamento exigem autorização aplicável ao lote.
6. Para Teste Hooks atual, **4 s de hook e receita desde o frame zero**: seguir `docs/hooks_4s.md`, por plano explícito. Planejar virtualmente hook6+receita32 com alvo N+48 frames e reduzir hook144 para96; mapear corpo+48 se a fonte real tiver hook192. Não somar48 se a fonte real tiver hook144. Validar fronteira por pixels. Não existe flag CLI de4s.
7. Os executores antigos `edit_pair_batch.py` e `flow_hook_receita_rapida` usam 3s/receita+2s. Preservar esse formato somente quando aplicável ao pedido. Matriz apenas se solicitada; pares do Flow dependem do controlador real externo.
8. Normalizar/transcrever cada voz uma vez. Preservar palavras, velocidade e idioma. Legendas acompanham o áudio final designado, não tempos de versão anterior.
9. Priorizar repouso entre cenas, outras pausas, repetição e aceleração seletiva até1,20x no perfil apropriado. Não cortar ações importantes silenciosamente. Ler `docs/cortes_por_movimento.md`. Heurísticas não reconhecem ingredientes; elipses autorizadas permanecem `exception/verified=false`, `visual_reviewed=false`.
10. Mudança de perfil/mapeamento: três pilotos antes do restante, cobrindo estilos/vozes, emenda e resultado. Revisão por quadros não equivale a reprodução/escuta integral nem aprovação de cada gesto de todos os vídeos.
11. Validar todos por decode completo, frames/duração, AAC da voz atribuída, SHA da cópia e hashes dos originais. Expor exceções com déficit, preservar atribuições; código2 do assistente é parcial.
12. Se solicitado, incluir pelo distribuidor real conforme `docs/pool.md`. Não criar banco novo, não reimportar reservados, não confundir preservados com livres. Retirada para destinatário é separada; nenhuma postagem/agendamento implícito.
13. Deixar só MP4s finais na entrega, remover scratch próprio no encerramento normal. Preservar originais, finais anteriores e recibos deliberados fora da mídia. Não iniciar watcher/gerador por inferência nem reiniciar processo saudável por falta de entradas.

## Fechar

Informar pasta, concluídos/pendentes, vozes/estilos, verificações e limites da revisão. Medir preparação de voz, planejamento/render, cópia/importação separadamente da auditoria prévia. Não extrapolar tempo de outra máquina como garantia. Novas regras duráveis devem atualizar os guias/DOX e ser reconciliadas com a fonte original.
