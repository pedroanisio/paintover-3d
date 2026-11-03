# IDEAS.md checado: o que vale para nós

Data: 2 de novembro de 2026. Três agentes conferiram cada afirmação do IDEAS.md nas fontes primárias (repositórios, arquivos LICENSE, model cards, artigos). Eu conferi os pontos que dependem do nosso pipeline e do nosso vídeo. Nada foi instalado nem executado além disso.

**Atualização (mesmo dia):** o SDK não é comercial. Com isso a Decisão 1 está resolvida, e várias ferramentas que este relatório tinha separado só para benchmark passam a ser candidatas. Esta versão já reflete isso. O que continua fora: copiar código GPL ou AGPL para o SDK, licenças que proíbem o próprio uso (Sapiens2) e o modelo de corpo SMPL, cuja licença só permite pesquisa científica.

O IDEAS.md foi escrito para o pipeline V5 do zip: rastreamento 2D por fluxo óptico a partir de poses marcadas à mão. O nosso pipeline já é outro, e parte das prioridades dele já está feita aqui.

## Resumo

1. **As tecnologias existem como descritas.** As licenças também conferem, com uma ressalva: o RTMW3D, que o IDEAS trata como Apache-2.0 limpo, foi treinado com dados de uso não comercial. Como o SDK não é comercial, isso não nos impede.
2. **Com o SDK não comercial, o CoTracker3 entra.** O HTD-Refine e o GVHMR podem rodar como ferramentas separadas na pasta de trabalho, mas dependem do SMPL (licença de pesquisa científica). Por isso servem de referência para medir, não de etapa do pipeline. O código do HTD-Refine é AGPL: a ideia pode ser reimplementada, o código não pode ser copiado. O Sapiens2 continua fora (veta processamento biométrico). A licença do SAM 3.1 precisa ser lida antes de usar.
3. **O teto de qualidade do IDEAS §4 não é nosso.** O nosso vídeo não tem quadros repetidos: são 9.801 quadros com intervalos uniformes de 41,7 ms, e o filtro de quase-duplicatas do ffmpeg manteve todos. Os "93 de 240 intervalos sem mudança" eram da gravação de tela do zip.
4. **A ideia mais valiosa é preservar eventos de movimento:** otimizar a sequência inteira, mantendo os picos confiáveis e removendo o tremido. Essa ideia vem do HTD-Refine e pode ser reimplementada sem o código dele. Mas a parte que mais preserva aceleração no HTD-Refine é uma rede (PVA-Net) que vem no código AGPL e trabalha sobre SMPL, então não entra no nosso pipeline. Sem ela, o ganho é menor. Rodar o HTD-Refine inteiro como referência mostra quanto perdemos (ver "Decisão 2").
5. **Achado nosso, ao conferir:** o `analyse.py` preenche os pontos com confiança abaixo de 0,3 a partir dos quadros vizinhos e não registra quais foram preenchidos. O manequim recebe esses pontos como se fossem medidos.

## Afirmação por afirmação

