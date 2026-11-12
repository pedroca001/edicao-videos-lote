# Edição de vídeos em lote

## Purpose

Repositório portátil com instruções, skill e snapshot do Editor Vídeos Bassi 0.8.2. Recebe vídeos e vozes existentes; entrega MP4s com montagem e legendas.

## Ownership

- Exportação: `<CODIGO_ROOT>/edicao-videos-lote`.
- Fonte original do algoritmo: `<CODIGO_ROOT>/local_video_editor`.
- Fonte original do workflow: `<BRAIN_ROOT>/Skills/edicao_videos_lote/SKILL.md`.
- Fora do Brain, este repositório é suficiente para consultar o contrato e instalar os componentes Mac. Não requer os caminhos privados do autor.
- Alterações neste export devem ser reconciliadas com a fonte original antes da próxima exportação; não sobrescrever correções locais automaticamente.

## Local Contracts

- Ler `skills/edicao_videos_lote/SKILL.md`, `docs/operacao.md` e o perfil aplicável antes de editar.
- Teste Hooks atual: hook de 4 s, receita de quatro cenas de 8 s entrando no primeiro frame. A adaptação está em `docs/hooks_4s.md`; não existe flag CLI `--hook-seconds 4` nesta versão.
- Perfis antigos mantêm seus contratos. O wizard não acrescenta hooks e os executores rápidos antigos usam 3 s com a receita 2 s adiantada.
- Dois estilos ativos: impacto_amarelo/0 e duas_linhas_lima/2. ID 1 removido, sem reindexar.
- Voz externa inteira, sem misturar som da fonte. Preservar originais e atribuições; um hook exclusivo por receita quando solicitado. Não fazer matriz sem pedido.
- Cortes dentro de gestos e alongamento visual exigem escolha aplicável ao lote. Instruções ou autorizações históricas não autorizam novos lotes.
- Heurísticas locais não reconhecem ingredientes. Até três pilotos/amostras; integridade técnica em todos os finais. Informar limites da revisão.
- Não incluir vídeos, áudios, modelos, bancos, inventários privados, credenciais, caminhos pessoais ou relatórios reais no Git.
- Apenas MP4s finais na entrega. Scratch fora do checkout, removido no encerramento normal. Recibos deliberados de operação ficam fora da pasta de mídia.
- Importação no pool é integração separada, descrita em `docs/pool.md`; não publicar/agendar nem iniciar geradores por inferência.

## Work Guidance

Usar duas tarefas de render por padrão, transcrição uma vez por voz e processamento local. Resolver runtime/configuração na máquina de destino. Windows requer o runtime CUDA/NVENC existente; não tem bootstrap independente como o Mac.

## Verification

- `python -B -m unittest discover -s tests -v` com NumPy instalado.
- Conferir `source_manifest.json` para integridade do snapshot original; atualizar manifesto após mudanças deliberadas nos arquivos listados.
- Mudança de perfil/mapeamento: três pilotos antes do restante, incluindo fronteira hook/receita e encerramento.
- Todos os finais: decode completo, frames/duração, AAC da voz atribuída e SHA256 da cópia. Conferir hashes dos originais.
- Instalar/atualizar em outra máquina não é comprovado pelos testes do checkout.

## Child DOX Index

- `docs/`: operação, cortes, adaptação de hooks e integração com pool; governados por esta raiz.
- `skills/edicao_videos_lote/`: instruções portáteis para agentes; governadas por esta raiz.
- `tests/`: testes do editor original; governados por esta raiz.
