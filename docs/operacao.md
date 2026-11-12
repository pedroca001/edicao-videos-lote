# Operação de um lote

## 1. Inventário antes do render

Conferir acesso ao SSD/Drive, arquivos realmente disponíveis e áudios. Não confundir número no nome da pasta, imagens, cenas intermediárias ou arquivos ainda sincronizando com vídeos completos. Ignorar sidecars AppleDouble (`._*`) e contar fontes únicas por SHA256.

Quando o pedido for editar somente inéditos, reconciliar hashes, origens, manifestos, recibos e histórico do pool. Ausência de um job ou de um final físico não prova que o original nunca foi usado. Fontes já editadas para outra campanha também precisam ser reconhecidas. Se não houver histórico suficiente, declarar a incerteza.

Identificar ED e WL e manter suas vozes/pools separados. Medir resolução, FPS, duração, frames e estrutura real. Uma fonte de 40 s pode ser Vids com quatro cenas de 10 s ou hook de 8 s + corpo de 32 s; duração sozinha não decide o perfil.

Congelar um manifesto externo com ID, caminho, SHA da receita, hook, voz, estilo, formato e destino. Informar contagem exata antes de render. Não iniciar geração, watcher ou coleta ilimitada se o pedido for um lote fechado.

## 2. Distribuição

- Uma saída por receita/hook/voz atribuídos. Usar matriz de todas as fontes com todas as vozes somente se pedido.
- Quando a quantidade for igual por áudio: dividir por número de vozes e distribuir a sobra de uma em uma. Exemplo: 330/6 = 55; 58 em três grupos solicitados = 20/20/18.
- Embaralhar com seed registrada. Manter atribuições nas retomadas e exceções, sem trocar a voz para esconder déficit.
- Dois estilos equilibrados, um por vídeo inteiro: 0 impacto_amarelo, 2 duas_linhas_lima. ID 1 não é válido.
- Conferir congruência da copy com a receita. No lote CP26/27/29/30, CP29 era a voz genérica usada para azeite/mel/canela; essa relação deve ser reconferida pelo conteúdo/SHA, não só pelo nome CP29.
- Exclusividade por conteúdo e histórico. Renomear um hook não o torna novo; mesmo ID com outro hash exige avaliar a versão correta e o vínculo.

## 3. Runtime e voz

Mac: instalador MLX/VideoToolbox; Windows: runtime CUDA/NVENC configurado. Resolver caminhos locais, ler configuração criada nessa máquina e fazer teste real. Não presumir runtime de outro aplicativo.

Normalizar cada áudio uma vez e transcrever localmente uma vez por voz por execução, com tempos de palavras. Reutilizar a transcrição em todo o grupo. Áudio final deve corresponder ao AAC designado. Preservar as palavras, velocidade e idioma da voz, sem misturar o áudio do vídeo original.

Se for pedido encurtar silêncios da voz, tratar como etapa separada: preservar respirações/bordas e palavras fracas, exportar nova versão para revisão quando solicitado e transcrever essa versão. Não aplicar tempos da voz original a um áudio encurtado. O modo comum de receitas não encurta silêncios da voz automaticamente.

## 4. Planejar e executar

| Perfil | Estrutura/limite |
| --- | --- |
| `vids_receita` | Vids 39-41 s, pausas e repetições nas mexidas conhecidas, aceleração visual seletiva até 1,20x |
| `conservative` | Outras estruturas; não presume ingredientes ou ciclos |
| `vids_receita_resumida` | Opt-in, 39-41 s para voz 13,5-24 s, elipses em gestos |
| `flow_receita_resumida` | Opt-in, 31-33 s/quatro cenas de 8 s, voz 13-31 s |
| `flow_cenas_resumidas` | Opt-in, quatro cenas de 8 s diferentes, voz 13,5-31 s |
| `flow_hook_receita` | Estrutura original 6 s + 32 s, hook completo de 6 s |
| `flow_hook_receita_rapida` | Mesma estrutura, hook 3 s, receita avançada 2 s |
| Adaptação de 4 s | Plano explícito de [hooks_4s.md](hooks_4s.md), corpo desde o início |