| Afirmação do IDEAS | Veredito | O que difere / importa | Pode ir para o produto? |
|---|---|---|---|
| RTMW3D: 133 pontos com profundidade relativa à raiz, Apache-2.0 | Parcialmente errado | Código e pesos têm rótulo Apache-2.0, mas o treino usa COCO-WholeBody, H3WB e DNA-Rendering, todos de uso não comercial. O erro publicado (MPJPE ~56 mm no H3WB) é medido dentro do próprio conjunto de treino, não em dança | Sim (SDK não comercial) |
| "P0: rodar RTMW3D em todo quadro" | Já feito aqui | Rodamos em todos os 9.801 quadros | — |
| CoTracker3: muitos pontos, visibilidade, modo offline atravessa oclusões; CC-BY-NC | Confirmado | Pesos também CC-BY-NC. Visibilidade booleana. O modo offline pede ~20 GB ou mais para ~1000 quadros | Sim (SDK não comercial). Concorre com TAPIR, BootsTAPIR e TAPNext++ do `google-deepmind/tapnet` (Apache-2.0, com logits de oclusão e incerteza): escolher pela qualidade nas mãos |
| HTD-Refine, CVPR 2026 Oral, AGPL-3.0, refina com velocidade e aceleração | Confirmado | Também UT Austin entre os autores. Precisa de SMPL/SMPL-X vindo do GVHMR ou TRAM, das intrínsecas da câmera e de 30 fps. A aceleração vem de uma rede (PVA-Net) treinada com BEDLAM, RICH e Human3.6M, todos não comerciais. Energia: velocidade + 0,1·aceleração + pontos 2D + 1e4·jerk + 1e4·regularização | O código não (AGPL). Como ferramenta separada, serve de referência para medir; a ideia pode ser reimplementada |
| GVHMR: movimento no mundo, trajetória global, contatos; só não comercial | Confirmado | Prevê SMPL-X (licença MPI, só pesquisa científica). Prevê parada de mãos, dedos e calcanhares e prende com IK. Só uma pessoa por vez | Como referência para medir contatos e trajetória |
| SAM 3.1 separa dançarinos sobrepostos | Plausível, não provado | Saiu em 27/03/2026. A "SAM License" cobre também os pesos e não é permissiva | Ler a SAM License antes. Alternativa sem dúvida: SAM 2.1 (Apache-2.0) |
| Sapiens2, ICLR 2026, 308 pontos, licença restritiva | Confirmado | Proíbe "processamento biométrico", engenharia reversa, e dá à Meta direito de auditoria | Não |
| AIST++ e DanceTrack para avaliar | Parcialmente errado | AIST++: 1.408 sequências de um dançarino, 9 câmeras calibradas, 60 fps, mas só 17 pontos (sem mãos e pés), e a verdade é pseudo-verdade triangulada (erro médio de 6,2 px). Vídeos só para pesquisa acadêmica, com formulário. DanceTrack: só caixas e identidades, sem pontos, uso não comercial | Só para avaliação, declarando a licença |
| Metas de aceite do IDEAS §5 | Mapeadas | Correspondem a 3DPCK, PA-MPJPE, erro de aceleração, foot skating, IDF1/IDsw e acerto de ordem de profundidade. "Recall de gestos" e "correlação de velocidade" não têm métrica padrão | — |
| "StykAnimate spatial rig" como etapa final | Não se aplica | O nosso destino é o manequim do SDK. StykAnimate é GPL-3.0: não usamos | — |

## O que adotar, em ordem

Cada item usa ferramenta que podemos usar num SDK não comercial, ou é reimplementado a partir de ideia publicada.

| # | O quê | Resolve | De onde vem | Esforço |
|---|---|---|---|---|
| 1 | Confiança por ponto até o SDK: pontos com confiança baixa chegam como ausentes, não preenchidos, e o `Take` registra o que foi observado e o que foi estimado | Movimento inventado tratado como medida | zip V5 e GOAL.md | Pequeno |
| 2 | Contatos dos pés: velocidade baixa (rampa do HTD-Refine, max(0, 1 − v/0,1 m/s)) e altura perto do chão, com histerese, separando dedos e calcanhar; depois prender com `plant()` e `hold(flat=True)`, que já existem | Pés deslizando | HTD-Refine e GVHMR (ideia) | Médio |
| 3 | Profundidade invertida: manter as duas hipóteses de cada joelho e pé e escolher a sequência por Viterbi (continuidade + amplitudes) | Torção de coxa e pé presa em ~30% dos quadros | Nosso | Médio |
| 4 | Otimizar a sequência inteira nos ângulos do manequim, no lugar do filtro Savitzky–Golay: termo de dados ponderado pela confiança, penalidade de jerk desligada onde a velocidade cai bruscamente (as paradas continuam secas), amplitudes e comprimentos como restrições | Tremido sem perder aceleração | HTD-Refine sem a PVA-Net | Grande |
| 5 | Trajetória no chão com câmera parada: plano do chão, raio 2D do pé plantado intersectado com o plano, velocidade do quadril entre contatos | Figuras que não andam em profundidade | Geometria | Médio |
| 6 | Identidade entre cortes e em sobreposição: associação OC-SORT sobre as caixas YOLOX que já temos (`roboflow/trackers`, Apache-2.0); SAM 2.1 se as caixas se fundirem | Trocas de dançarino | Agente 1 | Pequeno a médio |
| 7 | Mãos perdidas: pontos do CoTracker3 ou do TAPNext++ (o que for melhor nas nossas mãos) semeados nos pulsos confiáveis, usados onde a confiança do RTMW3D cai | Mãos em gesto rápido | co-tracker ou tapnet | Médio |

