# Instalar e usar no Mac

Apple Silicon M1 ou mais novo, incluindo M2; macOS Sonoma 14 ou mais novo. Reserve pelo menos 8 GB livres para a instalação e espaço adicional para os vídeos. Use Terminal nativo, sem Rosetta.

## Instalação única

Baixe o repositório como ZIP no GitHub e extraia mantendo os arquivos juntos. Na pasta extraída, execute:

```sh
bash instalar_mac.command
```

Também pode abrir Terminal, digitar `bash` e um espaço, arrastar `instalar_mac.command` para a janela e pressionar Enter.

O instalador baixa uv/Python 3.12, FFmpeg com libass, dependências de `requirements_apple.txt` e MLX Whisper large-v3-turbo. Testa carregamento do modelo e render real de legenda. Não exige Homebrew, login Google ou chave de API. Precisa de internet na primeira instalação.

Aplicativo, runtime, modelo e configuração ficam em `~/Library/Application Support/EditorVideosBassi`. Dependências não ficam dentro do repositório. Depois da instalação, a edição roda localmente.

## Receitas sem hook

O launcher abre o assistente para vídeos Vids de aproximadamente 40 s. Selecione a pasta de entrada, os áudios e a quantidade por áudio:

```sh
bash iniciar_editor.command
```

Exemplo por Terminal:

```sh
bash iniciar_editor.command \
  --videos "/caminho/videos" \
  --audio "/caminho/audio_1.mp4" 20 \
  --audio "/caminho/audio_2.mp4" 20 \
  --audio "/caminho/audio_3.mp4" restante \
  --output "/caminho/nova_entrega" \
  --review-mode auto --profile vids_receita --no-ui --sample-size 3 --workers 2
```

Use somente fontes na pasta de entrada, com áudios e entregas fora dela. `restante` só no último áudio. A saída deve ser nova. O assistente ordena naturalmente os nomes e informa exceções; código de saída 2 indica lote parcial. O assistente não insere hooks automaticamente.

Para receitas Flow de 32 s, selecione `--profile conservative`. Para outros perfis, veja [operação](docs/operacao.md). Os resumos que cortam dentro dos gestos precisam de autorização para o lote.

## Hooks e planos explícitos

Para o formato atual de 4 s, leia [hooks_4s.md](docs/hooks_4s.md). Execute os scripts deste checkout com o Python instalado, usando o `config.json` criado na máquina. Não copie a configuração do autor.

```sh
"$HOME/Library/Application Support/EditorVideosBassi/venv/bin/python" -B \
  batch_assistant.py --help
```

O instalador copia o núcleo do assistente para `app/`. Os executores adicionais, como matriz e pares, permanecem no checkout. Mantenha-o para usar esses scripts. Não há flag de 4 s no assistente ou na matriz.

## Conferir a entrega

MP4s verticais 720x1280, H.264, 24 fps, AAC. A voz externa substitui o som original da receita e permanece inteira. Áudios não AAC são normalizados uma vez, sem alterar a fala deliberadamente.

O programa verifica os arquivos tecnicamente. Confira também até três amostras, incluindo início, emendas, legenda e resultado. O reconhecimento de fala é automático; termos incomuns podem precisar de correção.

Em falha, preserve os finais já verificados e a mensagem de erro. Não reexecute todo o lote como se fosse inédito. Mantenha o SSD conectado até terminar. Para interromper, Control+C e aguarde o encerramento normal. Não há retomada automática genérica entre execuções.

## Atualização

Baixe uma nova versão do checkout e execute o instalador novamente para atualizar o núcleo instalado. Conferir apenas a versão do GitHub não comprova a versão da instalação local. O teste no Mac do autor também não comprova funcionamento no Mac de destino.

## Componentes públicos

[uv](https://docs.astral.sh/uv/), [FFmpeg via imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg), [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) e [modelo large-v3-turbo](https://huggingface.co/mlx-community/whisper-large-v3-turbo). Fontes são resolvidas pelo macOS; a aparência pode variar se a fonte solicitada estiver ausente.
