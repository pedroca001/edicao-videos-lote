# Incluir no pool sem duplicar fontes

Este repositório entrega os MP4s. A integração com o pool privado é responsabilidade do distribuidor existente na máquina de operação; seu código, ledger e credenciais não estão aqui.

## Antes da edição

Consultar histórico por SHA da fonte e identidade de origem, incluindo outras campanhas. Reconciliar recibos de composição e auditorias antigas quando o cadastro não tiver identidade de origem. Um original preservado, uma cópia do final ou um arquivo já separado para alguém não são estoque inédito.

Separar:

- originais ainda não editados;
- finais já editados e livres;
- finais reservados, agendados, retirados, publicados ou a confirmar;
- fontes/cópias preservadas e intermediários técnicos.

Não usar contagem física de MP4s como quantidade livre. Não liberar um agendamento só porque seu horário passou. Não importar novamente cópias de finais vinculados ao histórico.

## Depois da edição autorizada

1. Verificar decode/frames/AAC/SHA e os originais.
2. Identificar campanha (ED/WL), tipo de conteúdo (`recipe` para receita) e grupo real da voz pelo SHA. COPY/CP/VD e seus números não são equivalentes por nome.
3. Usar a importação nativa do distribuidor. Preservar delivery e recibos, sem copiar manualmente para a pasta de disponíveis burlando cadastro/reservas.
4. Registrar vínculo do final com receita, hook e voz originais. Backup transacional do ledger antes da mutação, integridade/FKs e preservação do histórico depois.
5. Conferir elegibilidade efetiva após importar e informar o total livre atual. Quantidade importada não é necessariamente todo o estoque.

Na instalação original, a rota utiliza `Ledger.ingest` e `MediaPool.include_existing` do projeto separado `facebook_reels_distributor`, com seleção explícita do grupo de voz. Resolver a configuração/ledger real; não criar um banco de produção vazio para simular o pool. Os caminhos de mídia devem ser obtidos pelo catálogo atual, pois finais podem ter sido movidos após a edição.

## Separar para Guilherme ou outro destinatário

Somente quando solicitado. Usar retirada nativa, com reserva exclusiva por SHA/origem antes da movimentação. Distribuir entre vozes conforme o pedido, pasta com a data solicitada e quantidade exata. Preservar remessas anteriores. Uma pasta de retirada já existente pode representar retomada; reconciliar antes de acrescentar outro lote.

Separado não significa enviado. Importação/retirada não autoriza upload, email, publicação ou agendamento.
