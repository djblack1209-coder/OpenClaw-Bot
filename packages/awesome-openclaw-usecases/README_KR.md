<div align="center">

<img width="1500" height="500" alt="Image" src="https://github.com/user-attachments/assets/4ae57dfb-4f18-4677-9136-43bf93017250" />

<br/>
<br/>

<strong>사람들이 일상에서 OpenClaw(이전 명칭: ClawdBot, MoltBot)를 실제로 어떻게 활용하는지 알아보세요.
</strong>
<br />
<br />

[![Awesome](https://awesome.re/badge.svg)](https://awesome.re)
![Use Cases](https://img.shields.io/badge/usecases-36-blue?style=flat-square)
![Last Update](https://img.shields.io/github/last-commit/hesamsheikh/awesome-openclaw-usecases?label=Last%20Update&style=flat-square)
[![Follow on X](https://img.shields.io/badge/Follow%20on-X-000000?style=flat-square&logo=x)](https://x.com/Hesamation)
[![Discord](https://img.shields.io/badge/Discord-Open%20Source%20AI%20Builders-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/vtJykN3t)

<p><sub><a href="https://x.com/Hesamation">X에서 인사해요.</a></sub></p>
</div>

# Awesome OpenClaw 활용 사례

> **⚠️ 번역 버전 안내**
> 이 문서는 커뮤니티가 번역한 한국어 버전으로, 최신 내용과 차이가 있을 수 있습니다. 최신 정보는 [영문 원본 README](README.md)를 참고하세요.

---

OpenClaw 도입의 병목은 ~~스킬~~이 아닙니다. **내 삶을 개선할 방법을 찾는 것**입니다. 이것은 [OpenClaw](https://github.com/openclaw/openclaw)의 실제 활용 사례를 모은 커뮤니티 컬렉션입니다.

> **경고:** 여기서 참조하는 OpenClaw 스킬과 서드파티 의존성에는 심각한 보안 취약점이 있을 수 있습니다. 많은 사례가 **이 목록의 관리자가 감사하지 않은** 커뮤니티 빌드 스킬, 플러그인, 외부 저장소를 링크합니다. 항상 스킬 소스 코드를 검토하고, 요청 권한을 확인하며, API 키나 자격증명을 하드코딩하지 마세요. 보안에 대한 책임은 전적으로 본인에게 있습니다.

## 소셜 미디어

| 이름 | 설명 |
|------|------|
| [일일 Reddit 다이제스트](usecases/daily-reddit-digest.md) | 취향에 맞는 서브레딧 인기 게시물을 매일 요약해서 전달합니다. |
| [일일 YouTube 다이제스트](usecases/daily-youtube-digest.md) | 구독 채널의 새 영상을 매일 요약해서 놓치지 않게 해줍니다. |
| [X 계정 분석](usecases/x-account-analysis.md) | 내 X 계정에 대한 정성적 분석을 제공합니다. |
| [멀티소스 테크 뉴스 다이제스트](usecases/multi-source-tech-news-digest.md) | RSS, Twitter/X, GitHub, 웹 검색 등 109개 이상 소스에서 품질 점수로 랭킹된 기술 뉴스를 자동 수집·전달합니다. |

## 창작 및 빌딩

| 이름 | 설명 |
|------|------|
| [자율 미니앱 빌더](usecases/overnight-mini-app-builder.md) | 목표를 입력하면 에이전트가 일일 태스크를 생성·실행하고, 밤새 미니앱까지 빌드합니다. |
| [YouTube 콘텐츠 파이프라인](usecases/youtube-content-pipeline.md) | YouTube 채널을 위한 영상 아이디어 발굴, 리서치, 추적을 자동화합니다. |
| [멀티에이전트 콘텐츠 팩토리](usecases/content-factory.md) | Discord에서 리서치·작성·썸네일 에이전트가 각자 채널에서 협업하는 콘텐츠 파이프라인을 운영합니다. |
| [자율 게임 개발 파이프라인](usecases/autonomous-game-dev-pipeline.md) | 백로그 선택부터 구현, 등록, 문서화, git 커밋까지 교육용 게임 개발 전 과정을 자동 관리합니다. "버그 우선" 정책 적용. |
| [팟캐스트 제작 파이프라인](usecases/podcast-production-pipeline.md) | 게스트 리서치, 에피소드 개요, 쇼노트, 소셜 미디어 홍보 등 팟캐스트 전 워크플로우를 자동화합니다. |

## 인프라 및 DevOps

| 이름 | 설명 |
|------|------|
| [n8n 워크플로우 오케스트레이션](usecases/n8n-workflow-orchestration.md) | 웹훅을 통해 n8n 워크플로우에 API 호출을 위임합니다. 에이전트는 자격증명을 다루지 않으며 모든 연동을 시각적으로 관리합니다. |
| [자가 치유 홈 서버](usecases/self-healing-home-server.md) | SSH 접근, 자동 크론 작업, 자가 치유 기능을 갖춘 상시 인프라 에이전트를 홈 네트워크에서 운영합니다. |

## 생산성

| 이름 | 설명 |
|------|------|
| [자율 프로젝트 관리](usecases/autonomous-project-management.md) | STATE.yaml 패턴으로 멀티에이전트 프로젝트를 조율합니다. 서브에이전트가 오케스트레이터 없이 병렬로 작업합니다. |
| [멀티채널 AI 고객 서비스](usecases/multi-channel-customer-service.md) | WhatsApp, Instagram, 이메일, Google 리뷰를 AI 기반 통합 받은편지함으로 24/7 자동 응답합니다. |
| [전화 기반 개인 어시스턴트](usecases/phone-based-personal-assistant.md) | 전화 통화로 AI 에이전트에 접근하고, 핸즈프리 음성 어시스턴트를 어떤 전화기에서든 사용합니다. |
| [받은편지함 정리](usecases/inbox-declutter.md) | 뉴스레터를 요약해서 다이제스트 이메일로 전송합니다. |
| [개인 CRM](usecases/personal-crm.md) | 이메일과 캘린더에서 연락처를 자동 발굴·추적하고 자연어로 조회합니다. |
| [건강 증상 트래커](usecases/health-symptom-tracker.md) | 정기 알림으로 음식 섭취와 증상을 기록하고 트리거를 파악합니다. |
| [멀티채널 개인 어시스턴트](usecases/multi-channel-assistant.md) | 단일 AI 어시스턴트로 Telegram, Slack, 이메일, 캘린더를 통합 관리합니다. |
| [프로젝트 상태 관리](usecases/project-state-management.md) | 정적 Kanban 보드를 대체하는 이벤트 기반 프로젝트 추적으로 맥락을 자동 캡처합니다. |
| [동적 대시보드](usecases/dynamic-dashboard.md) | API, 데이터베이스, 소셜 미디어에서 병렬로 데이터를 수집하는 실시간 대시보드입니다. |
| [Todoist 태스크 관리자](usecases/todoist-task-manager.md) | 에이전트의 추론 및 진행 로그를 Todoist에 동기화해서 투명성을 높입니다. |
| [전화 기반 개인 어시스턴트](usecases/phone-based-personal-assistant.md) | 음성 통화나 SMS로 어떤 전화에서든 OpenClaw에 접속합니다. 캘린더 업데이트, Jira 티켓, 웹 검색 결과를 핸즈프리로 확인합니다. |
| [가족 캘린더 및 가정 어시스턴트](usecases/family-calendar-household-assistant.md) | 모든 가족 캘린더를 모닝 브리핑으로 통합하고, 메시지에서 약속을 감지하며, 가정 재고를 관리합니다. |
| [멀티에이전트 전문 팀](usecases/multi-agent-team.md) | 전략, 개발, 마케팅, 사업 전문 에이전트를 단일 Telegram 채팅으로 조율된 팀으로 운영합니다. |
| [데스크톱 Cowork로 OpenClaw 사용](usecases/aionui-cowork-desktop.md) | OpenClaw를 데스크톱 Cowork 앱으로 사용 — 통합 UI, 멀티에이전트, MCP 한 번 설정, WebUI/Telegram/Lark/钉钉(딩탁). OpenClaw가 다운되면 Telegram 또는 WebUI로 원격에서 내장 OpenClaw 배포 전문가(설치, 감지, 복구)를 사용해 해결할 수 있습니다. |
| [맞춤형 모닝 브리프](usecases/custom-morning-brief.md) | 뉴스, 할일, 콘텐츠 초안, AI 추천 액션을 매일 아침 텍스트로 받아봅니다. |
| [회의록 및 액션 아이템 자동화](usecases/meeting-notes-action-items.md) | 회의 녹취록을 구조화된 요약으로 바꾸고 Jira, Linear, Todoist에 담당자에게 맞춰 자동으로 태스크를 생성합니다. |
| [습관 트래커 및 책임 코치](usecases/habit-tracker-accountability-coach.md) | Telegram 또는 SMS로 매일 능동적으로 체크인하며 습관을 추적하고 스트릭을 유지하며 진행 상황에 맞춰 톤을 조절합니다. |
| [세컨드 브레인](usecases/second-brain.md) | 봇에 문자를 보내 기억하고, 커스텀 Next.js 대시보드에서 모든 기억을 검색합니다. |
| [이벤트 참석 확인](usecases/event-guest-confirmation.md) | 이벤트 게스트에게 한 명씩 전화해 참석 여부를 확인하고 메모를 모아 요약합니다 — AI 음성 통화로 전 과정 자동화. |
| [전화 알림](usecases/phone-call-notifications.md) | 에이전트 알림을 실제 전화로 받기 — 모닝 브리핑, 가격 하락, 긴급 이메일을 양방향 대화로 전달합니다. |

## 리서치 및 학습

| 이름 | 설명 |
|------|------|
| [AI 실적 발표 트래커](usecases/earnings-tracker.md) | 자동 미리 보기, 알림, 상세 요약으로 테크/AI 기업 실적 발표를 추적합니다. |
| [개인 지식베이스 (RAG)](usecases/knowledge-base-rag.md) | URL, 트윗, 기사를 채팅에 드롭해서 검색 가능한 지식베이스를 구축합니다. |
| [시장 조사 및 제품 팩토리](usecases/market-research-product-factory.md) | Last 30 Days 스킬로 Reddit과 X에서 실제 페인포인트를 발굴하고 MVP를 빌드합니다. |
| [사전 빌드 아이디어 검증기](usecases/pre-build-idea-validator.md) | 새로운 것을 빌드하기 전에 GitHub, HN, npm, PyPI, Product Hunt를 자동 스캔합니다. 시장이 포화 상태면 중단, 열려 있으면 진행합니다. |
| [시맨틱 메모리 검색](usecases/semantic-memory-search.md) | 하이브리드 검색과 자동 동기화로 OpenClaw 마크다운 메모리 파일에 벡터 기반 시맨틱 검색을 추가합니다. |

## 금융 및 트레이딩

| 이름 | 설명 |
|------|------|
| [Polymarket 자동 매매](usecases/polymarket-autopilot.md) | 백테스팅, 전략 분석, 일일 성과 리포트가 포함된 예측 시장 자동 페이퍼 트레이딩입니다. |

## 🤝 기여하기

기여를 환영합니다! 가이드라인은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

- 새 활용 사례 추가
- 기존 사례 개선

> 직접 사용해보고 검증한 사례만 제출해주세요 (최소 하루 이상). 삶을 실제로 개선하는 진짜 아이디어를 소중히 여깁니다.
>
> **참고:** 암호화폐 관련 사례는 받지 않습니다.
