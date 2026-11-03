# Research findings: How to take our dance reconstruction from 3/10 toward 9/10

I researched current computer-vision and motion-reconstruction projects, including work released in 2026. The findings point to a substantially better architecture than our V1–V5 approach.

The biggest opportunity is combining anatomical pose detection, long-range point tracking, and a motion solver that explicitly preserves velocity and acceleration.

Our current system relies too heavily on optical flow and sparse manual poses. The models below address different parts of that problem.

## 1. The six most relevant technologies

[\[Paper\] RTMW: Real-Time Multi-Person 2D and 3D Whole-body Pose Estimation (arXiv’24) - Dongle’s 개발노트](https://images.openai.com/static-rsc-4/Vew0O8I41I050yZyEbz26AWRQ3I9p4i5ZRGabfvjXVW9LQcd6ycLi8S63Y6OYViqgC8v4LQyuazsH6HCwi5hbyfgftL24pwy8cTCmpzW_1FgyYDqx_fUGPHq-rr1g78MFKVX4vMvJNo5fjZ85Fw5sMxFn2QN519wWGH7Q_pilKE?purpose=inline)

[RTMW3D / MMPose](https://github.com/open-mmlab/mmpose?utm_source=chatgpt.com)

Start here

Detects 133 whole-body landmarks, including hands and feet, with root-relative 3D coordinates. This is a much stronger foundation for tracking the actual choreography than our 15-landmark annotations.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://arxiv.org\&sz=32)

arxiv.org+1



Solves: missing body joints, approximate limb depth

[CoTracker3 Revolutionizes Point Tracking by Simplifying Architectures and Leveraging Real Video Data](https://images.openai.com/static-rsc-4/HrXr3jr8NvsErPcOiOmFrM3b3qRItKyNhqy_fCwBWtc1vSbo8hDIp37gVVh8bUgw8W6H-5P-frhCJAc0rTnA3vP2e1-6WsR5gFJadC47DUcGdgxqi1lqxIhuMrwz_C8bz3nF8r_OPKKg-bQ3FYa4122Qnp2qWIgUL943XIkv2bc?purpose=inline)

[CoTracker3](https://github.com/facebookresearch/co-tracker?utm_source=chatgpt.com)

Tracks many image points jointly over time, with visibility estimates. Its offline model uses surrounding frames to recover trajectories through temporary occlusions. Unlike our previous optical-flow tracker, it does not rely on a single local feature per joint.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://openaccess.thecvf.com\&sz=32)

openaccess.thecvf.com



Solves: disappearing hands, tracking drift, temporary occlusion

[CVPR 2026 Oral 最佳论文候选 | 浙大&蚂蚁提出 HTD-Refine：对齐高阶动力学，让单目人体动作恢复告别“滑步”与“抖动” | 雷峰网](https://images.openai.com/static-rsc-4/vXaKqnm3vrcHpRI0osQZ2MKZDv3Zbl_Ezywv4gxMEVhgkHfvQdgqdzeJCzOLjxel3gcP5WaJLF_WVJc-io3bm1P0iyWwlGfFsNpDqHMBHaAFRXkmWfgJ_G1PcDATJhJ7sYTDnBTPeRCO-nn6EHQMWacNcMocSlwFLEXAuNFvpkg?purpose=inline)

[HTD-Refine — CVPR 2026](https://github.com/ant-research/HTD-Refine?utm_source=chatgpt.com)

The most directly relevant research for your speed requirement. It refines recovered motion using 3D velocity and acceleration, rather than optimizing only joint positions. It specifically targets overly smooth, dynamically incorrect motion. Code and documentation are available.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



Solves: lost acceleration, mechanical timing, excessive smoothing

[GVHMR——基于重力-视角坐标的人体运动恢复：从RGB视频中提取人的SMPL轨迹(包含人体姿态估计WHAM、手势估计HaMeR的详解) - 技术栈](https://images.openai.com/static-rsc-4/SD9otYB0qBA8dVx-8jCUUBv1lHzd-zMyFcbdsn5SH7E_kYGP8dUIL24lN8aI5lBd8V_PIiEHTBPC4JPv2tXWvybpRDbfqDLzm-Tq0buiOr8RzQauAKhCifx6k7R86tveffSTbuO-vCyrCWfjkVqrtKqVDaFcGi9rzqelyKern3Q?purpose=inline)

[GVHMR](https://github.com/zju3dv/GVHMR?utm_source=chatgpt.com)

Reconstructs world-grounded human motion from monocular video, including orientation and global trajectory. Its stationary-contact prediction is useful for reducing foot sliding and handling rapid movement.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://pubmed.ncbi.nlm.nih.gov\&sz=32)

PubMed+1



Solves: body rotation, root motion, contact consistency

[SAM 3D Body - Crie Modelos 3D de Corpo Humano a partir de Fotos Online](https://images.openai.com/static-rsc-4/i0kP4xfhDDbBcFfVBLz8qKZTrRr4cqDQDa1Hrxuyvg4i2KT_R9svo2c5ZxbEG0SiJaujsSPsJraGx7HCFsTAjqhPXhs8skWNZwKkTLHSmaTdS4Qha367j7009OYii6JvDVylglZhC28SPEruHv7xqLjQ8ZkUYorO1Vu1hVR9ItY?purpose=inline)

[SAM 3.1](https://github.com/facebookresearch/sam3?utm_source=chatgpt.com)

Tracks segmented objects with persistent identities. Its March 2026 update supports joint processing of multiple objects, making it a candidate for keeping two dancers separated when they overlap.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://ai.meta.com\&sz=32)

ai.meta.com



Solves: dancer identity confusion and overlapping silhouettes

[Sapiens: Foundation for Human Vision Models by Meta](https://images.openai.com/static-rsc-4/hcFC8F53AVwHj_DFhKqEotpo1MoitlDuCNBLlTy08pRv0zWqO1-6RV9XDehMK1KfcV9C2VFY4aayNFBqEhODSWtElgyK9NGEsLsdP_5iH2Rzn7LaBdpOug0CU36WTK763mfEWA5JwvsDndJSb8zj4t-5I_fR_zYUlLs5OBt0TSE?purpose=inline)

[Sapiens2 — ICLR 2026](https://github.com/facebookresearch/sapiens2?utm_source=chatgpt.com)

A high-resolution human understanding model family with 308-keypoint pose estimation, body-part segmentation, surface normals and pointmaps. Worth benchmarking as a more expensive alternative for frames where smaller pose models fail.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



Solves: detailed articulation and difficult pose localization

These technologies are complementary, not six models that necessarily need to run on every frame.

## 2. What I would change in our architecture

Original dance footage

Decode genuine frame timestamps, cuts and repeated frames

RTMW3D

Body, hands, feet and depth hypotheses

CoTracker3

Joint neighborhoods, visibility and trajectories

Confidence-aware motion fusion

Person identity, joint confidence, occlusion, re-detection

GVHMR → HTD-Refine

3D orientation, velocity, acceleration, physical constraints

StykAnimate spatial rig

Hierarchical rotation, actual depth, IK, original timing

A key implementation detail: CoTracker3 should track multiple points around each elbow, wrist and ankle, not just one point at its estimated center. We can use the resulting cluster to reject drifting tracks and reinitialize from a confident pose detection.

The 3D stage should operate separately on each dancer, then reconcile their positions in a shared scene. HTD-Refine's current demo assumes one primary subject, so we would need to provide separate person boxes and matching initial 3D motion tracks for our two-dancer sequence.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



## 3. The most important new concept: preserve movement events

The V5 pipeline primarily evaluates joint position error. But a 30-frame sequence can have reasonably accurate positions while entirely missing a fast wrist flick.

I would add an event-aware motion reconstruction stage, where each joint trajectory is analyzed for:

| Signal               | Why it matters                                                 |
| -------------------- | -------------------------------------------------------------- |
| Velocity             | Reproduces how quickly a limb travels                          |
| Acceleration         | Captures explosive starts and stops                            |
| Direction reversal   | Preserves rapid changes of gesture                             |
| Angular velocity     | Reproduces twisting, elbow bending and turns                   |
| Contact state        | Keeps feet planted or correctly airborne                       |
| Occlusion confidence | Prevents invented movements from being treated as measurements |

Rather than smoothing the entire trajectory, the optimizer should preserve reliable motion peaks while suppressing tracking jitter.

HTD-Refine is the most promising reference implementation for this. Its optimization balances position and high-order dynamics with constraints, rather than naively taking derivatives of noisy keypoints.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://zju3dv.github.io\&sz=32)

Project Page



## 4. The recording itself imposes a ceiling

In the previous analysis of your footage, 93 of 240 frame intervals in the test section had little visual change. This does not mean we have exactly 93 duplicate frames, but it suggests the recording has temporal information loss.

No pose-estimation model can reliably recover every motion that happened entirely between captured images.

The best practical improvements are to preserve presentation timestamps, avoid averaging across abrupt changes, and obtain the original higher-frame-rate clip if one exists. Frame interpolation such as RIFE can improve presentation smoothness, but it may invent incorrect hand positions around fast motion and occlusion.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://huggingface.co\&sz=32)

FuryTMP/RIFE_fp32 at main



## 5. How to benchmark without fooling ourselves

We need to stop judging progress only from a visually pleasant overlay.

I recommend annotating approximately 40–60 strategically selected frames from the same eight-second clip, concentrating on high-speed gestures, overlaps and direction reversals. Those frames should be excluded from any manual correction or optimization targets used for testing.

| Metric                          | Proposed acceptance target            |
| ------------------------------- | ------------------------------------- |
| Visible joint accuracy          | 90% within 5% of dancer height        |
| Major gesture recall            | ≥90% of reviewed gesture events       |
| Movement-peak timing            | Within ±1 source frame                |
| Velocity-profile correlation    | ≥0.85 against reviewed trajectories   |
| Dancer identity swaps           | Zero                                  |
| Incorrect limb front/back order | Fewer than 10% of reviewed occlusions |
| Foot-contact errors             | Minimal visible planted-foot sliding  |

For broader testing, [AIST++](https://google.github.io/aistplusplus_dataset/?utm_source=chatgpt.com) provides multiview dance sequences with 3D motion and 2D/3D keypoints, while [DanceTrack](https://dancetrack.github.io/?utm_source=chatgpt.com) specifically challenges multi-person identity tracking under diverse, irregular movement.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://google.github.io\&sz=32)

google.github.io+1



## 6. Implementation priorities

| Priority | Work                                   | Expected contribution                 |
| -------- | -------------------------------------- | ------------------------------------- |
| P0       | RTMW3D inference on every source frame | High — anatomical tracking            |
| P0       | CoTracker3 offline tracking fusion     | High — fewer lost gestures            |
| P0       | Independent validation and overlays    | High — trustworthy progress           |
| P1       | HTD-Refine temporal dynamics           | Very high — speed fidelity            |
| P1       | GVHMR world-space motion               | High — depth and rotation             |
| P1       | StykAnimate spatial-rig exporter       | High — correct perspective            |
| P2       | SAM 3.1 occlusion handling             | Medium — targeted difficult intervals |
| P2       | Sapiens2 difficult-frame fallback      | Potentially high, but expensive       |

One caveat for a production tool: the licenses matter. MMPose is Apache 2.0, but CoTracker3's main implementation is CC-BY-NC, GVHMR permits noncommercial use only without separate permission, and HTD-Refine uses AGPL-3.0-only. Sapiens2 also has its own restrictive model license. We can benchmark these technologies for research, but a commercial product requires a separate licensing review or appropriately licensed alternatives.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub+4



## My proposed V6

I would build two competing pipelines on the same eight-second section.

EXPERIMENT A

High-fidelity 2D/2.5D

RTMW3D + CoTracker3 + confidence-aware fusion

Goal: recover substantially more gestures and reliable per-frame trajectories before investing in full 3D reconstruction.

EXPERIMENT B

3D motion fidelity

Experiment A + GVHMR + HTD-Refine

Goal: preserve fast 3D motion, torso turns, depth order and planted-foot behavior.

Both should export identical landmark schemas, a timestamped joint timeline, a 30 FPS skeleton overlay, and an editable StykAnimate project. That makes the comparison meaningful rather than subjective.

The central lesson from the research: we should no longer ask our interpolator to guess the choreography. We need to measure the body as often as the footage allows, track those observations consistently, reconstruct the missing 3D motion with explicit uncertainty, and only then animate the character.

That is the most credible path from V5's missing gestures toward a genuinely impressive motion-transfer system.