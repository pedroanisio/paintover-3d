# REFERENCES.md checado: o que vale para nós

Data: 2 de novembro de 2026. Dois agentes conferiram cada projeto do `_tmp/REFERENCES.md` nas fontes primárias: repositórios, arquivos LICENSE, model cards e artigos. Nada foi instalado, clonado ou executado. Este relatório complementa o `IDEAS_CHECK.md`. As regras de licença são as do `GOAL.md`: o SDK não é comercial; código GPL ou AGPL nunca entra nele; e o SMPL, de licença só para pesquisa, serve como referência.

## Resumo

1. **Os dez projetos existem, mas três estão descritos errado.**
   - O Motius não é um invólucro de EDGE e Bailando: é um arcabouço geral, com 37 métodos.
   - As instruções de texto do TeMuDance são movimentos básicos (agachar, chutar, girar), não "estilo e trajetória".
   - "g1-dance" é o nome de vários repositórios.
   - O OpenDance, o TeMuDance e o AtomicDance não publicaram pesos. O DiscoForcing também não, embora tenha código.
2. **Nenhum modelo entra no SDK.** Todos dependem do SMPL ou SMPL-X e foram treinados com AIST++ ou FineDance, cujos termos são de pesquisa ou de uso não comercial. O EDGE ainda depende do Jukebox, cuja licença não comercial cobre também o que ele gera. O que podemos trazer são ideias e métricas, reimplementadas a partir dos artigos, e alguns trechos de código MIT.
3. **A melhor descoberta ataca o nosso tremido de 2 cm.** O `retarget.py` do g1-dance (MIT) não segura a junta no limite. Ele usa uma penalidade suave que começa 0,05 rad antes do limite, mais um termo de suavidade contra o quadro anterior, e resolve o membro inteiro de uma vez. O nosso `_controls` segura a junta no limite de forma brusca. A troca entre segurar e soltar, quadro a quadro, é a causa provável do tremido de 4 a 6 Hz.
4. **Faltam métricas que meçam o que você pediu: tempo e aceleração de cada gesto.** O Bailando e o EDGE têm a definição de batida cinemática, que é o mínimo local da velocidade média das juntas, e do Beat Align Score. Aplicados entre o vídeo e o manequim, eles medem se preservamos o tempo. O erro de velocidade e de aceleração por junta mede se preservamos a aceleração.
5. **Nenhum projeto resolve os pés deslizando nem a falta de trajetória no mundo.** Todos tiram a raiz do GVHMR, que já avaliamos. A detecção de contatos continua sendo trabalho nosso (item 2 do `IDEAS_CHECK.md`). O EDGE dá um bom formato para ela: 4 bits por quadro (calcanhar e dedos de cada pé) e um termo de consistência para medir o resultado.

## Projeto por projeto

