## Objetivo: Motion-to-Dance Manequim SDK

Desenvolver uma ferramenta capaz de analisar vídeos de dança, extrair e reconstruir os movimentos corporais em um manequim digital articulado e transformar esses movimentos em uma biblioteca reutilizável de animações.

O objetivo é evoluir essa capacidade para um **SDK de dança programática**, integrado ao `sr-core` e ao `scene-render`, permitindo criar, combinar, adaptar e executar coreografias automaticamente, sincronizadas ao ritmo, à estrutura e às características musicais de qualquer faixa.

O SDK não começa do zero. Ele estende o `srlocations` (este repositório) e o manequim que já existe nele. Cada capacidade nova entra por um ponto de extensão do SDK (`Figure`, `Check`, `Library`, `Plugin`, `PropTemplate` e outros), não por um caso especial dentro de um compilador.

### Onde estamos (novembro de 2026)

Primeiro teste real: o vídeo "FE!N" (YouTube `fOGHfeRo7Iw`, 23,976 fps, 408 s). Nele foram medidos 26 trechos de dançarinos, somando 17.204 quadros.

| Etapa | Existe hoje | Medido |
|---|---|---|
| Pessoas e pontos 3D por quadro | YOLOX-m + RTMW3D-x via rtmlib (Apache-2.0), 133 pontos por pessoa | Profundidade relativa ao quadril; mãos e cabeça pouco confiáveis neste vídeo |
| Batida | librosa | 152 bpm; os dançarinos param na batida em 18 de 26 trechos (p = 0,001) |
| Pontos → manequim | `srlocations.interchange.load_keypoints()`, que gera um `Take` pelo mesmo `_retargeted()` do BVH e do glTF | Atraso dos picos de velocidade: 0 quadros. Aceleração de pico: 107% da do rastreador. Distância mediana das articulações: 7,8 cm |
| Manequim | `stock.mannequin`: 55 ossos e 103 parâmetros (nomes do Unity Humanoid), amplitudes clínicas, colisão, `holds`, `balanced`, `walk` | Articulações presas no limite: clavículas ~40% dos quadros, torção de coxa e pé ~30% |
| Movimento e render | `location.move()`, `Clip`, `Renderer.clip()`; um quadro de filme é idêntico, byte a byte, a um still de `location.at(t)` | 5 s com 3 manequins: ~40 s de leitura e ~3 min de render |
| Exportar | `save_bvh()` e `save_glb()`, inclusive com skin | Ida e volta da pose dentro de 1 mm |

Ainda não existem a biblioteca de passos, a análise musical além da batida, a coreografia procedural nem pés plantados nos vídeos.

### Capacidades fundamentais

1. **Video-to-Motion:** analisar vídeos e reconstruir movimentos em 3D, preservando articulações, orientação espacial, profundidade, velocidade, aceleração e timing original.
   - *Entrada:* um vídeo. *Saída:* pontos 3D por quadro, por dançarino, com confiança por ponto e tempo exato do quadro de origem.
   - *Falta:* guardar a confiança que o modelo já dá; corrigir a profundidade invertida (joelho ou dedão do lado errado); identificar a mesma pessoa em cortes diferentes; separar o que a câmera move do que o dançarino desloca.

2. **Motion Retargeting:** transferir os movimentos capturados para diferentes personagens e manequins, independentemente de suas proporções corporais, preservando a intenção e a expressividade da performance.
   - *Entrada:* pontos ou BVH/glTF. *Saída:* um `Take` com poses do `Figure` de destino e a lista do que ficou preso no limite.
   - *Falta:* ajustar a postura de repouso da clavícula a cada dançarino, porque hoje a diferença de proporção conta como pose fora da amplitude; plantar os pés nos contatos (com `holds`/`balanced`); deslocar a figura em profundidade, e não só pela posição na tela.

3. **Dance Motion Library:** construir uma biblioteca de passos, gestos, transições e sequências coreográficas, com metadados de ritmo, duração, estilo, intensidade e compatibilidade entre movimentos.
   - Cada passo é um trecho de `Take` cortado em batidas, com: duração em batidas e compassos, pose de entrada e de saída, pé de apoio, deslocamento, intensidade (velocidade e aceleração medidas), estilo e origem (vídeo, trecho, quadros).
   - Dois passos são compatíveis quando a pose de saída de um alcança a de entrada do outro dentro do tempo de uma transição, sem violar amplitudes nem colisão.
   - Publica pelo `Catalog`, com versão e digest, como as props.