Para fontes sem hook, `batch_assistant.py` coordena o planejamento e `run_pipeline.py`. Padrão Vids: `--review-mode auto --profile vids_receita --no-ui --sample-size 3`. `--plan-only` é opcional quando medir a viabilidade for útil; não precisa repetir em toda execução.

Para pares do controlador Flow, `edit_pair_batch.py MANIFESTO --config CONFIG --flow-root FLOW_ROOT` exige o controlador externo real, seus módulos `bridge`, `platform_lock`, `compose_hook_recipe` e `ready_edits.json`. O manifesto contém `quantity`, `destination`, `long_voice`, `pairs`, e cada par `id`, `hook_folder`, `recipe_folder`, `audio`, `style`. Este repositório não inclui o controlador. Esse executor implementa 3 s/receita+2 s. Não o usar para obter 4 s sem adaptação.

`edit_hook_matrix.py --manifest MANIFESTO --config CONFIG --review-pilots` é para cruzamento solicitado, não para substituir atribuições exclusivas. Entradas `sources: [{path, label}]`, `audios`, `output`, perfil e política explícita de voz longa. Não passar fontes de 40 s direto ao planejador de 38 s.

Manter dois workers. Cortes por repouso primeiro, depois repetição e aceleração seletiva dentro dos limites. Montagem resumida requer autorização aplicável; registrar elipses como `exception`, `verified: false`, `visual_reviewed: false`. Não chamar movimento baixo de reconhecimento de ingredientes.

Voz maior que o visual exige uma escolha concreta já autorizada ou nova escolha: desacelerar somente o corpo ou repetir apresentação. No formato anterior, `long_voice=slow_recipe` preserva hook a 1x e limita corpo a 0,80x. Essa escolha não autoriza alterar qualquer outro vídeo/voz. Nunca truncar voz ou recuar a entrada do corpo silenciosamente.

## 5. Revisão e verificação

Em mudança de perfil/mapeamento, renderizar três pilotos antes do restante. Cobrir vozes/estilos e limites de duração. Inspecionar início, emenda hook/corpo, cortes e apresentação; conferir também voz/legenda. Em lotes seguintes do mesmo perfil, revisão limitada a até três saídas. Não analisar visualmente todos os vídeos pelo agente.

Em todos os finais: decode completo, resolução/codecs, quantidade exata de frames e duração, integridade do AAC da voz e SHA256 da cópia no destino. Conferir os hashes dos originais. Para 4 s, conferir a fronteira normalizada também por pixels.

Inspeção por quadros não equivale a reprodução/escuta integral. Uma amostra não comprova semanticamente todas as ações. Exceções devem continuar listadas com motivo e déficit; o lote pode concluir os itens resolvidos. Código 2 do assistente indica parcial, mesmo com MP4s produzidos.

## 6. Retomada e fechamento

Consultar processos/recibos antes de retomar. Não reiniciar watcher saudável por ausência de fontes. Reusar caches só após comparar AAC exato e validar palavras/segmentos. `--watch` é explícito, nunca padrão implícito.

Preservar finais já verificados; não sobrescrever arquivos desconhecidos. Copiar através de parcial no destino, conferir SHA e renomear atomicamente. Deixar somente MP4s na entrega. Planos, ASS, frames, transcrições e caches por tarefa ficam em scratch do sistema e são removidos ao terminar. Recibos externos deliberados podem registrar proveniência sem duplicar mídia.

Fechar com quantidades concluídas/pendentes, vozes/estilos, pasta, verificações e tempos medidos. Separar auditoria, preparação de voz, planejamento/render e cópia/importação. Pipeline local usa zero tokens de LLM; conversa e amostras no agente consomem uso normal. Não prometer no M2 o tempo medido em outra máquina.

Incluir no pool somente se autorizado, seguindo [pool.md](pool.md). Separar para alguém não significa enviar. Editar/incluir não significa publicar ou agendar.