| Projeto | Existe? | Licença (código / pesos / dados) | Maturidade | O que ele realmente faz |
|---|---|---|---|---|
| EDGE (Stanford, CVPR 2023) | Sim | MIT / treinado com AIST++ / precisa do Jukebox (não comercial) | Pesos publicados | Gera dança a partir da música, por difusão. Pose em SMPL-24 com rotações 6D, mais 4 bits de contato. Janelas de 5 s com sobreposição de 2,5 s. Edição por máscara de juntas × tempo. |
| Motius | Sim | Sem licença no repositório; o card do EDGE diz MIT e o do Bailando diz S-Lab (não comercial) | Agosto de 2026, pesos no HF | Arcabouço com 37 métodos, interface `*Pipeline` comum, conversão entre representações e visualizador 3D. O EDGE dele reproduz o original, não o melhora. |
| OpenDance (CVPR 2026) | Só o artigo | Nada publicado | Código "em breve" | Condiciona a dança em música, pontos 2D, trajetória e texto. Os dados vêm de vídeos da internet (ViTPose → GVHMR → Kalman). |
| DiscoForcing (ICML 2026) | Sim | MIT / sem pesos / SMPL, AIST++ e FineDance | 1 commit | Dança contínua a partir de áudio em tempo real. Usa um autoencoder periódico (amplitude, frequência e fase por canal). |
| TeMuDance | Só o artigo | Sem código; FineDance | Abril de 2026 | Dança por texto com movimentos básicos. Testes por predicados cinemáticos. |
| Bailando / Bailando++ (CVPR 2022, TPAMI 2023) | Sim | S-Lab 1.0 (não comercial) / SMPL | Pesos publicados | Dicionário de movimentos por VQ-VAE (corpo superior e inferior separados), com recompensa de alinhamento à batida. A perda usa posição, velocidade e aceleração. |
| MotionMind | Sim, pequeno | MIT / sem pesos / precisa de GVHMR e SMPL | 4 commits, agosto de 2026 | GVHMR → SMPL → ossos VRM. Exporta BVH, GLB e JSON. Não detecta contatos. |
| AtomicDance (ECCV 2026, segundo o repositório) | Sim | MIT / pesos não publicados / AIST++, SMPL | 7 commits | Corta a dança em movimentos atômicos. Os cortes vêm de features visuais I3D, não de velocidade nem de batida. Agrupa os trechos em 100 protótipos. O plano tem um rótulo por quadro, com 0 para transição, e um modelo de difusão preenche as transições. |
| g1-dance (supat-roong) | Sim, um entre vários | MIT; Humanoid-GPT Apache-2.0 (não verificado) | 15 commits, só simulação | Vídeo → IK por mínimos quadrados → robô G1 no MuJoCo. A viabilidade vem de uma passada cinemática e de uma política treinada, não de um solver físico. |
| librosa | Sim | ISC | 1.0.0 | O nosso `beats.py` faz uma única chamada a `beat_track`. Faltam os ataques (onsets) e os tempos fortes de compasso (downbeats). Para os downbeats, o librosa não basta; o beat_this (MIT) faz isso. |

## Ideias para adotar, em ordem

| # | Ideia | De onde vem | Resolve | Como entra |
|---|---|---|---|---|
| 1 | **Métricas de tempo e aceleração**: (a) Beat Align Score nos dois sentidos, entre as batidas cinemáticas do vídeo e as do manequim, com σ em segundos (~0,1 s); (b) atraso por correlação das velocidades; (c) erro de velocidade e de aceleração por junta, normalizado pelo comprimento do osso; (d) PFC, deslizamento em contato e flutuação | Bailando, EDGE, Motius | Sabermos se cada mudança preserva o tempo e a aceleração; medir antes de mudar | Ideia: código nosso no `report.py` da pasta de trabalho |
| 2 | **Penalidade suave antes do limite**: começa 0,05 rad antes do limite (`4·max(0, lo+0,05−q)`), soma suavidade contra o quadro anterior (`0,35·(q−q_ant)`) e resolve o membro inteiro de uma vez, para o excesso passar às juntas vizinhas | g1-dance `retarget.py` (MIT) | Tremido de 2 cm a 4–6 Hz | Mudança no `_controls` do SDK, com teste e medindo com o item 1 |
| 3 | **Descartar saltos de velocidade antes de preencher**: um quadro é inválido se algum ponto andar mais de 12 m/s; buracos de até 0,2 s são preenchidos e nada atravessa um buraco maior. Somado à confiança por ponto e ao Viterbi do `IDEAS_CHECK.md` | g1-dance `clean.py` (MIT) | Torção de coxa e pé presa no limite (inversões de profundidade) | `analyse.py`, antes do Savitzky–Golay |
| 4 | **Contatos no formato do EDGE**: 4 bits por quadro, a partir dos pontos de calcanhar e dedos do RTMW3D, com histerese de altura e velocidade, viram `plant()` e `hold(flat=True)`. Medidos pelo termo de consistência (velocidade do pé × contato = 0) | EDGE | Pés deslizando | Ideia: detecção na pasta de trabalho, planting no SDK |
| 5 | **Ataques e compassos**: `onset_detect` do librosa para os acentos fora da batida e beat_this para compassos e contagens de 8. Os picos e as paradas dos gestos são alinhados a eles | librosa (ISC), beat_this (MIT) | Medir e preservar os acentos; âncoras para a biblioteca de movimentos | Ferramentas na pasta de trabalho |
| 6 | **Biblioteca de movimentos (depois)**: um Movimento tem um protótipo, etiquetas e instâncias (take, trecho, duração nativa, número de batidas); as transições são geradas, não guardadas. **Não reescalar o tempo como o AtomicDance faz**, porque isso muda a aceleração: guardar no tempo nativo e ajustar só entre âncoras de batida | AtomicDance (artigo) | Objetivo futuro da biblioteca | Ideia |
| 7 | **Música → dança (depois)**: máscara de (controle × quadro) como interface de edição do movimento com keys, e emenda de janelas com a sobreposição como restrição rígida, não com crossfade, que achata a aceleração | EDGE | Objetivo futuro de coreografia | Ideia. O EDGE ou o Motius-EDGE pode rodar como ferramenta separada, com uma ponte Humanoid ↔ SMPL, como referência |