4. **Music-to-Motion:** analisar BPM, beats, compassos, acentos, frases musicais e mudanças de energia para selecionar, combinar e adaptar movimentos à música.
   - *Saída:* uma grade de tempo da faixa (batidas, tempo forte, compassos, frases, seções, curva de energia) que outras partes do SDK leem.
   - Adaptar um passo a outro BPM muda o tempo dele, não a forma: as paradas ficam na batida e a aceleração escala com o tempo.

5. **Procedural Choreography:** gerar coreografias programaticamente, com controle sobre estilo, complexidade, velocidade, expressividade, improvisação e sincronização musical.
   - Determinística: a mesma faixa, os mesmos parâmetros e a mesma `seed` dão a mesma coreografia.
   - Cada escolha é registrada (qual passo, por quê, em qual batida), para que se possa revisar e editar a coreografia.

6. **Rendering & SDK Integration:** disponibilizar APIs para controlar personagens articulados e executar coreografias por meio do `sr-core` e do `scene-render`, com suporte a animações determinísticas e reprodução independente da taxa de quadros.
   - A regra de movimento que já existe vale aqui: qualquer instante `t` é uma pose bem definida, e um quadro a qualquer fps é igual ao still daquele instante.
   - Sincronizar com o áudio é parte da API: o filme sai na taxa da fonte, ou o tempo é exato em segundos, nunca "24 em vez de 23,976".

### Critérios de qualidade

A ferramenta deve priorizar a fidelidade temporal e espacial dos movimentos, especialmente em danças rápidas, mudanças de direção, rotações, deslocamentos e interações com o chão.

A reconstrução deve preservar não apenas as posições das articulações, mas também a dinâmica do movimento: velocidade, aceleração, distribuição de peso, contatos, equilíbrio e continuidade entre poses.

O sistema deve diferenciar movimentos observados, movimentos estimados e movimentos sintetizados, mantendo indicadores de confiança para situações de oclusão ou ambiguidade de profundidade.

#### Como medir

As metas abaixo são propostas, a confirmar. As de posição só valem contra uma referência marcada à mão: hoje a única comparação possível é manequim contra rastreador, o que mede a leitura, mas não a verdade.

| Critério | Medida | Meta proposta | Hoje (FE!N, cena 14) |
|---|---|---|---|
| Timing | Atraso dos picos de velocidade (correlação cruzada) entre fonte e manequim | 0 quadros em ≥ 95% das articulações | 0 quadros em todas |
| Aceleração | Aceleração de pico (percentil 95) do manequim sobre a da fonte | 90–110% | 107–110% |
| Ritmo | Ganho na faixa da batida (2–4 Hz a 152 bpm) | 95–105% | 105% |
| Movimento espúrio | Tremor que o manequim acrescenta a 4–6 Hz nas mãos e pés (RMS) | ≤ 1 cm | 2 cm |
| Saltos | Maior mudança de posição de uma mão ou pé entre dois quadros, sobre a dos pontos | ≤ 2× | Garantido por teste em varreduras sintéticas |
| Posição | Erro mediano por articulação contra marcação manual (MPJPE) | ≤ 5 cm; p95 ≤ 15 cm | Sem referência manual ainda |
| Chão | Deslize de um pé em contato | ≤ 2 cm por contato | Pés não plantados |
| Equilíbrio | Centro de massa dentro da base de apoio quando parado | Sempre, salvo salto ou queda | `balanced` existe, não ligado aos vídeos |
| Determinismo | Mesma entrada, mesma saída | Byte a byte | Já é regra do SDK para movimento |

#### Observado, estimado, sintetizado

Toda pose e toda chave carregam a sua origem e uma confiança de 0 a 1:

- **Observado:** vem de um ponto que o rastreador viu naquele quadro, com confiança acima do limite.
- **Estimado:** existe porque foi inferido, seja um ponto ausente mantido do quadro anterior, uma articulação presa no limite, uma profundidade corrigida ou um pé plantado.
- **Sintetizado:** foi criado pelo SDK, como uma transição entre passos, um passo adaptado a outro BPM ou a coreografia procedural.

`Take.clamped` já registra o que ficou preso no limite. O resto ainda precisa ser registrado.

### Restrições

