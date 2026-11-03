# Pipeline de dança: nossa versão + dancepose 0.3.0, combinadas

Data: 2026-11-02. Vídeo de teste: "FE!N" (fOGHfeRo7Iw), 9801 quadros, 16 cenas, 27 dançarinos rastreados.

## Resumo

A versão combinada pega a profundidade do MediaPipe (como o dancepose faz) e mantém o que já era nosso: o
rastreamento de várias pessoas, a escala por comprimento de osso, a escolha de sinal e o retarget para o manequim com
amplitudes de articulação. Foi acrescentado um passo novo que põe os dois pés no chão e o peso sobre os pés.

Sobre 26 dançarinos (17.204 quadros), comparando com a nossa versão anterior:

- o manequim "caindo" (centro de massa fora dos pés por vários quadros seguidos) passou de 59% para **35%** dos quadros
  (era 80% antes da correção de sinais);
- a diferença de altura entre os pés caiu de 5,1 cm para **2,7 cm**;
- quadros com alguma articulação no limite caíram de 91% para **67%**;
- o tronco deixou de inclinar sem motivo: mediana de 27° para 13°;
- tempo e aceleração dos gestos se mantiveram (aceleração 1,27 → 1,20, batidas 0,90 → 0,91).

Vídeo final com o áudio original:
`/home/pals/src/worskpace/_tmp/media-dl/fOGHfeRo7Iw/pose/out/merged/mannequins/full_beside.mp4`
(9801 quadros, 408,8 s, AAC; o original fica à esquerda e os manequins à direita).

## O que veio de cada lado

| Parte | Origem | Por quê |
|---|---|---|
| Detecção e rastreamento de várias pessoas (RTMW3D, trilhas, cenas) | nossa | o dancepose segue uma pessoa por vez |
| MediaPipe Pose Landmarker (heavy) no recorte de cada dançarino | dancepose (método) | modelo treinado contra corpos 3D (GHUM): fornece a profundidade que o RTMW3D erra |
| Escolha da pose do MediaPipe mais próxima do RTMW3D, fora da caixa escurecido | nova | no vídeo inteiro o MediaPipe pulava para o vizinho (erro de 360 px); agora erra cerca de 13 px e é usado em 98,5% dos quadros |
| Comprimento dos ossos (Taylor 2000) e escala | nossa, corrigida | o comprimento passa a ser medido com o ângulo do próprio MediaPipe; antes o tronco saía 29° fora do plano contra 4° |
| Profundidade: média ponderada entre Taylor e MediaPipe | nova | cada fonte pesa pelo seu erro |
| Sinal da profundidade (frente/trás), Viterbi `upright()` | nossa, com votos do MediaPipe | o MediaPipe vota onde é visto; o tronco tem peso 4× para não ser jogado para trás contra ele |
| Contato dos pés: calcanhar e ponta por quadro | dancepose (regra) | piso = o mais baixo entre calcanhar e ponta, com limiares de altura, velocidade e salto |
| Retarget para o manequim com amplitudes, métricas de fidelidade | nossa (SDK) | — |
| Nivelamento: os dois pés no chão quando a regra diz que estão | nova (`level.py`) | antes um pé flutuava e o corpo apoiava num pé só |
| Peso sobre os pés: quadril deslocado até 12 cm, suavizado ±4 quadros | nova (`level.py`) | reaproveita o `_steadied`/`_support` do manequim, que o SDK já tinha |
| Mãos (Hand Landmarker) | dancepose (método), **não usadas no final** | ver Limites |

Licenças: o dancepose é MIT e o MediaPipe é Apache-2.0. Nenhum código GPL entrou.

## Resultados

### Vídeo inteiro (26 dançarinos com as quatro versões; ponderado por quadros)

| Métrica | antes dos sinais | nossa anterior | combinada (sem nivelar) | **final** |
|---|---:|---:|---:|---:|
| centro de massa fora dos pés | 53% | 25% | 21% | **16%** |
| caindo (`fallen`) | 80% | 59% | 63% | **35%** |
| diferença de altura dos pés | 6,5 cm | 5,1 cm | 4,9 cm | **2,7 cm** |
| pé deslizando no chão (`slide`) | 1,14 | 0,67 | 0,64 | 0,63 |
| tremor 4–6 Hz acrescentado (`ripple`) | 1,16 cm | 0,92 cm | 0,77 cm | 0,78 cm |
| aceleração (razão p95, ideal 1) | 1,19 | 1,27 | 1,19 | 1,20 |
| velocidade (razão p95, ideal 1) | 1,08 | 1,12 | 1,11 | 1,11 |
| batidas (Beat Align, maior é melhor) | 0,91 | 0,90 | 0,93 | 0,91 |
| quadros com articulação no limite | 93% | 91% | 67% | 67% |
| inversões de profundidade do joelho por s | 1,53 | 0,12 | 0,21 | 0,21 |
| inclinação do tronco (mediana) | 25° | 27° | 13° | 13° |
| flexão do joelho (mediana) | 40° | 60° | 48° | 48° |

Sozinha, a combinação acertou a postura (tronco, joelhos, limites), mas não o equilíbrio: `fallen` subiu de 59% para 63%.
O ganho de equilíbrio vem do nivelamento e do peso sobre os pés.

