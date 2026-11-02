# Manequim: o que mudou depois da avaliação

Feito em 2026-11-02, test-first (TDD): cada item começou com um teste que falhava. Nada foi commitado nem enviado (push).

## Feito

| Item | O que faz agora | Onde |
|---|---|---|
| Corpo inteiro para pés presos | O quadril desce para um pé preso fora de alcance, no máximo 0,1 da perna (`LOWEST`), proporcional ao que não foi solto | `_lowered` |
| Rolagem do pé | `foot.roll_in_out` (-15 a 35°), fora do Unity: são 103 parâmetros. Um pé preso mantém a orientação toda, dentro das faixas | `LEGS`, `_kept` |
| Ponta dos pés | Um pé preso que o quadril deixa para trás sobe na ponta, até 50° (`TIPPED`), com os dedos de volta ao chão | `_tipped` |
| Soltura gradual | `plant(release=)` solta em segundos; `let_go` mistura de preso a livre | `location.plant` |
| Pé plano | `hold(flat=True)` põe o pé nivelado no chão, na altura em pé, virado para onde aponta | `Mannequin.hold` |
| Caminhada | `location.walk()` leva uma figura a um ponto ou marca, passo a passo, com cada pé plantado enquanto pisa | `location.walk`, `stepping`, `passing`, `stride` |
| Poses novas | `crouch`, `kneel`, `sit-floor`, `lie`, `run`, `wave`, `arms-crossed`, `hands-on-hips`, `phone`, `type`. Todas testadas em todos os tipos de corpo: na faixa, no chão, sem se atravessar | `POSES` |
| Faixas citadas | Faixas clínicas do VA (38 CFR 4.71), AAOS 1965 e Soucie et al. 2011; dorsiflexão 39° (Hemmerich et al. 2006, citado por Howe 2015, não conferido no artigo). As demais são faixas de trabalho, marcadas como tal | comentário antes de `_torso` |
| Crianças medidas | `teen`, `child` e `toddler` com estatura e altura sentada das medianas NHANES (Fryar et al. 2021; McDowell et al. 2009). O resto do corpo continua desenhado | `YOUNG` |
| Dedos analíticos | Um dedo leva o punho ao ponto menos o deslocamento do dedo, com a mão virada como estava; até `FINGER_ROUNDS` voltas onde uma faixa impede a mão de voltar; busca só onde isso não alcança | `reach_to` |
| Casco convexo de modelos | Um `Cloud` por peça conectada do modelo, não a caixa; um só casco acima de `PIECES` (64) peças; a caixa quando o SDK não lê o arquivo ou ele passa de `MAX_TRIANGLES` | `Model.pieces`, `Mesh.hulls` |
| Protocolo `Figure` | `report()` e `blocking()` leem a figura só por `Figure`: `stature()` e `shoulders()`. Uma figura sem `head` tem a folga medida acima do corpo inteiro | `figures.py`, `review.py`, `framing.py` |
| BVH e glTF | `save_bvh`, `load_bvh` e `save_glb` (do agente de interchange), integrados ao main; o worktree e o branch foram removidos | `interchange.py` |
| Nomes Mixamo/HumanIK | O dedo mínimo é `HandPinky`, não `HandLittle` | `_known_as` |

## Concessões que vale saber

- `arms-crossed`: com membros rígidos e um peito largo, braços cruzados baixos e sem atravessar em todos os 11 tipos só fecharam com limites mais folgados. No homem padrão, a mão para a 0,226 m do outro cotovelo (limite do teste 0,24) e o cotovelo direito fica 0,187 m abaixo do ombro (limite 0,15). Conferido em render.
- Um teste de interchange usava `spine.front_back = 20`; a extensão nova vai até 12, então passou a 10.
- O casco de uma peça só é convexo: uma cadeira feita numa peça é sólida por baixo do assento.

## Catálogo

- `examples/publish_catalog.py` voltou a rodar (decisão: opção A). O dining set publicado agora grava `seats`, então as duas versões subiram: 1.0.0 para 1.0.1 e 1.1.0 para 1.1.1. As antigas ficam como estavam, e `studio.dining-set` sem versão pega a 1.1.1. O script roda duas vezes seguidas e o catálogo verifica limpo.
- A linha do CLAUDE.md sobre o Location Book (artefato) continua lá, mas não republiquei nada, conforme sua instrução.

## Testes

Suíte completa: 1362 passaram, 2 pulados (os de srstudio), em 5 min 24 s, com a GPU. Depois das últimas mudanças (folha de
poses e linhas do README), os arquivos afetados rodaram de novo: 707 passaram.

`examples/mannequin.py` agora põe as 17 poses em duas fileiras desencontradas, com as câmeras mais altas, porque numa fileira só
as de fora saíam do quadro. As renders foram conferidas a olho, e também um close dos braços cruzados.