**Não adotar no SDK:** código do HTD-Refine, StykAnimate e boxmot (todos copyleft), e Sapiens2 (veta o uso). **Só como referência para medir:** HTD-Refine e GVHMR rodando inteiros, por dependerem do SMPL. Os pesos de detector treinados no DanceTrack deixam de ser problema de licença.

## Como medir sem nos enganar

Hoje só comparamos o manequim com o rastreador: isso mede a nossa leitura, não a verdade.

- **Referência própria:** cerca de 20 trechos escolhidos por gênero, oclusão e velocidade. Quadros marcados em intervalos fixos, escolhidos antes de rodar o modelo, nunca onde ele erra. Marcar também a ordem frente/trás dos membros, os intervalos de contato dos pés e os eventos de gesto e de batida.
  - Duas pessoas marcam 10% dos quadros; a concordância entre elas é o piso de ruído.
  - A referência fica congelada: nunca ajustamos filtro nem limiar nela, e há um conjunto separado para desenvolvimento.
  - O erro 2D é medido projetando o manequim, não o rastreador, para testar as duas etapas juntas.
- **AIST++** só para avaliação, com sujeitos inteiros separados, lembrando que só tem 17 pontos.
- **Sete métricas:**

  | Métrica | Meta proposta |
  |---|---|
  | PA-MPJPE | — |
  | 3DPCK a 5% da altura | 90% (factível após alinhamento; ambicioso sem ele) |
  | Erro de aceleração | O WHAM chega a 6,6 m/s² no 3DPW |
  | Foot skating em mm | O WHAM chega a 4,4 mm no EMDB |
  | Acerto da ordem de profundidade | < 10% de erro |
  | Atraso dos picos | Em ms, já medido |
  | IDF1 ou trocas de identidade | Zero trocas é realista em duo, não em multidão |

## Decisões para você

**Decisão 1: a licença do RTMW3D.** Resolvida: o SDK não é comercial, então seguimos com o RTMW3D. Registrado no GOAL.md.

**Decisão 2: até onde ir na otimização da sequência (item 4).**
- *O quê:* sem a PVA-Net, a otimização preserva as paradas só porque desliga a penalidade de jerk onde detecta uma parada. É uma heurística nossa, não o resultado publicado.
- *Opções:*
  1. Implementar e medir contra o filtro atual com as nossas métricas.
  2. Esperar a referência marcada à mão para julgar.
  3. Rodar o HTD-Refine inteiro (com GVHMR) num trecho como referência e comparar.
- *Recomendação:* fazer primeiro os itens 1 a 3, que são baratos e medem coisas que a otimização depois usa (confiança, contatos, profundidade corrigida), e só então o item 4.

## Fontes

- `github.com/facebookresearch/co-tracker` (LICENSE.md); `huggingface.co/facebook/cotracker3`; issue #126 do co-tracker
- `github.com/google-deepmind/tapnet`; `github.com/cvlab-kaist/locotrack`
- `github.com/facebookresearch/sam3` (LICENSE); `huggingface.co/facebook/sam3.1`; arXiv 2511.16719
- `github.com/facebookresearch/sam2`; `github.com/roboflow/trackers`; `github.com/noahcao/OC_SORT`; `github.com/DanceTrack/DanceTrack`
- `github.com/ant-research/HTD-Refine`; arXiv 2605.26879; `cvpr.thecvf.com/virtual/2026/oral/40351`
- `github.com/zju3dv/GVHMR` (LICENSE, docs/INSTALL.md, issue #29); arXiv 2409.06662
- `github.com/cure-lab/SmoothNet`; `github.com/rlabbe/filterpy`; DROID-SLAM (BSD-3); DPVO (MIT); Depth Anything V2-Small (Apache-2.0)
- `github.com/open-mmlab/mmpose/tree/main/projects/rtmpose3d`; arXiv 2407.08634; `github.com/Tau-J/rtmlib`; `github.com/jin-s13/COCO-WholeBody`; `github.com/wholebody3d/wholebody3d`; `dna-rendering.github.io`
- `github.com/facebookresearch/sapiens2` (LICENSE.md); arXiv 2604.21681
- `google.github.io/aistplusplus_dataset`; `aistdancedb.ongaaccel.jp/terms_of_use/`; arXiv 2101.08779; arXiv 2111.14690