### Cena 14 contra o MediaPipe sozinho (o método do dancepose), nos mesmos quadros

4 dançarinos, 428 quadros:

| Métrica | MediaPipe sozinho | nossa anterior | **final** |
|---|---:|---:|---:|
| fora dos pés | **17%** | 18% | 21% |
| caindo | 70% | 58% | **48%** |
| diferença dos pés | **4,2 cm** | 6,3 cm | 4,6 cm |
| tremor acrescentado | **0,49 cm** | 0,64 cm | 0,72 cm |
| aceleração | **1,20** | 1,30 | 1,31 |
| articulação no limite | 59% | 90% | **58%** |
| inversões de profundidade por s | 1,51 | **0,14** | 0,31 |
| inclinação do tronco | 12° | 26° | 15° |
| joelho | 28° | 64° | 43° |

Nesta cena a final cai menos que o MediaPipe e inverte a perna cinco vezes menos, mas fica um pouco atrás em quadros
fora dos pés, em tremor e em aceleração. Cada versão é medida contra os seus próprios pontos, então tremor e aceleração
dizem quanto o retarget acrescenta, não qual versão está mais perto do dançarino real. Não temos captura de movimento
deste vídeo, e por isso não há como medir o erro absoluto.

### Visual

`/home/pals/src/worskpace/_tmp/media-dl/fOGHfeRo7Iw/pose/out/merged/report/mp_p10_final.png`: colunas com a fonte, o
MediaPipe, a nossa anterior e a final, cada uma de frente e de lado. Nas linhas 2 e 6 a nossa anterior agachava onde a
dançarina está de pé, e a final fica de pé como o MediaPipe. Na linha 4 a final não joga mais o tronco para trás.

## Defeitos encontrados e corrigidos durante a combinação

1. **O MediaPipe pulava para o vizinho** em modo vídeo: agora lê até 3 corpos no recorte e fica com o mais próximo do RTMW3D.
2. **Taylor exagerava o ângulo fora do plano**, porque o comprimento vinha do percentil 97: agora usa o ângulo do MediaPipe.
3. **O tronco ia para trás** em 14–28% dos quadros, contra 1–5% no MediaPipe, porque o `upright()` virava o tronco contra
   ele. Com o peso do tronco em 4×, ficou em 1–6%.
4. **Saltos ao preencher quadros recusados**: o quadril tem dois conjuntos de ângulos para a mesma orientação (−180, −176,
   −7) e (1, 3, 166). A mistura linear entre eles girava o boneco. Agora se mistura apenas a correção, que é pequena.
5. **Correção de altura por quadro tremia** (aceleração 1,02 → 1,59 num dançarino): a diferença dos pés passou a ser
   suavizada ±2 quadros e os pés acompanham o quanto estão no chão.

## Limites (honestos)

- **Mãos não entram.** O Hand Landmarker encontra a mão em cerca de 25% dos quadros (o resto está borrado pelo
  movimento). Com palma e dedos, os quadros com articulação no limite subiram de 63% para 82–87%, e o punho bateu no
  limite em 30% dos quadros. As mãos ficam disponíveis (`OUT/hands/`), mas a qualidade não basta.
- **O contato dos pés é medido em altura de imagem**, como no dancepose: com a perspectiva, um pé atrás parece levantado.
- **O nivelamento recusa de 10% a 15% dos quadros** (o solver não alcança dentro das amplitudes). Esses quadros recebem a
  correção misturada dos vizinhos.
- **Ainda há 35% de quadros "caindo"**. Parte é real, porque dança tem saltos e passos em um pé só, e parte é erro.
  `plant()` com trajetória da raiz no chão continua pendente.
- O manequim não representa as proporções de ninguém em particular.

## Como reproduzir

Pasta: `/home/pals/src/worskpace/_tmp/media-dl/fOGHfeRo7Iw/pose/` (fora dos repositórios, porque deriva do vídeo).

```sh
# 1b: MediaPipe nos recortes (interpretador com mediapipe), cerca de 33 min
generated/venvs/pose/bin/python crops.py VIDEO parts out/merged
# 2: profundidade, sinais, contatos (pose/.venv), cerca de 1 min
.venv/bin/python analyse.py parts out/merged 1.5 0.4 && .venv/bin/python export.py out/merged
# 3: pés no chão e peso sobre os pés (interpretador do studio), cerca de 30 s por dançarino
/home/pals/src/studio/.venv/bin/python level.py out/merged
# vídeo completo com áudio, cerca de 25 min; retoma pelos pedaços em out/merged/full/
/home/pals/src/studio/.venv/bin/python full.py VIDEO out/merged
```

Os números estão em `out/merged/report/*.json`, gerados por `compare.py`.

## Próximos passos

1. Levar `level.py` para o SDK, como passo de `Take` (nivelar e equilibrar com contatos), com testes.
2. `plant()` com trajetória da raiz, que é o que falta para os 35% restantes.
3. Limite suave em `_controls` e rejeição de saltos de velocidade.
4. Empacotar o pipeline como módulo (passo 3 da missão), depois trajetória no mundo e identidade (passo 4).

O SDK não mudou nesta etapa: todo o trabalho está nos scripts da pasta `pose/`. As mudanças de `fidelity.py` (`BEARING`)
continuam sem commit.
