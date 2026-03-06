# Paper-Morning Web Console — UI 개선 구현 계획서

> **파일**: `web_app.py` 단일 파일만 수정  
> **원칙**: 기존 기능 100% 유지 / 심미성·편의성만 개선  
> **목표 디자인**: 깔끔하고 세련된 SaaS 대시보드 느낌 (Linear, Notion, Vercel 참고)  
> **버전**: paper-morning v0.1.4

---

## 전체 디자인 방향

### 비전
- **Before**: 기능 위주의 최소형 유틸리티 UI (흰 배경, 파란 버튼 나열)
- **After**: 절제된 그레이 팔레트, 미세한 그림자, 부드러운 인터랙션이 있는 세련된 내부 도구 UI

### 참고 디자인 키워드
- **Notion**식 넓은 여백과 깔끔한 타이포그래피
- **Linear**식 진한 배경의 사이드바 + 밝은 콘텐츠 영역 대비
- **Vercel**식 미니멀 버튼과 pill 배지
- 한국어 텍스트에 맞는 자연스러운 폰트 (`Pretendard` 우선, 없으면 `Inter`)

---

## 구현 지침

> 아래 모든 변경은 `web_app.py` 내 `BASE_TEMPLATE` 문자열을 교체하고,  
> `build_home_body()`, `settings()`, `topics()`, `manual()` 함수의 HTML 문자열을 수정하는 방식으로 구현합니다.

---

## STEP 1: BASE_TEMPLATE 전면 교체

`BASE_TEMPLATE = """..."""` 전체를 아래로 교체합니다.