**Não adotar:** o filtro passa-baixa de 4 Hz do g1-dance, que apaga os acentos; reescalar o tempo como o AtomicDance; e FID_k e FID_g, que exigem os conjuntos de referência do AIST++ e extratores em SMPL, e que o próprio EDGE mostra discordarem de estudos com usuários. O teto de velocidade do MotionMind (80 rad/s) serve no máximo como alarme.

## A arquitetura proposta e o que já temos

| Camada proposta | O que temos | O que falta |
|---|---|---|
| Vídeo → movimento (GVHMR) | RTMW3D em todos os quadros, `load_keypoints()` e o manequim | Confiança por ponto, descarte de saltos, Viterbi e trajetória no mundo. O GVHMR fica só como referência, por causa do SMPL. |
| Representação canônica (rotações, raiz, velocidade, contatos) | `Take` com as 103 controles do manequim, keys por quadro (`motion.py`) e BVH/glTF de entrada e saída | Contatos e proveniência (observado ou estimado) no `Take` |
| Biblioteca de dança | — | Ideia 6, depois das ideias 1 a 5 |
| Motor musical | `beats.py` (batida e andamento) | Ataques, compassos e frases (ideia 5) |
| sr-core e scene-render | Pronto: o vídeo completo de 9.801 quadros com áudio já sai por aqui | Nada urgente. O motor é ~3% do tempo de render; o gargalo era a checagem de colisão do SDK, já corrigida. |

O documento de referência recomenda começar pelo GVHMR. Discordamos: a licença do SMPL só permite pesquisa, ele lê uma pessoa por vez e o nosso vídeo tem até quatro dançarinos. A nossa base (RTMW3D → manequim) já funciona. O ganho está nas ideias 1 a 4.

## Fontes

- `github.com/Stanford-TML/EDGE`; arXiv 2211.10658
- `github.com/ZeyuLing/Motius`; `huggingface.co/ZeyuLing/Motius-EDGE-AISTPP`, `…/Motius-Bailando-AISTPP`
- arXiv 2506.07565; `open-dance.github.io`
- arXiv 2605.28491; `github.com/CurMack/DiscoForcing`
- arXiv 2604.17005
- `github.com/lisiyao21/Bailando`; arXiv 2203.13055
- `github.com/rohitacharyams/MotionMind`
- `github.com/oceanflowlab/AtomicDance`; arXiv 2607.13978
- `github.com/supat-roong/g1-dance` (`retarget.py`, `motion/clean.py`, `motion/constraints.py`); `github.com/OyunbatBatzorig/g1-dance-rl`; `github.com/mizuharaa/g1-dance-studio`
- `github.com/librosa/librosa`; beat_this (CPJKU, ISMIR 2024)
- Termos: AIST Dance DB (pesquisa acadêmica), FineDance (não comercial, sem redistribuição), Jukebox (não comercial), SMPL/SMPL-X (pesquisa)
