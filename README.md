# Edição de vídeos em lote

Instruções e código do Editor Vídeos Bassi **0.8.2**, com processamento local, narrações prontas e legendas automáticas. Snapshot exportado em 12/11/2026, renderer 0.4.2.

O formato dos últimos lotes Teste Hooks é **4 segundos de hook + receita entrando desde o início**, com duração final ajustada à voz inteira. As legendas variam entre **impacto amarelo (0)** e **duas linhas lima (2)**. Cápsula menta foi removida.

## Começar

1. Leia a [operação do lote](docs/operacao.md).
2. Instale no [Mac Apple Silicon](LEIA_PRIMEIRO.md), incluindo M2, ou configure o [Windows com NVIDIA](INSTALACAO_WINDOWS.md).
3. Escolha a rota conforme a estrutura real do vídeo:

| Entrada | Rota |
| --- | --- |
| Receita Vids de cerca de 40 s, sem hook | `batch_assistant.py`, perfil `vids_receita` |
| Receita Flow de cerca de 32 s, sem hook | `conservative`; resumo somente se autorizado |
| Hook separado de 8 s + receita de 32 s, abertura final de 4 s | [Adaptação de 4 s](docs/hooks_4s.md), com plano explícito |
| Filme já unido: hook de 6 s + receita de 32 s, abertura final de 4 s | [Adaptação de 4 s](docs/hooks_4s.md), conferindo a fronteira real |
| Filme já unido: hook de 6 s + receita de 32 s, formato rápido anterior | `flow_hook_receita_rapida`: hook 3 s, receita 2 s adiantada |
| Fonte de 40 s com hook de 8 s já unido | Mapear explicitamente os frames; não tratar como Vids sem hook |

**A abertura de 4 s é uma adaptação documentada por plano, usada nas entregas anteriores. Não é uma opção automática do launcher.** O planejador original aceita abertura de 6 s ou 3 s. Não usar a matriz ou o executor pareado antigo esperando obter 4 s.

## Para usar com Codex ou outro agente

Abra esta pasta como workspace e peça:

> Leia AGENTS.md e skills/edicao_videos_lote/SKILL.md. Edite somente as fontes ainda inéditas da pasta que vou informar, usando as vozes fornecidas. Para hooks separados de 8 s e receitas de quatro cenas de 8 s, use hook de 4 s e receita desde o primeiro quadro conforme docs/hooks_4s.md. Preserve originais, registre as atribuições por SHA, use os dois estilos equilibrados e valide três pilotos antes do restante. Informe as exceções e a pasta entregue.

A skill também pode ser instalada copiando `skills/edicao_videos_lote` para a pasta de skills do agente. Ela depende deste checkout para acessar o código e os guias.

## Conteúdo

- [Skill portátil](skills/edicao_videos_lote/SKILL.md): fluxo para o agente.
- [Operação](docs/operacao.md): inventário, distribuição, revisão, custos e fechamento.
- [Cortes por movimento](docs/cortes_por_movimento.md): pausas, gestos e limites.
- [Hooks de 4 s](docs/hooks_4s.md): normalização e mapeamento exato.
- [Pool](docs/pool.md): regras para incluir e retirar sem duplicar origens.
- Arquivos Python, launchers e `tests/`: snapshot do editor original.
- `source_manifest.json`: hashes dos arquivos copiados, sem dados dos lotes.

O pipeline local não usa LLM nem API paga. O uso do agente na conversa e na inspeção de amostras consome o uso normal desse agente. O tempo depende da máquina e deve ser medido por lote.

Este repositório não contém a mídia, as copys, o ledger ou o controlador Flow do autor. `edit_pair_batch.py` exige módulos externos do controlador real (`bridge`, `platform_lock`, `compose_hook_recipe`), descritos na operação; não é um executor independente de 4 s. O editor gera arquivos locais. A gestão do pool e a postagem são etapas separadas.

## Verificação do checkout

Com o Python do runtime instalado e NumPy disponível:

```sh
python -B -m unittest discover -s tests -v
```

Os testes verificam contratos do código. Não instalam o aplicativo em outra máquina nem substituem o teste de render do instalador ou a revisão dos pilotos reais.

Validação desta exportação (12/11/2026): 50 testes aprovados, hashes dos 31 arquivos de código/testes conferidos e sintaxe dos launchers Bash validada. O código copiado não foi alterado.