- **Pessoas reais.** O manequim nunca substitui as proporções aprovadas de um personagem com nome. A aparência de pessoas reais (dançarinos, o usuário) fica fora dos dados de medida e do repositório. Do vídeo saem só números: pontos, ângulos, tempos.
- **Dados de vídeo fora do repositório.** Vídeos, pontos e renders ficam em pastas de trabalho fora dos repositórios.
- **Coreografia de terceiros.** Uma coreografia de referência serve para medir e validar. Publicar uma reprodução dela é decisão de direitos, não do SDK.
- **Licenças.** O SDK não é comercial (decidido em 2/11/2026), então código e pesos de uso não comercial (CC-BY-NC, pesos treinados com dados não comerciais) podem ser usados, desde que a licença seja registrada ao lado da ferramenta. Continuam de fora: copiar ou traduzir código GPL ou AGPL para o SDK, como o StykAnimate ou o HTD-Refine (rodar um deles como ferramenta separada na pasta de trabalho é outra coisa); licenças que proíbem o próprio uso, como a do Sapiens2, que veta processamento biométrico; e modelos de corpo cuja licença só permite pesquisa científica, como o SMPL, que ficam para comparação.
- **Amplitudes.** As amplitudes do manequim são proteção contra pose quebrada, não um juízo de conforto. Ampliá-las para dança é decisão explícita e documentada, nunca um ajuste para fazer um teste passar.
- **Testes.** Toda mudança no SDK entra com teste que falha sem ela, e o conjunto completo continua passando.

### Fora de escopo por enquanto

- Física simulada (`rigidBody` e `physics` do motor seguem sem uso). Contato e equilíbrio são geométricos.
- Dedos e expressão facial a partir de vídeo comum: a resolução não basta.
- Interação física entre dançarinos (pegadas, lifts).
- Roupa e cabelo com simulação.

### Riscos e questões abertas

1. **Profundidade monocular.** O rastreador inverte o lado de um joelho ou de um pé em parte dos quadros. É a principal causa da torção de coxa e pé presa no limite. Corrigir pede uma regra (continuidade, contato com o chão, outra vista) e uma medida de quanto erra.
2. **Sem verdade de referência.** Sem alguns quadros marcados à mão, não há como saber o erro real de posição nem calibrar a confiança.
3. **Proporção contra pose.** Corpos diferentes do manequim aparecem como articulações no limite (clavículas em ~40% dos quadros). É preciso separar proporção (ajustada uma vez por dançarino) de movimento (lido por quadro).
4. **Suavizar contra preservar.** Um filtro que remove ruído também remove a aceleração das paradas. O filtro atual (Savitzky–Golay de ordem 4 em 9 quadros, fase zero) mantém a batida inteira e 2/3 do primeiro harmônico de uma parada. Suavizar depois da leitura, nas articulações presas, foi testado e descartado: tirou 1/5 da aceleração dos gestos para reduzir 1/4 do tremor.
5. **Escala.** 5 s de cena levam ~3,5 min entre leitura e render. Um vídeo inteiro com vários dançarinos pede render em lotes ou em paralelo.

### Marcos

| Marco | Entrega | Pronto quando |
|---|---|---|
| M0 | Leitura de pontos (`load_keypoints`), sem saltos, timing exato | Feito |
| M1 | Confiança por ponto, origem por chave, referência manual de ~20 instantes | MPJPE medido e meta revisada |
| M2 | Clavícula ajustada por dançarino, profundidade corrigida, pés plantados | Deslize ≤ 2 cm, tremor ≤ 1 cm |
| M3 | Grade musical (compasso, frase, seção, energia) e corte de passos em batidas | Uma biblioteca com os passos do FE!N, publicada no catálogo |
| M4 | Transições e compatibilidade entre passos | Qualquer sequência compatível toca sem salto nem colisão |
| M5 | Coreografia procedural determinística para uma faixa nova | Mesma seed, mesmo filme; paradas na batida medidas como no M0 |

### Resultado esperado

Um sistema capaz de transformar **vídeo em movimento, movimento em linguagem coreográfica e música em animação**, permitindo que personagens digitais executem danças originais ou reproduzam performances de referência com precisão, naturalidade e expressividade.

Cada etapa é medida com os mesmos critérios, e o filme mostra de onde veio cada movimento: o que foi visto, o que foi estimado e o que foi criado.
