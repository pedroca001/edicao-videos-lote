# Configurar no Windows

Este caminho reutiliza uma instalação **existente** de LocalWhisper ou um Python com NumPy, PyTorch e faster-whisper, modelo local large-v3-turbo e FFmpeg com libass. Requer GPU NVIDIA/CUDA e encoder NVENC funcional. Não é o bootstrap independente oferecido no Mac.

Com os componentes existentes:

```powershell
python install_windows.py
```

Ou informe caminhos locais explicitamente:

```powershell
python install_windows.py --python "C:\caminho\python.exe" --model "C:\caminho\modelo" --ffmpeg "C:\caminho\ffmpeg.exe"
```

O instalador testa ASR local com silêncio e renderiza os dois estilos com NVENC, verificando decode/frames/AAC. Não mede a precisão da transcrição numa voz real. Não altera o aplicativo de ditado.

Configuração e referência da instalação ficam em `~/.local/share/local_video_editor`. O código permanece neste checkout. Use o shell PowerShell disponível na máquina.

```powershell
.\iniciar_editor.ps1 --videos "C:\caminho\videos" --audio "C:\caminho\voz.mp3" restante --output "C:\caminho\nova_entrega" --profile vids_receita --workers 2
```

Esse exemplo é para Vids sem hook, aproximadamente 40 s. Para Flow de 32 s, começar com `conservative`. Resumos e alongamento seguem a escolha do lote.

O formato atual de **hook 4 s + receita desde o início** exige plano explícito conforme [hooks_4s.md](docs/hooks_4s.md). `--matrix-manifest` e `edit_pair_batch.py` usam o formato rápido anterior de 3 s/receita+2 s, não a adaptação de 4 s.

Dois estilos ativos, IDs 0 e 2, sem cápsula menta. Voz intacta, dois workers, verificação técnica de todos os finais, até três pilotos por perfil/mapeamento. Não reutilizar configs de outra máquina nem iniciar geradores ou watchers por este guia.