### 1-1. `<head>` 영역 — Google Fonts + 새 CSS 변수

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ title }}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    /* ── Design Tokens ───────────────────────────────── */
    :root {
      --bg:           #f4f5f7;        /* 연한 쿨그레이 페이지 배경 */
      --sidebar-bg:   #1a1d23;        /* 다크 사이드바 */
      --sidebar-text: #a8b3c4;        /* 사이드바 비활성 텍스트 */
      --sidebar-active-bg:  #2a2f3a;
      --sidebar-active-text: #ffffff;
      --card:         #ffffff;
      --card-border:  #e5e8ef;
      --text:         #111827;        /* 거의 검정에 가까운 메인 텍스트 */
      --text-sub:     #6b7280;        /* 보조 텍스트 */
      --accent:       #4f6ef7;        /* 밝은 인디고/파랑 */
      --accent-hover: #3b55e0;
      --accent-bg:    #eef2ff;
      --ok-bg:        #ecfdf5;
      --ok-text:      #065f46;
      --ok-border:    #6ee7b7;
      --danger-bg:    #fef2f2;
      --danger-text:  #991b1b;
      --danger-border:#fca5a5;
      --warn-bg:      #fffbeb;
      --warn-text:    #92400e;
      --radius-sm:    6px;
      --radius-md:    10px;
      --radius-lg:    14px;
      --shadow-sm:    0 1px 2px rgba(0,0,0,0.05);
      --shadow-md:    0 4px 12px rgba(0,0,0,0.07);
      --shadow-lg:    0 8px 24px rgba(0,0,0,0.09);
      --transition:   0.15s ease;
      --sidebar-width:220px;
    }

    /* ── Reset & Base ────────────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: 'Inter', 'Pretendard', 'Segoe UI', sans-serif;
      font-size: 14px;
      line-height: 1.6;
      background: var(--bg);
      color: var(--text);
      display: flex;
      min-height: 100vh;
    }

    /* ── Sidebar Navigation ──────────────────────────── */
    .sidebar {
      width: var(--sidebar-width);
      min-height: 100vh;
      background: var(--sidebar-bg);
      display: flex;
      flex-direction: column;
      padding: 0;
      position: fixed;
      top: 0; left: 0; bottom: 0;
      z-index: 100;
    }
    .sidebar-logo {
      padding: 20px 20px 16px;
      border-bottom: 1px solid rgba(255,255,255,0.07);
    }
    .sidebar-logo .logo-title {
      font-size: 13px;
      font-weight: 600;
      color: #ffffff;
      letter-spacing: 0.02em;
    }
    .sidebar-logo .logo-version {
      font-size: 11px;
      color: var(--sidebar-text);
      margin-top: 2px;
    }
    .sidebar-nav {
      padding: 12px 10px;
      flex: 1;
    }
    .sidebar-nav a {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 9px 12px;
      border-radius: var(--radius-sm);
      color: var(--sidebar-text);
      text-decoration: none;
      font-size: 13.5px;
      font-weight: 500;
      transition: background var(--transition), color var(--transition);
      margin-bottom: 2px;
    }
    .sidebar-nav a:hover {
      background: rgba(255,255,255,0.06);
      color: var(--sidebar-active-text);
    }
    .sidebar-nav a.active {
      background: var(--sidebar-active-bg);
      color: var(--sidebar-active-text);
    }
    .sidebar-nav a .nav-icon { font-size: 16px; flex-shrink: 0; }

    /* ── Main Content ────────────────────────────────── */
    .main-content {
      margin-left: var(--sidebar-width);
      flex: 1;
      padding: 32px 36px 48px;
      max-width: calc(100vw - var(--sidebar-width));
    }
    .page-header {
      margin-bottom: 24px;
    }
    .page-header h1 {
      font-size: 20px;
      font-weight: 600;
      margin: 0 0 4px;
    }
    .page-header p {
      font-size: 13px;
      color: var(--text-sub);
      margin: 0;
    }

    /* ── Cards ───────────────────────────────────────── */
    .card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: var(--radius-md);
      padding: 20px 22px;
      margin-bottom: 16px;
      box-shadow: var(--shadow-sm);
    }
    .card-title {
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-sub);
      margin: 0 0 14px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--card-border);
    }

    /* ── Buttons ─────────────────────────────────────── */
    button, .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: var(--radius-sm);
      padding: 8px 14px;
      font-size: 13.5px;
      font-weight: 500;
      font-family: inherit;
      cursor: pointer;
      transition: background var(--transition), transform var(--transition), box-shadow var(--transition);
      box-shadow: 0 1px 2px rgba(79,110,247,0.25);
    }
    button:hover:not(:disabled) {
      background: var(--accent-hover);
      box-shadow: 0 3px 8px rgba(79,110,247,0.3);
      transform: translateY(-1px);
    }
    button:active:not(:disabled) { transform: translateY(0); }
    button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
    .btn-ghost {
      background: transparent;
      color: var(--text-sub);
      border: 1px solid var(--card-border);
      box-shadow: none;
    }
    .btn-ghost:hover:not(:disabled) {
      background: var(--bg);
      color: var(--text);
      box-shadow: none;
    }
    .btn-danger {
      background: var(--danger-bg);
      color: var(--danger-text);
      border: 1px solid var(--danger-border);
      box-shadow: none;
    }
    .btn-danger:hover:not(:disabled) {
      background: #fee2e2;
      box-shadow: none;
    }
    .btn-success {
      background: #059669;
      box-shadow: 0 1px 2px rgba(5,150,105,0.25);
    }
    .btn-success:hover:not(:disabled) {
      background: #047857;
      box-shadow: 0 3px 8px rgba(5,150,105,0.3);
    }

    /* ── Badges / Pills ──────────────────────────────── */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 99px;
      font-size: 12px;
      font-weight: 500;
    }
    .badge-idle    { background: #f3f4f6; color: var(--text-sub); }
    .badge-running { background: #dbeafe; color: #1d4ed8; }
    .badge-ok      { background: var(--ok-bg); color: var(--ok-text); }
    .badge-danger  { background: var(--danger-bg); color: var(--danger-text); }

    /* ── Forms ───────────────────────────────────────── */
    input[type="text"],
    input[type="password"],
    input[type="number"],
    input[type="time"],
    input[type="email"],
    select,
    textarea {
      width: 100%;
      box-sizing: border-box;
      padding: 8px 10px;
      border: 1px solid var(--card-border);
      border-radius: var(--radius-sm);
      font-size: 13.5px;
      font-family: inherit;
      color: var(--text);
      background: #fff;
      transition: border-color var(--transition), box-shadow var(--transition);
      outline: none;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(79,110,247,0.12);
    }
    textarea {
      min-height: 80px;
      font-family: 'Consolas', 'Menlo', monospace;
      font-size: 12.5px;
      resize: vertical;
    }
    input[type="checkbox"] {
      width: 16px; height: 16px;
      accent-color: var(--accent);
      cursor: pointer;
    }
    label { font-size: 13px; color: var(--text-sub); }

    /* ── Settings Table ──────────────────────────────── */
    .settings-grid { display: flex; flex-direction: column; gap: 0; }
    .settings-row {
      display: grid;
      grid-template-columns: 240px 1fr;
      gap: 16px;
      align-items: start;
      padding: 12px 0;
      border-bottom: 1px solid var(--card-border);
    }
    .settings-row:last-child { border-bottom: none; }
    .settings-label { padding-top: 6px; }
    .settings-label strong {
      display: block;
      font-size: 13.5px;
      font-weight: 500;
      color: var(--text);
    }
    .settings-label small {
      display: block;
      margin-top: 2px;
      font-size: 12px;
      color: var(--text-sub);
      line-height: 1.4;
    }

    /* ── Section Divider in Settings ─────────────────── */
    .settings-section-header {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-sub);
      margin: 20px 0 4px;
    }
    .settings-section-header:first-child { margin-top: 0; }

    /* ── Progress Bar ────────────────────────────────── */
    .progress-track {
      background: var(--bg);
      border: 1px solid var(--card-border);
      border-radius: 99px;
      height: 8px;
      overflow: hidden;
      margin: 10px 0;
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), #7c3aed);
      border-radius: 99px;
      transition: width 0.4s ease;
    }

    /* ── Flash / Alerts ──────────────────────────────── */
    .flash {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 12px 14px;
      border-radius: var(--radius-sm);
      margin-bottom: 14px;
      font-size: 13.5px;
      animation: fadeIn 0.25s ease;
    }
    .flash.ok      { background: var(--ok-bg); color: var(--ok-text); border: 1px solid var(--ok-border); }
    .flash.danger  { background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border); }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: none; } }

    /* ── Pre / Code blocks ───────────────────────────── */
    pre {
      background: #0f1117;
      color: #d1d5db;
      border-radius: var(--radius-md);
      padding: 16px;
      font-size: 12.5px;
      font-family: 'Consolas', 'Menlo', monospace;
      white-space: pre-wrap;
      word-break: break-all;
      max-height: 420px;
      overflow-y: auto;
      margin: 0;
    }

    /* ── Table (Topic Editor) ────────────────────────── */
    table { width: 100%; border-collapse: collapse; }
    thead th {
      text-align: left;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--text-sub);
      padding: 8px 10px;
      border-bottom: 2px solid var(--card-border);
    }
    tbody tr {
      transition: background var(--transition);
    }
    tbody tr:hover { background: #f9fafb; }
    tbody td {
      padding: 8px 10px;
      vertical-align: top;
      border-bottom: 1px solid var(--card-border);
    }
    tbody tr:last-child td { border-bottom: none; }

    /* ── Action Button Row ───────────────────────────── */
    .action-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    }
    .action-card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: var(--radius-md);
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      box-shadow: var(--shadow-sm);
    }
    .action-card .action-icon { font-size: 22px; }
    .action-card .action-label { font-weight: 600; font-size: 13.5px; }
    .action-card .action-desc { font-size: 12px; color: var(--text-sub); line-height: 1.4; }
    .action-card button { margin-top: 8px; }

    /* ── Status Panel ────────────────────────────────── */
    .status-panel {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 10px;
      margin-bottom: 14px;
    }
    .status-kv { }
    .status-kv .kv-label { font-size: 11px; color: var(--text-sub); margin-bottom: 2px; }
    .status-kv .kv-value { font-size: 13px; font-weight: 500; }

    /* ── Markdown body ───────────────────────────────── */
    .md-body h1 { font-size: 20px; margin-top: 1.4em; }
    .md-body h2 { font-size: 17px; margin-top: 1.3em; border-bottom: 1px solid var(--card-border); padding-bottom: 6px; }
    .md-body h3 { font-size: 15px; margin-top: 1.2em; }
    .md-body code {
      background: #f3f4f6; color: #374151;
      padding: 2px 5px; border-radius: 4px;
      font-size: 12.5px; font-family: 'Consolas', monospace;
    }
    .md-body pre { margin: 12px 0; }
    .md-body pre code { background: transparent; color: inherit; padding: 0; }
    .md-body table { margin: 12px 0; }
    .md-body a { color: var(--accent); }

    /* ── Responsive ──────────────────────────────────── */
    @media (max-width: 900px) {
      .sidebar { display: none; }
      .main-content { margin-left: 0; max-width: 100vw; padding: 16px; }
      .action-grid { grid-template-columns: 1fr; }
      .status-panel { grid-template-columns: 1fr 1fr; }
      .settings-row { grid-template-columns: 1fr; gap: 4px; }
    }

    /* ── Utilities ───────────────────────────────────── */
    .small { font-size: 12px; color: var(--text-sub); }
    .text-ok { color: var(--ok-text); }
    .text-danger { color: var(--danger-text); }
    .mt-8 { margin-top: 8px; }
    .mt-12 { margin-top: 12px; }
    .gap-8 { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  </style>
</head>
<body>
```

### 1-2. `<body>` 내부 — 사이드바 + 메인 레이아웃

```html
  <aside class="sidebar">
    <div class="sidebar-logo">
      <div class="logo-title">📄 Paper Morning</div>
      <div class="logo-version">v{{ app_version }}</div>
    </div>
    <nav class="sidebar-nav">
      <a href="{{ url_for('home') }}" class="{{ 'active' if active_page == 'home' else '' }}">
        <span class="nav-icon">🏠</span> Home
      </a>
      <a href="{{ url_for('settings') }}" class="{{ 'active' if active_page == 'settings' else '' }}">
        <span class="nav-icon">⚙️</span> Settings
      </a>
      <a href="{{ url_for('topics') }}" class="{{ 'active' if active_page == 'topics' else '' }}">
        <span class="nav-icon">📋</span> Topic Editor
      </a>
      <a href="{{ url_for('manual') }}" class="{{ 'active' if active_page == 'manual' else '' }}">
        <span class="nav-icon">📖</span> Manual
      </a>
    </nav>
  </aside>

  <div class="main-content">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash {{ category }}">
            {{ '✅' if category == 'ok' else '❌' }} {{ message }}
          </div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {{ body|safe }}
  </div>

  <script>window.APP_TOKEN = "{{ auth_token }}";</script>
</body>
</html>
```

### 1-3. `render_page()` 함수 시그니처 변경

이제 `render_page`가 `active_page`와 `app_version`을 템플릿에 전달해야 합니다.

```python
# 현재
def render_page(title: str, body: str):
    return render_template_string(BASE_TEMPLATE, title=title, body=body, auth_token=APP_AUTH_TOKEN)

# 변경 후
def render_page(title: str, body: str, active_page: str = ""):
    return render_template_string(
        BASE_TEMPLATE,
        title=title,
        body=body,
        auth_token=APP_AUTH_TOKEN,
        active_page=active_page,
        app_version=APP_VERSION,
    )
```

---

## STEP 2: Home 페이지 (`build_home_body()`)

`build_home_body()` 함수의 return 직전에 사용하는 HTML 문자열 전체를 교체합니다.  
`render_page()` 호출부도 `active_page="home"` 을 추가합니다.

```python
@app.route("/")
def home():
    return render_page(APP_TITLE, build_home_body(), active_page="home")
```

새 `build_home_body()` HTML:

```html
<div class="page-header">
  <h1>Dashboard</h1>
  <p>논문 수집·발송을 수동으로 실행하거나, 스케줄러 상태를 확인합니다.</p>
</div>

<!-- Scheduler Status (상단 1줄 배지) -->
<div class="card" style="display:flex; align-items:center; gap:10px; padding:14px 18px;">
  <span id="sched-icon" style="font-size:18px;">📅</span>
  <span id="sched-text" style="font-size:13.5px; font-weight:500;">__SCHEDULER_STATUS__</span>
</div>

<!-- 3개 Action Card -->
<div class="action-grid">
  <div class="action-card">
    <span class="action-icon">🔍</span>
    <span class="action-label">Dry-Run</span>
    <span class="action-desc">메일 발송 없이 오늘 수집·선별 결과만 확인합니다.</span>
    <button id="btn-dry" onclick="startJob('dry_run')">실행</button>
  </div>
  <div class="action-card">
    <span class="action-icon">📨</span>
    <span class="action-label">Send Now</span>
    <span class="action-desc">지금 즉시 실제 논문 리포트 메일을 1회 발송합니다.</span>
    <button id="btn-send" class="btn-success" onclick="startJob('send_now')">발송</button>
  </div>
  <div class="action-card">
    <span class="action-icon">🔄</span>
    <span class="action-label">Reload Scheduler</span>
    <span class="action-desc">변경된 발송 시간·설정을 스케줄러에 다시 반영합니다.</span>
    <button id="btn-reload" class="btn-ghost" onclick="startJob('reload_scheduler')">리로드</button>
  </div>
</div>

<!-- Task Status Panel -->
<div class="card">
  <p class="card-title">Task Status</p>
  <div class="status-panel">
    <div class="status-kv">
      <div class="kv-label">상태</div>
      <div class="kv-value" id="status-badge"><span class="badge badge-idle">⬜ 대기 중</span></div>
    </div>
    <div class="status-kv">
      <div class="kv-label">시작 시각</div>
      <div class="kv-value" id="status-started">—</div>
    </div>
    <div class="status-kv">
      <div class="kv-label">완료 시각</div>
      <div class="kv-value" id="status-finished">—</div>
    </div>
  </div>
  <div class="progress-track">
    <div class="progress-fill" id="job-progress"></div>
  </div>
  <p id="job-message" style="margin:8px 0 0; font-size:13px; color:var(--text-sub);">No running task.</p>
  <p id="job-error" class="text-danger" style="margin:4px 0 0; font-size:13px;"></p>
</div>

<!-- Last Dry-Run Output -->
<div class="card">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
    <p class="card-title" style="margin:0; border:none; padding:0;">Last Dry-Run Output</p>
    <button class="btn-ghost" onclick="toggleOutput()" id="btn-toggle" style="padding:4px 10px; font-size:12px;">접기 ▲</button>
  </div>
  <div id="output-wrap">
    <pre id="output-pre">__LAST_DRY_OUTPUT__</pre>
  </div>
</div>

<script>
  let outputVisible = true;
  function toggleOutput() {
    const wrap = document.getElementById('output-wrap');
    const btn  = document.getElementById('btn-toggle');
    outputVisible = !outputVisible;
    wrap.style.display = outputVisible ? '' : 'none';
    btn.textContent = outputVisible ? '접기 ▲' : '펼치기 ▼';
  }

  const JOB_LABEL = { dry_run: 'Dry-Run', send_now: 'Send Now', reload_scheduler: 'Reload Scheduler', none: '' };

  async function fetchStatus() {
    try {
      const res  = await fetch('__API_STATUS__');
      const data = await res.json();
      renderStatus(data);
    } catch (err) {
      document.getElementById('job-message').textContent = 'Failed to load job status.';
    }
  }

  function setButtonsDisabled(disabled) {
    ['btn-dry','btn-send','btn-reload'].forEach(id => {
      document.getElementById(id).disabled = disabled;
    });
  }

  function renderStatus(data) {
    const p        = Math.max(0, Math.min(100, Number(data.progress || 0)));
    const running  = Boolean(data.running);
    const hasError = Boolean(data.error);
    const kind     = data.kind || 'none';

    document.getElementById('job-progress').style.width = p + '%';
    document.getElementById('status-started').textContent  = data.started_at  || '—';
    document.getElementById('status-finished').textContent = data.finished_at || '—';
    document.getElementById('job-message').textContent = data.status || '';
    document.getElementById('job-error').textContent   = data.error  || '';

    const badgeEl = document.getElementById('status-badge');
    if (running) {
      badgeEl.innerHTML = `<span class="badge badge-running">🔵 실행 중 — ${JOB_LABEL[kind]}</span>`;
    } else if (hasError) {
      badgeEl.innerHTML = `<span class="badge badge-danger">🔴 실패</span>`;
    } else {
      badgeEl.innerHTML = `<span class="badge badge-idle">⬜ 대기 중</span>`;
    }
    setButtonsDisabled(running);
  }

  async function startJob(kind) {
    try {
      const res  = await fetch(`__API_START_BASE__/${kind}`, {
        method: 'POST',
        headers: { 'X-App-Token': window.APP_TOKEN || '' },
      });
      const data = await res.json();
      if (!res.ok) { alert(data.message || 'Failed to start task'); return; }
      await fetchStatus();
    } catch (err) { alert('Failed to start task'); }
  }

  fetchStatus();
  setInterval(fetchStatus, 1200);
</script>
```

`build_home_body()`의 `return` 블록에서 `__APP_TITLE__` 치환이 제거되므로  
기존 `.replace("__APP_TITLE__", ...)` 호출부도 삭제합니다.

---

## STEP 3: Settings 페이지 (`settings()` 함수)

### 3-1. `render_page()` 호출부 수정

```python
return render_page("Settings", body, active_page="settings")
```

### 3-2. SEND_HOUR + SEND_MINUTE → time picker 통합

Settings의 HTML `<form>` 내에서 두 행 대신 하나로 합칩니다:

```html
<!-- 기존: SEND_HOUR 행, SEND_MINUTE 행 (2개) 삭제 -->

<!-- 대체: 1개 time input -->
<div class="settings-row">
  <div class="settings-label">
    <strong>발송 시각</strong>
    <small>매일 논문 리포트를 보내는 시각 (로컬 시간)</small>
  </div>
  <div>
    <input type="time" id="send_time_picker"
      value="{send_hour_padded}:{send_minute_padded}"
      onchange="splitTime(this.value)"
    />
    <input type="hidden" name="SEND_HOUR"   id="send_hour_hidden"   value="{esc('SEND_HOUR')}" />
    <input type="hidden" name="SEND_MINUTE" id="send_minute_hidden" value="{esc('SEND_MINUTE')}" />
  </div>
</div>
<script>
  function splitTime(val) {
    const [h, m] = val.split(':');
    document.getElementById('send_hour_hidden').value   = parseInt(h, 10);
    document.getElementById('send_minute_hidden').value = parseInt(m, 10);
  }
</script>
```

Python 쪽에서 패딩값 계산:
```python
send_hour_padded   = str(env_map.get('SEND_HOUR',   '9')).zfill(2)
send_minute_padded = str(env_map.get('SEND_MINUTE', '0')).zfill(2)
```

### 3-3. Settings 전체 폼 HTML 구조

기존 `<table>` 기반 레이아웃을 **카테고리 섹션 + `.settings-grid`** 로 교체합니다.  
아래가 최종 폼 body 전체입니다 (f-string 내 `{esc(...)}` 등은 기존 방식 그대로 유지):

```html
<div class="page-header">
  <h1>Settings</h1>
  <p>설정 파일 위치: <code>{env_path}</code></p>
</div>

<form method="post">
  <input type="hidden" name="app_token" value="{APP_AUTH_TOKEN}" />

  <!-- ① 이메일 -->
  <div class="card">
    <p class="card-title">📧 이메일 설정</p>
    <div class="settings-grid">
      <div class="settings-row">
        <div class="settings-label">
          <strong>발신 Gmail 주소</strong>
          <small>GMAIL_ADDRESS</small>
        </div>
        <input type="text" name="GMAIL_ADDRESS" value="{esc('GMAIL_ADDRESS')}" placeholder="example@gmail.com" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>Gmail 앱 비밀번호</strong>
          <small>Google 앱 비밀번호 16자리. 빈칸 저장 시 기존값 유지.</small>
        </div>
        <input type="password" name="GMAIL_APP_PASSWORD" value="" placeholder="xxxx xxxx xxxx xxxx" autocomplete="new-password" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>수신 이메일</strong>
          <small>RECIPIENT_EMAIL — 리포트를 받을 주소</small>
        </div>
        <input type="text" name="RECIPIENT_EMAIL" value="{esc('RECIPIENT_EMAIL')}" placeholder="recipient@example.com" />
      </div>
    </div>
  </div>

  <!-- ② 발송 스케줄 -->
  <div class="card">
    <p class="card-title">⏰ 발송 스케줄</p>
    <div class="settings-grid">
      <div class="settings-row">
        <div class="settings-label">
          <strong>타임존</strong>
          <small>TIMEZONE — 예: Asia/Seoul</small>
        </div>
        <input type="text" name="TIMEZONE" value="{esc('TIMEZONE')}" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>발송 시각</strong>
          <small>매일 논문 리포트를 보내는 시각</small>
        </div>
        <div>
          <input type="time" id="send_time_picker" value="{send_hour_padded}:{send_minute_padded}" onchange="splitTime(this.value)" style="width:140px;" />
          <input type="hidden" name="SEND_HOUR"   id="send_hour_hidden"   value="{esc('SEND_HOUR')}" />
          <input type="hidden" name="SEND_MINUTE" id="send_minute_hidden" value="{esc('SEND_MINUTE')}" />
        </div>
      </div>
    </div>
  </div>

  <!-- ③ 검색 파라미터 -->
  <div class="card">
    <p class="card-title">🔍 검색 파라미터</p>
    <div class="settings-grid">
      <div class="settings-row">
        <div class="settings-label">
          <strong>탐색 기간 (시간)</strong>
          <small>LOOKBACK_HOURS — 최근 몇 시간 이내 논문을 수집할지</small>
        </div>
        <input type="number" name="LOOKBACK_HOURS" min="1" value="{esc('LOOKBACK_HOURS')}" style="width:120px;" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>최대 논문 수</strong>
          <small>MAX_PAPERS — 리포트에 포함할 최대 논문 수</small>
        </div>
        <input type="number" name="MAX_PAPERS" min="1" value="{esc('MAX_PAPERS')}" style="width:120px;" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>최소 관련성 점수</strong>
          <small>MIN_RELEVANCE_SCORE — 1~10 사이. LLM 비사용 시 키워드 점수 필터</small>
        </div>
        <input type="text" name="MIN_RELEVANCE_SCORE" value="{esc('MIN_RELEVANCE_SCORE')}" style="width:120px;" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>arXiv 쿼리당 최대 결과</strong>
          <small>ARXIV_MAX_RESULTS_PER_QUERY</small>
        </div>
        <input type="number" name="ARXIV_MAX_RESULTS_PER_QUERY" min="1" value="{esc('ARXIV_MAX_RESULTS_PER_QUERY')}" style="width:120px;" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>PubMed 쿼리당 최대 결과</strong>
          <small>PUBMED_MAX_IDS_PER_QUERY</small>
        </div>
        <input type="number" name="PUBMED_MAX_IDS_PER_QUERY" min="1" value="{esc('PUBMED_MAX_IDS_PER_QUERY')}" style="width:120px;" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>소스당 최대 검색 쿼리 수</strong>
          <small>MAX_SEARCH_QUERIES_PER_SOURCE</small>
        </div>
        <input type="number" name="MAX_SEARCH_QUERIES_PER_SOURCE" min="1" value="{esc('MAX_SEARCH_QUERIES_PER_SOURCE')}" style="width:120px;" />
      </div>
    </div>
  </div>

  <!-- ④ LLM / Gemini -->
  <div class="card">
    <p class="card-title">🤖 LLM / Gemini 설정</p>
    <div class="settings-grid">
      <div class="settings-row">
        <div class="settings-label">
          <strong>LLM 에이전트 사용</strong>
          <small>ENABLE_LLM_AGENT — Gemini로 논문 관련성 자동 평가</small>
        </div>
        <input type="checkbox" name="ENABLE_LLM_AGENT" {checked} />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>Gemini API Key</strong>
          <small>빈칸 저장 시 기존값 유지</small>
        </div>
        <input type="password" name="GEMINI_API_KEY" value="" placeholder="AI Studio에서 발급받은 키" autocomplete="new-password" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>Gemini 모델</strong>
          <small>GEMINI_MODEL</small>
        </div>
        <input type="text" name="GEMINI_MODEL" value="{esc('GEMINI_MODEL')}" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>Gemini 최대 논문 수</strong>
          <small>GEMINI_MAX_PAPERS — LLM이 최종 요약할 논문 수</small>
        </div>
        <input type="number" name="GEMINI_MAX_PAPERS" min="1" value="{esc('GEMINI_MAX_PAPERS')}" style="width:120px;" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>LLM 관련성 임계점</strong>
          <small>LLM_RELEVANCE_THRESHOLD — 이 점수(1~10) 이상인 논문만 리포트에 포함</small>
        </div>
        <input type="number" step="0.1" name="LLM_RELEVANCE_THRESHOLD" min="1" max="10" value="{esc('LLM_RELEVANCE_THRESHOLD')}" style="width:120px;" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>LLM 배치 크기</strong>
          <small>LLM_BATCH_SIZE — 한 번에 Gemini에 보내는 논문 수</small>
        </div>
        <input type="number" name="LLM_BATCH_SIZE" min="1" value="{esc('LLM_BATCH_SIZE')}" style="width:120px;" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>LLM 최대 후보 수</strong>
          <small>LLM_MAX_CANDIDATES — LLM 평가 전 1차 필터 후보 최대 수</small>
        </div>
        <input type="number" name="LLM_MAX_CANDIDATES" min="1" value="{esc('LLM_MAX_CANDIDATES')}" style="width:120px;" />
      </div>
    </div>
  </div>

  <!-- ⑤ 기타 -->
  <div class="card">
    <p class="card-title">📁 기타</p>
    <div class="settings-grid">
      <div class="settings-row">
        <div class="settings-label">
          <strong>NCBI API Key</strong>
          <small>NCBI_API_KEY — PubMed 처리량 향상. 없어도 동작함</small>
        </div>
        <input type="text" name="NCBI_API_KEY" value="{esc('NCBI_API_KEY')}" />
      </div>
      <div class="settings-row">
        <div class="settings-label">
          <strong>Topics 파일 경로</strong>
          <small>USER_TOPICS_FILE</small>
        </div>
        <input type="text" name="USER_TOPICS_FILE" value="{esc('USER_TOPICS_FILE')}" />
      </div>
    </div>
  </div>

  <div class="gap-8" style="padding:4px 0 8px;">
    <button type="submit">💾 저장</button>
    <span class="small">저장 후 스케줄러가 자동으로 재시작됩니다.</span>
  </div>
</form>

<script>
  function splitTime(val) {
    const parts = val.split(':');
    document.getElementById('send_hour_hidden').value   = parseInt(parts[0], 10);
    document.getElementById('send_minute_hidden').value = parseInt(parts[1], 10);
  }
</script>
```

---

## STEP 4: Topic Editor (`topics()` 함수)

```python
# render_page 호출부
return render_page("Topic Editor", body, active_page="topics")
```

주요 변경:

```html
<div class="page-header">
  <h1>Topic Editor</h1>
  <p>프로젝트 컨텍스트를 입력한 뒤 <b>Gemini로 생성</b> 버튼으로 키워드·쿼리 초안을 만들고, 수동 수정 후 저장하세요.</p>
  <p class="small" style="margin-top:4px;">현재 파일: <code>__TOPICS_PATH__</code></p>
</div>
```

- Delete 버튼 스타일: `class="btn-danger"` 적용
- "Keyword / Query 생성" 버튼: `class="btn-success"` + 로딩 중 `🔄 생성 중...` 텍스트 변경
- Save Topics 버튼: 페이지 하단 스티키 바로 분리

```html
<!-- 기존 저장 카드 대체 -->
<div style="position:sticky; bottom:0; background:rgba(244,245,247,0.95);
            backdrop-filter:blur(6px); border-top:1px solid var(--card-border);
            padding:12px 0; display:flex; gap:10px; align-items:center; z-index:50;">
  <button type="button" onclick="preparePayloadBeforeSave() && document.getElementById('topics-save-form').submit()">
    💾 Save Topics
  </button>
  <span class="small">저장 후 화면이 새로고침됩니다.</span>
</div>
<form id="topics-save-form" method="post" action="__TOPICS_SAVE_URL__">
  <input type="hidden" name="app_token" value="__APP_TOKEN__" />
  <input type="hidden" id="payload_json" name="payload_json" />
</form>
```

> **중요**: `preparePayloadBeforeSave()`가 `return false`를 반환할 경우 submit을 막아야 하므로,  
> onclick 로직을 `if (preparePayloadBeforeSave()) document.getElementById('topics-save-form').submit();` 로 적용

---

## STEP 5: Manual 페이지 (`manual()` 함수)

```python
return render_page("Manual", body, active_page="manual")
```

HTML 변경:

```html
<div class="page-header">
  <h1>📖 Manual</h1>
  <p>Paper Morning 사용 방법 가이드</p>
</div>
<div class="card md-body">
  {rendered_html}
</div>
```

---

## 최종 검증 체크리스트

구현 완료 후 아래 항목을 확인합니다.

| 항목 | 확인 방법 |
|------|-----------|
| 사이드바 활성 탭 표시 | 각 페이지 접속 시 해당 링크에 `active` 클래스 확인 |
| Settings 저장 정상 동작 | 값 변경 후 저장 → 재접속 시 값 유지 |
| SEND_HOUR/MINUTE 분리 저장 | time picker 변경 → hidden input 값 확인 (`splitTime`) |
| Dry-Run 실행 후 출력 표시 | `pre#output-pre` 내용 변경 확인 |
| 접기/펼치기 버튼 동작 | `toggleOutput()` |
| Topic Editor 저장 | payload_json 정상 직렬화 후 서버 저장 확인 |
| 모바일 레이아웃 | 900px 이하에서 사이드바 숨김 + 1열 레이아웃 |
| Flash 메시지 표시 | Settings 저장 후 ✅ 메시지 표시 |

---

## 기능 불변 보장

- 모든 `name` 속성값 (`GMAIL_ADDRESS`, `GEMINI_API_KEY` 등)은 **기존 그대로 유지**
- POST 엔드포인트 경로, 토큰 인증 방식 변경 없음
- Python 백엔드 (`paper_digest_app.py`) 변경 없음
- `BASE_TEMPLATE`, `build_home_body`, `settings`, `topics`, `manual` **5개 항목의 HTML 문자열만 수정**
