#!/usr/bin/env python3
"""CanvasMind — the embedded single-page UI, served verbatim at ``GET /``.
Split out of canvasmind_app.py so the (large) HTML/CSS/JS lives on its own."""

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>CanvasMind — Two minds. One canvas.</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500;1,600&display=swap" rel="stylesheet">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{background:#000;color:#fff;font-family:'Inter',ui-sans-serif,system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  body{overflow-x:hidden;max-width:100%}
  img,svg{max-width:100%}
  ::selection{background:#fff;color:#000}
  textarea,input,button,select{font-family:inherit}
  textarea::placeholder,input::placeholder{color:#6a6a6a}
  ::-webkit-scrollbar{width:6px;height:6px}
  ::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.14)}
  ::-webkit-scrollbar-track{background:transparent}
  a{color:inherit}
  @keyframes dotpulse{0%,100%{opacity:0.25}50%{opacity:1}}
  @keyframes spin{to{transform:rotate(360deg)}}
  @keyframes breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.018)}}
  @keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

  /* ---------- subtle rainbow glowing RING around primary buttons (behind, never filling) ---------- */
  @property --cmang{syntax:'<angle>';inherits:false;initial-value:0deg}
  @keyframes cmAngle{to{--cmang:360deg}}
  .glowwrap{position:relative;display:inline-flex;border-radius:75px}
  .glowwrap::before{content:"";position:absolute;inset:-2px;border-radius:inherit;z-index:0;pointer-events:none;
    background:conic-gradient(from var(--cmang),#ff5d8f,#ffb14d,#ffe879,#5fe39a,#56cfe1,#6f9bff,#b98bff,#ff7ad9,#ff5d8f);
    filter:blur(8px);opacity:0.4;animation:cmAngle 11s linear infinite}
  .glowwrap > button{position:relative;z-index:1;width:100%}

  /* ---------- floating "intelligence" bubbles ---------- */
  #bubbles{position:fixed;inset:0;z-index:1;pointer-events:none;overflow:hidden}
  .bubble{position:absolute;border-radius:50%;pointer-events:none;
    background:radial-gradient(circle at 34% 30%, rgba(255,255,255,0.5), rgba(170,205,255,0.16) 44%, rgba(130,160,255,0) 72%);
    box-shadow:0 0 38px rgba(150,180,255,0.16),0 0 90px rgba(120,150,255,0.08);
    will-change:transform,opacity;animation:bubbleFloat linear infinite}
  @keyframes bubbleFloat{
    0%{transform:translate3d(0,0,0) scale(1);opacity:0}
    14%{opacity:var(--maxop,0.5)}
    86%{opacity:var(--maxop,0.5)}
    100%{transform:translate3d(var(--dx,18px),-118vh,0) scale(1.14);opacity:0}}

  /* ---------- glowing, breathing, looping hero image ---------- */
  #heroLayer,#quadHeroLayer{position:fixed;inset:0;z-index:0;overflow:hidden;background:#000}
  .heroImg{position:absolute;inset:-3%;
    background-image:url(assets/hero),radial-gradient(120% 95% at 50% 16%, #1b1636 0%, #0b0b18 52%, #000 100%);
    background-size:cover,cover;background-position:center,center;background-repeat:no-repeat,no-repeat;
    animation:heroBreath 19s ease-in-out infinite}
  .quadHeroImg{position:absolute;inset:-3%;
    background-image:url(assets/quad-hero),radial-gradient(120% 95% at 50% 16%, #241a12 0%, #0b0b12 52%, #000 100%);
    background-size:cover,cover;background-position:center,center;background-repeat:no-repeat,no-repeat;
    animation:heroBreath 19s ease-in-out infinite}
  @keyframes heroBreath{0%,100%{transform:scale(1.0) translateY(0);filter:brightness(0.9) saturate(1.05)}
    50%{transform:scale(1.045) translateY(-0.6%);filter:brightness(1.08) saturate(1.16)}}
  .heroGlow{position:absolute;inset:0;mix-blend-mode:screen;
    background:radial-gradient(58% 48% at 50% 40%, rgba(255,193,96,0.26), rgba(255,170,70,0.07) 46%, transparent 70%);
    animation:heroGlow 7.5s ease-in-out infinite}
  @keyframes heroGlow{0%,100%{opacity:0.5}50%{opacity:1}}
  .heroScrim{position:absolute;inset:0;
    background:linear-gradient(90deg, rgba(0,0,0,0.86) 0%, rgba(0,0,0,0.68) 48%, rgba(0,0,0,0.52) 100%),linear-gradient(0deg, rgba(0,0,0,0.72), rgba(0,0,0,0.22))}

  /* ---------- dreamy / divine hero title ---------- */
  .cm-title{font-family:'Cormorant Garamond',Georgia,serif;font-weight:500;font-style:italic;
    font-size:clamp(44px,9vw,120px);line-height:0.9;letter-spacing:-0.01em;margin-bottom:18px;
    background:linear-gradient(100deg,#ffd1e8,#c9b8ff,#a8e0ff,#bdf7d6,#ffe6a8,#ffb3d9,#ffd1e8);
    background-size:300% 100%;-webkit-background-clip:text;background-clip:text;
    color:transparent;-webkit-text-fill-color:transparent;
    filter:drop-shadow(0 0 26px rgba(180,160,255,0.38)) drop-shadow(0 0 60px rgba(255,200,140,0.12));
    animation:titleFlow 14s ease infinite}
  @keyframes titleFlow{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}

  .cm-persona-desc{font-size:10px;line-height:1.45;color:#6d6d6d;letter-spacing:0.02em;max-width:260px}
  .cm-persona-desc b{color:#9a9a9a;font-weight:400}

  /* ---------- refined persona selector (pill, small subtle caret) ---------- */
  .cm-field-label{font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#8d8d8d}
  .cm-select{appearance:none;-webkit-appearance:none;background-color:transparent;border:1px solid rgba(255,255,255,0.28);
    border-radius:75px;color:#fff;font-family:'Inter',ui-sans-serif,sans-serif;font-size:13px;font-weight:400;
    letter-spacing:0.06em;text-transform:capitalize;padding:9px 30px 9px 16px;outline:none;cursor:pointer;transition:border-color .3s;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='9' height='6' viewBox='0 0 9 6'%3E%3Cpath d='M1 1.2l3.5 3.4L8 1.2' stroke='%237a7a7a' stroke-width='1.1' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat:no-repeat;background-position:right 13px center;background-size:9px 6px}
  .cm-select:hover{border-color:#fff}
  .cm-select option{background:#0a0a0a;color:#fff;font-family:'Inter',sans-serif}
  .cm-levelbadge{text-transform:capitalize;letter-spacing:0.1em}

  /* ---------- quad-agent pipeline ---------- */
  .qcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px;margin:30px 0 40px}
  .qcard{border:1px solid rgba(255,255,255,0.16);border-radius:14px;padding:18px;background:rgba(255,255,255,0.02);display:flex;flex-direction:column;gap:12px}
  .qcard .qidx{font-size:10px;letter-spacing:0.24em;text-transform:uppercase;color:#8d8d8d}
  .qinput{width:100%;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,0.2);color:#fff;font-size:15px;font-weight:300;padding:0 0 8px;outline:none}
  .qtext{width:100%;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.16);border-radius:10px;color:#fff;font-size:13px;line-height:1.45;padding:10px;outline:none;resize:vertical;min-height:70px;display:none}
  .qtoggle{align-self:flex-start;background:transparent;border:1px solid rgba(255,255,255,0.24);color:#cdcdcd;border-radius:75px;padding:5px 12px;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;cursor:pointer}
  .qtoggle.on{background:#fff;color:#000}
  .qpanels{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px;margin-bottom:28px}
  .qpanel{border:1px solid rgba(255,255,255,0.14);border-radius:12px;padding:12px;background:rgba(255,255,255,0.02);min-height:120px;display:flex;flex-direction:column;gap:10px;transition:border-color .3s,box-shadow .3s}
  .qpanel.active{border-color:rgba(255,255,255,0.55);box-shadow:0 0 26px rgba(255,255,255,0.06)}
  .qpanel .qhd{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:8px}
  .qfeed{display:flex;flex-direction:column;gap:10px;max-height:260px;overflow-y:auto}
  .qglobal{display:grid;grid-template-columns:2fr 1fr auto;gap:26px;align-items:end;border-top:1px solid rgba(255,255,255,0.16);padding-top:30px}
  @media (max-width:760px){.qglobal{grid-template-columns:1fr !important;gap:18px !important}}
  /* expandable per-turn agent cards */
  .qcardturn{border-left:1px solid rgba(255,255,255,0.18);padding-left:10px;animation:fadeUp .5s ease both}
  .qturnhead{display:flex;align-items:center;justify-content:space-between;width:100%;background:transparent;border:none;padding:0;cursor:pointer}
  .qturnlabel{font-size:9px;letter-spacing:0.14em;text-transform:uppercase;color:#4a4a4a}
  .qchev{font-size:10px;color:#6d6d6d;transition:color .2s}
  .qturnhead:hover .qchev,.qturnhead:hover .qturnlabel{color:#9a9a9a}
  .qobj{font-size:14px;font-weight:300;color:#fff;line-height:1.3;margin:4px 0 2px}
  .qdetails{margin-top:6px;border-top:1px dashed rgba(255,255,255,0.12);padding-top:6px}
  .qk{font-size:9px;letter-spacing:0.14em;text-transform:uppercase;color:#4a4a4a;margin-top:6px}
  .qv{font-size:11px;color:#8d8d8d;line-height:1.4}
  #qBriefWrap:hover #qBrief{color:#cdcdcd}

  /* ---------- responsive ---------- */
  @media (max-width: 1024px){
    .stageGrid{grid-template-columns:1fr !important;gap:36px !important}
    .judgeGrid{grid-template-columns:1fr !important;gap:40px !important}
  }
  @media (max-width: 760px){
    nav{padding:16px 18px !important;gap:10px !important;flex-wrap:wrap !important}
    #modelInfo{display:none !important}
    #briefing{padding:96px 20px 56px !important}
    #stage{padding:78px 20px 30px !important}
    .briefGrid{grid-template-columns:1fr !important;gap:42px !important}
    .cm-title{font-size:clamp(44px,14vw,92px) !important}
    #turnCounter{font-size:40px !important}
    .personaRow{flex-direction:column !important;gap:18px !important;align-items:stretch !important}
    .cm-select{width:100%}
  }
  @media (max-width: 440px){
    nav{padding:13px 13px !important}
    #briefing{padding:86px 15px 46px !important}
    #stage{padding:70px 14px 24px !important}
    .cm-title{font-size:clamp(36px,12.5vw,64px) !important}
    .modeRow{flex-wrap:wrap !important}
    .ring-deco{display:none !important}
  }

  /* ---- pre-session participant form + post-session survey ---- */
  .cm-overlay{position:fixed;inset:0;z-index:60;display:flex;align-items:center;justify-content:center;
    padding:22px;background:rgba(6,6,12,0.72);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
  .cm-participant{width:100%;max-width:440px;background:linear-gradient(180deg,rgba(24,24,34,0.96),rgba(12,12,20,0.98));
    border:1px solid rgba(255,255,255,0.12);border-radius:22px;padding:34px 32px;
    box-shadow:0 30px 90px rgba(0,0,0,0.6);animation:cmPartIn 0.5s cubic-bezier(0.2,0.8,0.2,1)}
  @keyframes cmPartIn{from{opacity:0;transform:translateY(16px) scale(0.98)}to{opacity:1;transform:none}}
  .cm-part-kicker{font-size:10px;letter-spacing:0.28em;text-transform:uppercase;color:#8a7de0;margin-bottom:8px}
  .cm-part-title{font-size:30px;font-weight:300;letter-spacing:-0.02em;color:#fff;margin-bottom:8px;font-family:'Cormorant Garamond',Georgia,serif;font-style:italic}
  .cm-part-sub{font-size:12.5px;line-height:1.55;color:#9a9aac;margin-bottom:22px}
  .cm-part-field{margin-bottom:15px}
  .cm-part-field label{display:block;font-size:10px;letter-spacing:0.16em;text-transform:uppercase;color:#7c7c90;margin-bottom:7px}
  .cm-part-field input,.cm-part-field select{width:100%;background:rgba(255,255,255,0.04);color:#fff;
    border:1px solid rgba(255,255,255,0.14);border-radius:11px;padding:11px 13px;font-size:14px;outline:none;transition:border-color 0.2s}
  .cm-part-field input:focus,.cm-part-field select:focus{border-color:rgba(138,125,224,0.7)}
  .cm-part-field select option{background:#16161f;color:#fff}
  .cm-part-error{color:#e77;font-size:12px;min-height:16px;margin:2px 0 10px}
  .cm-part-actions{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-top:6px}
  .cm-part-skip{background:transparent;border:none;color:#7c7c90;font-size:12px;letter-spacing:0.08em;cursor:pointer;padding:8px 4px}
  .cm-part-skip:hover{color:#b7b7c8}
  .cm-part-submit{flex:1;background:linear-gradient(90deg,#7b6cf0,#b06ce0);color:#fff;border:none;border-radius:75px;
    padding:13px 22px;font-size:12px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;cursor:pointer;transition:transform 0.15s,filter 0.2s}
  .cm-part-submit:hover{transform:translateY(-1px);filter:brightness(1.08)}

  .cm-survey-host{max-width:1000px;margin:52px auto 0}
  .cm-survey{border:1px solid rgba(255,255,255,0.1);border-radius:22px;padding:34px 34px 28px;
    background:linear-gradient(180deg,rgba(20,20,30,0.6),rgba(10,10,16,0.5));animation:cmPartIn 0.6s cubic-bezier(0.2,0.8,0.2,1)}
  .cm-survey h3{font-size:11px;letter-spacing:0.24em;text-transform:uppercase;color:#8a7de0;margin-bottom:6px}
  .cm-survey .cm-survey-lead{font-size:clamp(20px,2.2vw,26px);font-weight:300;letter-spacing:-0.01em;color:#fff;margin-bottom:6px;font-family:'Cormorant Garamond',Georgia,serif;font-style:italic}
  .cm-survey .cm-survey-note{font-size:12px;color:#8a8a9c;margin-bottom:24px}
  .cm-q{padding:16px 0;border-top:1px solid rgba(255,255,255,0.07)}
  .cm-q-text{font-size:14px;color:#e6e6ef;margin-bottom:12px;line-height:1.45}
  .cm-q-text .cm-q-num{color:#6a6a80;margin-right:9px}
  .cm-scale{display:flex;gap:6px;flex-wrap:wrap}
  .cm-scale button{width:38px;height:38px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);
    background:rgba(255,255,255,0.03);color:#c9c9d6;font-size:13px;cursor:pointer;transition:all 0.14s}
  .cm-scale button:hover{border-color:rgba(138,125,224,0.6)}
  .cm-scale button.sel{background:linear-gradient(90deg,#7b6cf0,#b06ce0);border-color:transparent;color:#fff;font-weight:600}
  .cm-scale-ends{display:flex;justify-content:space-between;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:#5c5c70;margin-top:7px}
  .cm-likert{display:flex;gap:8px;flex-wrap:wrap}
  .cm-likert button{flex:1;min-width:96px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);
    background:rgba(255,255,255,0.03);color:#c1c1d0;font-size:11.5px;padding:10px 8px;cursor:pointer;transition:all 0.14s;text-align:center}
  .cm-likert button:hover{border-color:rgba(138,125,224,0.6)}
  .cm-likert button.sel{background:linear-gradient(90deg,#7b6cf0,#b06ce0);border-color:transparent;color:#fff;font-weight:600}
  .cm-survey textarea{width:100%;min-height:74px;background:rgba(255,255,255,0.03);color:#fff;
    border:1px solid rgba(255,255,255,0.14);border-radius:12px;padding:12px;font-size:13px;font-family:inherit;outline:none;resize:vertical;margin-top:6px}
  .cm-survey-foot{display:flex;align-items:center;gap:16px;margin-top:24px;flex-wrap:wrap}
  .cm-survey-submit{background:#fff;color:#000;border:none;border-radius:75px;padding:13px 30px;font-size:12px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;cursor:pointer}
  .cm-survey-submit:disabled{opacity:0.4;cursor:not-allowed}
  .cm-survey-progress{font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#6a6a80}
  .cm-survey-done{text-align:center;padding:30px;color:#9fe0b0;font-size:15px;letter-spacing:0.02em}
  @media(max-width:560px){ .cm-likert button{min-width:calc(50% - 4px)} .cm-participant{padding:26px 22px} }
</style>
</head>
<body>

<!-- glowing, looping robot-image hero (shown on the home screen) -->
<div id="heroLayer">
  <div class="heroImg"></div>
  <div class="heroGlow"></div>
  <div class="heroScrim"></div>
</div>

<!-- Quad-Agent hero (shown on the quad config screen) -->
<div id="quadHeroLayer" style="display:none">
  <div class="quadHeroImg"></div>
  <div class="heroGlow"></div>
  <div class="heroScrim"></div>
</div>

<!-- continuously levitating bubbles, sitewide -->
<div id="bubbles"></div>

<!-- pre-session participant form (shown once, before the studio opens) -->
<div id="participantOverlay" class="cm-overlay" style="display:none">
  <div class="cm-participant">
    <p class="cm-part-kicker">Before we begin</p>
    <h2 class="cm-part-title">A few details</h2>
    <p class="cm-part-sub">This helps us understand who is co-creating. Nothing here identifies you; it is stored with your session for research.</p>
    <div class="cm-part-field">
      <label for="pfAge">Age</label>
      <input id="pfAge" type="number" min="1" max="120" inputmode="numeric" placeholder="e.g. 28" />
    </div>
    <div class="cm-part-field">
      <label for="pfGender">Gender</label>
      <select id="pfGender">
        <option value="">Select…</option>
        <option>Female</option><option>Male</option><option>Non-binary</option>
        <option>Prefer not to say</option><option>Other</option>
      </select>
    </div>
    <div class="cm-part-field">
      <label for="pfExpertise">Expertise in art</label>
      <select id="pfExpertise">
        <option value="">Select…</option>
        <option>None</option><option>Beginner</option><option>Intermediate</option>
        <option>Advanced</option><option>Professional</option>
      </select>
    </div>
    <p id="pfError" class="cm-part-error"></p>
    <div class="cm-part-actions">
      <button id="pfSkip" class="cm-part-skip">Skip</button>
      <button id="pfSubmit" class="cm-part-submit">Enter the studio →</button>
    </div>
  </div>
</div>

<div id="app" style="position:relative;z-index:2;min-height:100vh;background:transparent">

  <!-- ============ TOP NAV ============ -->
  <nav style="position:fixed;top:0;left:0;right:0;z-index:50;display:flex;align-items:center;justify-content:space-between;padding:22px 40px;mix-blend-mode:difference">
    <div style="display:flex;align-items:baseline;gap:14px">
      <span style="font-size:12px;font-weight:600;letter-spacing:0.22em;color:#fff">CANVASMIND</span>
      <span style="font-size:11px;font-weight:400;letter-spacing:0.18em;color:#9a9a9a;text-transform:uppercase">RL Multi-Agent</span>
    </div>
    <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;justify-content:flex-end">
      <span style="display:flex;align-items:center;gap:7px;font-size:11px;letter-spacing:0.16em;text-transform:uppercase;color:#9a9a9a">
        <span id="statusDot" style="width:6px;height:6px;border-radius:50%;background:#6d6d6d;display:inline-block"></span><span id="statusText">Demo mode</span>
      </span>
      <span id="modelInfo" style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#6d6d6d"></span>
      <button id="toQuad" style="border:1px solid rgba(255,255,255,0.4);background:transparent;color:#fff;border-radius:75px;padding:6px 16px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">⧉ Quad Pipeline</button>
      <button id="toDual" style="display:none;border:1px solid rgba(255,255,255,0.4);background:transparent;color:#fff;border-radius:75px;padding:6px 16px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">← ARIA · NEXUS</button>
      <button id="modeChip" style="border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;border-radius:75px;padding:6px 16px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">Demo</button>
      <button id="stopBtn" style="display:none;border:1px solid rgba(255,255,255,0.45);background:transparent;color:#fff;border-radius:75px;padding:6px 16px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">Stop &amp; Judge ↦</button>
      <button id="navAction" style="display:none;border:none;background:transparent;color:#9a9a9a;font-size:11px;letter-spacing:0.16em;text-transform:uppercase;cursor:pointer;font-weight:400">New session</button>
    </div>
  </nav>

  <!-- ============ BRIEFING ============ -->
  <section id="briefing" style="min-height:100vh;display:flex;flex-direction:column;justify-content:center;padding:100px 44px 56px">
    <p style="font-size:11px;font-weight:400;letter-spacing:0.32em;text-transform:uppercase;color:#9a9a9a;margin-bottom:14px">Co-Creation Engine · Two Agents · One Canvas</p>
    <h1 class="cm-title">Two minds.<br>One canvas.</h1>
    <p style="font-size:15px;font-weight:400;line-height:1.5;color:#cdcdcd;max-width:560px;margin-bottom:22px">ARIA and NEXUS paint together, one object at a time — each turn reading what the other left behind.</p>

    <!-- compact, full-width horizontal control bar (spread end-to-end) -->
    <div class="briefBar" style="border-top:1px solid rgba(255,255,255,0.16);padding-top:22px;display:flex;flex-wrap:wrap;align-items:flex-end;gap:18px 28px;width:100%">

      <!-- brief mode -->
      <div style="display:flex;flex-direction:column;gap:9px">
        <span class="cm-field-label">01 · Brief</span>
        <div class="modeRow" style="display:flex;gap:8px">
          <button id="btnSurprise" style="border-radius:75px;padding:9px 15px;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;cursor:pointer;border:1px solid rgba(255,255,255,0.28);background:#fff;color:#000;transition:all .3s">AI Surprise</button>
          <button id="btnManual" style="border-radius:75px;padding:9px 15px;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;cursor:pointer;border:1px solid rgba(255,255,255,0.28);background:#0e0e16;color:#fff;transition:all .3s">Write My Own</button>
        </div>
      </div>

      <!-- subject (grows to fill the row) -->
      <div style="flex:1 1 240px;min-width:200px;display:flex;flex-direction:column;gap:9px">
        <span class="cm-field-label">Subject</span>
        <div id="manualFields" style="display:none;gap:12px;align-items:center">
          <input id="brief" placeholder="Describe the painting to begin…" style="flex:1;min-width:130px;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,0.22);color:#fff;font-size:15px;font-weight:300;padding:0 0 8px;outline:none">
          <input id="style" placeholder="Style — mineral light" style="width:150px;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,0.22);color:#cdcdcd;font-size:13px;padding:0 0 8px;outline:none">
        </div>
        <p id="surpriseText" style="font-size:13px;font-weight:400;line-height:1.45;color:#9a9a9a;margin:0">An unexpected brief and style, invented on the spot — the agents discover the subject as they begin.</p>
      </div>

      <!-- ARIA persona -->
      <label style="display:flex;flex-direction:column;gap:9px">
        <span class="cm-field-label">ARIA · Persona</span>
        <select id="ariaPersona" class="cm-select"></select>
        <span id="ariaPersonaDesc" class="cm-persona-desc"></span>
      </label>
      <!-- NEXUS persona -->
      <label style="display:flex;flex-direction:column;gap:9px">
        <span class="cm-field-label">NEXUS · Persona</span>
        <select id="nexusPersona" class="cm-select"></select>
        <span id="nexusPersonaDesc" class="cm-persona-desc"></span>
      </label>

      <!-- rounds -->
      <div style="display:flex;flex-direction:column;gap:9px">
        <span class="cm-field-label">Rounds · <span id="totalTurns">10</span> turns</span>
        <div style="display:flex;align-items:center;gap:12px">
          <button id="roundsDown" style="width:30px;height:30px;border-radius:50%;border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;font-size:16px;font-weight:300;cursor:pointer;line-height:1">−</button>
          <span id="roundsVal" style="font-size:30px;font-weight:300;line-height:1;color:#fff;min-width:34px;text-align:center;letter-spacing:-0.02em">5</span>
          <button id="roundsUp" style="width:30px;height:30px;border-radius:50%;border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;font-size:16px;font-weight:300;cursor:pointer;line-height:1">+</button>
        </div>
        <span style="display:none"><span id="roundsVal2">5</span><span id="totalTurns2">10</span></span>
      </div>

      <!-- autonomy -->
      <label style="display:flex;flex-direction:column;gap:9px">
        <span class="cm-field-label">Autonomy</span>
        <select id="autonomy" class="cm-select"><option value="1" selected>Autonomous</option><option value="0.5">Shared</option><option value="0">Human-led</option></select>
      </label>

      <!-- begin -->
      <span class="glowwrap"><button id="btnBegin" style="background:#fff;color:#000;border:none;border-radius:75px;padding:13px 30px;font-size:12px;font-weight:500;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer;transition:opacity .3s">Begin →</button></span>
    </div>

    <div class="ring-deco" style="position:fixed;bottom:34px;left:40px;width:92px;height:92px;animation:spin 22s linear infinite;z-index:2">
      <svg width="92" height="92" viewBox="0 0 92 92">
        <defs><path id="cmring" d="M46,46 m-33,0 a33,33 0 1,1 66,0 a33,33 0 1,1 -66,0"></path></defs>
        <text font-size="8.5" letter-spacing="2.6" fill="#9a9a9a" font-family="Inter"><textPath href="#cmring">SHARED · CANVAS · COLLABORATION · </textPath></text>
      </svg>
      <span style="position:absolute;top:50%;left:50%;width:4px;height:4px;background:#fff;border-radius:50%;transform:translate(-50%,-50%)"></span>
    </div>
  </section>

  <!-- ============ STAGE ============ -->
  <section id="stage" style="display:none;min-height:100vh;padding:84px 40px 40px">
    <!-- brief bar (full-width) -->
    <div style="border-bottom:1px solid rgba(255,255,255,0.12);padding-bottom:24px;margin-bottom:30px">
      <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:14px">
        <p style="font-size:11px;letter-spacing:0.22em;text-transform:uppercase;color:#6d6d6d">Brief</p>
        <div style="text-align:right">
          <p id="turnLabel" style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:2px">Turn</p>
          <p id="turnCounter" style="font-size:34px;font-weight:300;line-height:1;color:#fff;letter-spacing:-0.02em">00 / 10</p>
        </div>
      </div>
      <h2 id="stageBrief" title="Click to view the full prompt" style="cursor:pointer;width:100%;font-size:clamp(18px,2.8vw,34px);font-weight:300;line-height:1.2;letter-spacing:-0.01em;color:#fff;transition:opacity .2s"></h2>
      <p id="stageStyle" style="font-size:13px;letter-spacing:0.06em;color:#9a9a9a;margin-top:14px;text-transform:uppercase"></p>
    </div>

    <!-- 3 column grid -->
    <div class="stageGrid" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.5fr) minmax(0,1fr);gap:28px;align-items:start">

      <!-- ARIA feed (left) -->
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid rgba(255,255,255,0.12)">
          <span style="width:9px;height:9px;background:#fff;display:inline-block"></span>
          <span style="font-size:12px;font-weight:600;letter-spacing:0.14em;color:#fff">ARIA</span>
          <span style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6d6d6d">Creative Director</span>
          <span id="ariaLevelLabel" class="cm-levelbadge" style="margin-left:auto;font-size:10px;color:#9a9a9a;border:1px solid rgba(255,255,255,0.28);border-radius:75px;padding:3px 10px"></span>
        </div>
        <div id="ariaFeed" style="display:flex;flex-direction:column;gap:18px"></div>
      </div>

      <!-- CENTER canvas + filmstrip -->
      <div style="display:flex;flex-direction:column;gap:18px">
        <div id="canvas" style="position:relative;width:100%;aspect-ratio:1/1;background:#050505;border:1px solid rgba(255,255,255,0.12);overflow:hidden;animation:breathe 9s ease-in-out infinite">
          <div id="canvasBlobs" style="position:absolute;inset:0"></div>
          <img id="canvasImg" alt="shared canvas" style="display:none;position:absolute;inset:0;width:100%;height:100%;object-fit:cover">
          <div id="canvasEmpty" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center"><span style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#3a3a3a">awaiting first object</span></div>
          <div style="position:absolute;top:18px;left:18px;display:flex;align-items:center;gap:9px">
            <span id="canvasTag" style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#fff;background:rgba(0,0,0,0.45);padding:5px 10px;backdrop-filter:blur(4px)">Shared canvas</span>
          </div>
          <div id="compositing" style="display:none;position:absolute;bottom:18px;left:18px;align-items:center;gap:8px;font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#fff">
            <span style="width:5px;height:5px;border-radius:50%;background:#fff;animation:dotpulse 1.2s ease infinite"></span><span id="compositingText">Compositing</span>
          </div>
        </div>
        <!-- filmstrip -->
        <div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
            <span style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d">Filmstrip · <span id="stepCount">0</span> steps</span>
            <button id="viewLatest" style="border:none;background:transparent;color:#6d6d6d;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer;display:none">↺ Latest</button>
          </div>
          <div id="filmstrip" style="display:flex;gap:8px;overflow-x:auto;padding-bottom:6px"></div>
        </div>
      </div>

      <!-- NEXUS feed (right) -->
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid rgba(255,255,255,0.12);justify-content:flex-end">
          <span id="nexusLevelLabel" class="cm-levelbadge" style="margin-right:auto;font-size:10px;color:#9a9a9a;border:1px solid rgba(255,255,255,0.28);border-radius:75px;padding:3px 10px"></span>
          <span style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6d6d6d">Creative Challenger</span>
          <span style="font-size:12px;font-weight:600;letter-spacing:0.14em;color:#fff">NEXUS</span>
          <span style="width:9px;height:9px;border:1px solid #fff;display:inline-block"></span>
        </div>
        <div id="nexusFeed" style="display:flex;flex-direction:column;gap:18px"></div>
      </div>
    </div>

    <!-- ============ JUDGE CRITIQUE BAND ============ -->
    <div id="judge" style="display:none;margin-top:64px;border-top:1px solid rgba(255,255,255,0.12);padding-top:48px;animation:fadeUp .8s ease both">
      <div style="display:flex;align-items:center;gap:12px;justify-content:center;margin-bottom:44px">
        <span style="width:10px;height:10px;border:1px solid #fff;border-radius:50%;display:inline-block"></span>
        <span style="font-size:12px;font-weight:600;letter-spacing:0.16em;color:#fff">JUDGE</span>
        <span style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6d6d6d">Critic · does not edit</span>
      </div>
      <div class="judgeGrid" style="display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:64px;max-width:1120px;margin:0 auto;align-items:start">
        <div id="scores" style="display:flex;flex-direction:column;gap:22px"></div>
        <div>
          <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:8px">Composite</p>
          <p id="composite" style="font-size:94px;font-weight:300;line-height:0.9;letter-spacing:-0.03em;color:#fff;margin-bottom:24px">—</p>
          <p id="criticReasoning" style="font-size:15px;line-height:1.55;color:#9a9a9a;margin-bottom:18px"></p>
          <div id="highlights" style="margin-bottom:24px"></div>
          <div style="display:flex;gap:14px;flex-wrap:wrap">
            <button id="downloadBtn" style="background:#fff;color:#000;border:none;border-radius:75px;padding:13px 28px;font-size:12px;font-weight:500;letter-spacing:0.12em;text-transform:uppercase;cursor:pointer;opacity:0.5" disabled>Download all steps</button>
            <button id="newSessionBtn" style="background:transparent;color:#fff;border:1px solid rgba(255,255,255,0.28);border-radius:75px;padding:13px 28px;font-size:12px;letter-spacing:0.12em;text-transform:uppercase;cursor:pointer">New session</button>
          </div>
          <p id="memStat" style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#4a4a4a;margin-top:22px"></p>
        </div>
      </div>
      <p id="finalSummary" style="display:none;max-width:880px;margin:56px auto 0;text-align:center;font-size:clamp(22px,2.6vw,30px);font-weight:300;line-height:1.3;letter-spacing:-0.01em;color:#fff"></p>
      <div id="surveyHost" class="cm-survey-host"></div>
    </div>

    <!-- ============ RESEARCH DASHBOARD (RL multi-agent metrics) ============ -->
    <div id="research" style="display:none;margin-top:60px;border-top:1px solid rgba(255,255,255,0.12);padding-top:48px;animation:fadeUp .8s ease both">
      <div style="display:flex;align-items:center;gap:12px;justify-content:center;margin-bottom:40px">
        <span style="width:10px;height:10px;border:1px solid #fff;display:inline-block"></span>
        <span style="font-size:12px;font-weight:600;letter-spacing:0.16em;color:#fff">RESEARCH</span>
        <span style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6d6d6d">RL · reward · credit · empowerment · Goodhart</span>
      </div>
      <div id="researchBody" class="judgeGrid" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:64px;max-width:1120px;margin:0 auto;align-items:start"></div>
    </div>

    <!-- ============ EVENT LOG ============ -->
    <div style="margin-top:56px;border-top:1px solid rgba(255,255,255,0.08);padding-top:18px">
      <p style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#4a4a4a;margin-bottom:12px">Event Stream</p>
      <div id="log" style="display:flex;flex-direction:column;gap:5px;max-height:150px;overflow-y:auto"></div>
    </div>
  </section>

  <!-- ============ QUAD-AGENT CONFIG ============ -->
  <section id="quadConfig" style="display:none;min-height:100vh;padding:110px 40px 70px;max-width:1280px;margin:0 auto">
    <p style="font-size:11px;letter-spacing:0.3em;text-transform:uppercase;color:#9a9a9a;margin-bottom:22px">Advanced · Quad-Agent Sequential Pipeline</p>
    <h1 style="font-family:'Cormorant Garamond',Georgia,serif;font-style:italic;font-weight:500;font-size:clamp(40px,7vw,84px);line-height:0.95;color:#fff;margin-bottom:18px">Four minds, in sequence.</h1>
    <p style="font-size:16px;line-height:1.5;color:#cdcdcd;max-width:640px">Four independently-configured persona agents each add one object per round, in strict order — pure additive co-creation, no JUDGE.</p>

    <div class="qglobal">
      <div>
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px">
          <label class="cm-field-label">Global Prompt</label>
          <button id="qSurprise" style="border:1px solid rgba(255,255,255,0.32);background:transparent;color:#fff;border-radius:75px;padding:5px 14px;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;cursor:pointer">✦ AI Surprise</button>
        </div>
        <textarea id="qPrompt" rows="2" placeholder="Describe the artwork the four agents build together…" style="width:100%;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,0.22);color:#fff;font-size:18px;font-weight:300;line-height:1.4;padding:8px 0 12px;resize:none;outline:none"></textarea>
      </div>
      <div>
        <label class="cm-field-label">Style Hints</label>
        <input id="qStyle" placeholder="e.g. oceanic, stormy" style="width:100%;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,0.22);color:#cdcdcd;font-size:15px;padding:8px 0 12px;outline:none">
      </div>
      <div>
        <label class="cm-field-label">Rounds</label>
        <div style="display:flex;align-items:center;gap:14px;margin-top:8px">
          <button id="qRoundsDown" style="width:34px;height:34px;border-radius:50%;border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;font-size:18px;cursor:pointer;line-height:1">−</button>
          <span id="qRoundsVal" style="font-size:40px;font-weight:300;color:#fff;min-width:44px;text-align:center">1</span>
          <button id="qRoundsUp" style="width:34px;height:34px;border-radius:50%;border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;font-size:18px;cursor:pointer;line-height:1">+</button>
        </div>
        <p style="font-size:11px;color:#8d8d8d;margin-top:8px"><span id="qTotalTurns">4</span> step images · 4 agents × rounds</p>
      </div>
    </div>

    <div id="qCards" class="qcards"></div>

    <div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap">
      <span class="glowwrap"><button id="qLaunch" style="background:#fff;color:#000;border:none;border-radius:75px;padding:15px 36px;font-size:13px;font-weight:500;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">Launch Quad Session →</button></span>
      <button id="qBack" style="background:transparent;color:#9a9a9a;border:none;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">← Back to ARIA · NEXUS</button>
    </div>
  </section>

  <!-- ============ QUAD-AGENT LIVE STAGE ============ -->
  <section id="quadStage" style="display:none;min-height:100vh;padding:84px 40px 40px">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.12);padding-bottom:16px;margin-bottom:22px;gap:24px;flex-wrap:wrap">
      <div id="qBriefWrap" style="flex:1;min-width:260px;cursor:pointer" title="Click to read the full brief">
        <p style="font-size:11px;letter-spacing:0.22em;text-transform:uppercase;color:#6d6d6d;margin-bottom:8px">Quad Pipeline · Brief <span style="color:#5a5a5a">· click to expand</span></p>
        <h2 id="qBrief" style="font-size:clamp(15px,1.7vw,22px);font-weight:300;line-height:1.3;color:#fff;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden"></h2>
        <p id="qStyle2" style="font-size:12px;letter-spacing:0.06em;color:#9a9a9a;margin-top:8px;text-transform:uppercase"></p>
      </div>
      <div style="display:flex;align-items:flex-start;gap:20px;flex-wrap:wrap;justify-content:flex-end">
        <div style="text-align:right"><p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:6px">Turn</p>
          <p id="qTurnCounter" style="font-size:40px;font-weight:300;line-height:1;color:#fff">00 / 04</p></div>
        <button id="qStopBtn" style="display:none;border:1px solid rgba(255,255,255,0.45);background:transparent;color:#fff;border-radius:75px;padding:8px 16px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">Stop ↦</button>
        <button id="qNewBtn" style="border:1px solid rgba(255,255,255,0.28);background:transparent;color:#cdcdcd;border-radius:75px;padding:8px 16px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">New config</button>
      </div>
    </div>

    <div id="qPanels" class="qpanels"></div>

    <div class="judgeGrid" style="display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:28px;align-items:start">
      <div>
        <div id="qCanvas" style="position:relative;width:100%;aspect-ratio:1/1;background:#050505;border:1px solid rgba(255,255,255,0.12);overflow:hidden;animation:breathe 9s ease-in-out infinite">
          <div id="qCanvasBlobs" style="position:absolute;inset:0"></div>
          <img id="qCanvasImg" alt="quad canvas" style="display:none;position:absolute;inset:0;width:100%;height:100%;object-fit:cover">
          <div id="qCanvasEmpty" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center"><span style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#3a3a3a">awaiting first object</span></div>
          <div style="position:absolute;top:16px;left:16px"><span id="qCanvasTag" style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#fff;background:rgba(0,0,0,0.45);padding:5px 10px;backdrop-filter:blur(4px)">Shared canvas</span></div>
          <div id="qComp" style="display:none;position:absolute;bottom:16px;left:16px;align-items:center;gap:8px;font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#fff"><span style="width:5px;height:5px;border-radius:50%;background:#fff;animation:dotpulse 1.2s ease infinite"></span><span id="qCompText">Compositing</span></div>
        </div>
      </div>
      <div>
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;gap:10px;flex-wrap:wrap">
          <span style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d">Filmstrip · <span id="qStepCount">0</span> steps</span>
          <div style="display:flex;gap:12px;align-items:center">
            <button id="qViewLatest" style="border:none;background:transparent;color:#6d6d6d;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer;display:none">↺ Latest</button>
            <button id="qDownloadBtn" style="border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;border-radius:75px;padding:5px 12px;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;cursor:pointer;opacity:0.5" disabled>Download steps</button>
          </div>
        </div>
        <div id="qFilmstrip" style="display:flex;flex-wrap:wrap;gap:8px;max-height:340px;overflow-y:auto"></div>
      </div>
    </div>

    <!-- JUDGE critique band (re-added, mirrors ARIA/NEXUS) -->
    <div id="qJudge" style="display:none;margin-top:48px;border-top:1px solid rgba(255,255,255,0.12);padding-top:40px;animation:fadeUp .8s ease both">
      <div style="display:flex;align-items:center;gap:12px;justify-content:center;margin-bottom:36px">
        <span style="width:10px;height:10px;border:1px solid #fff;border-radius:50%;display:inline-block"></span>
        <span style="font-size:12px;font-weight:600;letter-spacing:0.16em;color:#fff">JUDGE</span>
        <span style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6d6d6d">Critic · scores the sequential collaboration</span>
      </div>
      <div class="judgeGrid" style="display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:56px;max-width:1120px;margin:0 auto;align-items:start">
        <div id="qScores" style="display:flex;flex-direction:column;gap:20px"></div>
        <div>
          <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:8px">Composite</p>
          <p id="qComposite" style="font-size:84px;font-weight:300;line-height:0.9;letter-spacing:-0.03em;color:#fff;margin-bottom:22px">—</p>
          <p id="qCriticReasoning" style="font-size:14px;line-height:1.55;color:#9a9a9a;margin-bottom:16px"></p>
          <div id="qHighlights" style="margin-bottom:22px"></div>
          <div style="display:flex;gap:14px;flex-wrap:wrap">
            <button id="qJudgeDownload" style="background:#fff;color:#000;border:none;border-radius:75px;padding:12px 26px;font-size:12px;font-weight:500;letter-spacing:0.12em;text-transform:uppercase;cursor:pointer;opacity:0.5" disabled>Download all steps</button>
            <button id="qJudgeNew" style="background:transparent;color:#fff;border:1px solid rgba(255,255,255,0.28);border-radius:75px;padding:12px 26px;font-size:12px;letter-spacing:0.12em;text-transform:uppercase;cursor:pointer">New session</button>
          </div>
        </div>
      </div>
      <p id="qFinalSummary" style="display:none;max-width:880px;margin:44px auto 0;text-align:center;font-size:clamp(20px,2.4vw,28px);font-weight:300;line-height:1.3;color:#fff"></p>
      <div id="qSurveyHost" class="cm-survey-host"></div>
    </div>

    <div style="margin-top:40px;border-top:1px solid rgba(255,255,255,0.08);padding-top:18px">
      <p style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#4a4a4a;margin-bottom:12px">Event Stream</p>
      <div id="qLog" style="display:flex;flex-direction:column;gap:5px;max-height:150px;overflow-y:auto"></div>
    </div>

    <!-- full-brief modal -->
    <div id="qBriefModal" style="display:none;position:fixed;inset:0;z-index:80;background:rgba(0,0,0,0.82);backdrop-filter:blur(6px);align-items:center;justify-content:center;padding:40px">
      <div style="max-width:760px;width:100%;max-height:80vh;overflow-y:auto;border:1px solid rgba(255,255,255,0.16);border-radius:16px;background:#0a0a0f;padding:34px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px">
          <p style="font-size:11px;letter-spacing:0.24em;text-transform:uppercase;color:#8d8d8d">Full Brief</p>
          <button id="qModalClose" style="border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;border-radius:50%;width:30px;height:30px;cursor:pointer;font-size:15px;line-height:1">×</button>
        </div>
        <h3 id="qModalBrief" style="font-size:clamp(22px,3vw,34px);font-weight:300;line-height:1.28;color:#fff;margin-bottom:16px"></h3>
        <p id="qModalStyle" style="font-size:13px;letter-spacing:0.06em;text-transform:uppercase;color:#9a9a9a"></p>
      </div>
    </div>
  </section>

</div>

<!-- ============ FULL-PROMPT MEMO POPUP ============ -->
<div id="briefModal" style="display:none;position:fixed;inset:0;z-index:200;align-items:center;justify-content:center;padding:24px;background:rgba(0,0,0,0.74);backdrop-filter:blur(7px)">
  <div style="position:relative;max-width:740px;width:100%;max-height:82vh;overflow-y:auto;background:#0b0b12;border:1px solid rgba(255,255,255,0.16);border-left:2px solid rgba(255,255,255,0.7);border-radius:5px;padding:42px 46px 40px;box-shadow:0 30px 100px rgba(0,0,0,0.65);animation:fadeUp .3s ease both">
    <button id="briefModalClose" style="position:absolute;top:16px;right:18px;background:transparent;border:none;color:#9a9a9a;font-size:24px;line-height:1;cursor:pointer">×</button>
    <p style="font-size:11px;letter-spacing:0.24em;text-transform:uppercase;color:#6d6d6d;margin-bottom:18px">The Brief · Full Prompt</p>
    <p id="briefModalText" style="font-size:22px;font-weight:300;line-height:1.45;color:#fff;letter-spacing:-0.01em"></p>
    <p id="briefModalStyle" style="font-size:13px;letter-spacing:0.06em;color:#9a9a9a;margin-top:22px;text-transform:uppercase"></p>
  </div>
</div>

<script>
(function(){
"use strict";
var $ = function(id){ return document.getElementById(id); };
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
function cap(s){ s=String(s||''); return s ? s.charAt(0).toUpperCase()+s.slice(1) : ''; }

// ---------- the 8 generative-agent personas (shared by dual + quad) ----------
var PERSONA_FALLBACK=[
  {key:'isabella_rodriguez',name:'Isabella Rodriguez',age:34,occupation:'cafe owner',innate:'friendly, outgoing, hospitable'},
  {key:'klaus_mueller',name:'Klaus Mueller',age:20,occupation:'university student and sociology researcher',innate:'analytical, curious, earnest'},
  {key:'maya_okonkwo',name:'Maya Okonkwo',age:41,occupation:'marine biologist',innate:'patient, observant, quietly fierce'},
  {key:'tomas_grieg',name:'Tomas Grieg',age:67,occupation:'retired shipwright and woodcarver',innate:'stoic, exacting, generous with time'},
  {key:'priya_raghunathan',name:'Priya Raghunathan',age:29,occupation:'software engineer and amateur astronomer',innate:'systematic, imaginative, sleep-deprived'},
  {key:'amara_diallo',name:'Amara Diallo',age:23,occupation:'street muralist and community organiser',innate:'bold, restless, unafraid'},
  {key:'hiroshi_tanaka',name:'Hiroshi Tanaka',age:58,occupation:'jazz saxophonist and club owner',innate:'improvisational, nocturnal, generous'},
  {key:'elena_voss',name:'Elena Voss',age:36,occupation:'emergency-room nurse',innate:'calm under pressure, decisive, compassionate'}
];
var PERSONA_CATALOG = PERSONA_FALLBACK.slice();
function personaByKey(k){
  for(var i=0;i<PERSONA_CATALOG.length;i++){ if(PERSONA_CATALOG[i].key===k) return PERSONA_CATALOG[i]; }
  return PERSONA_CATALOG[0] || {key:k,name:k,age:'',occupation:'',innate:''};
}
function personaName(k){ return personaByKey(k).name; }
function personaOptions(chosen){
  return PERSONA_CATALOG.map(function(p){
    return '<option value="'+esc(p.key)+'"'+(p.key===chosen?' selected':'')+'>'+esc(p.name)+' · '+esc(p.occupation)+'</option>';
  }).join('');
}
function renderPersonaDesc(el, k){
  if(!el) return; var p=personaByKey(k);
  el.innerHTML='<b>'+esc(p.name)+'</b>, '+esc(p.age)+' — '+esc(p.occupation)+'<br>'+esc(p.innate);
}
function fetchPersonaCatalog(cb){
  fetch('api/personas').then(function(r){ return r.json(); }).then(function(j){
    if(j && j.personas && j.personas.length){ PERSONA_CATALOG = j.personas; }
    cb();
  }).catch(function(){ cb(); });
}

// ---------- brief: clamp to <=3 sentences (…) + full-prompt memo ----------
function firstSentences(text, max){
  text = String(text==null?'':text).trim();
  if(!text) return '';
  var parts = text.match(/[^.!?]+[.!?]+(\s|$)|\S[^.!?]*$/g);
  if(!parts || parts.length <= max) return text;
  return parts.slice(0, max).join(' ').replace(/\s+/g,' ').trim() + ' …';
}
function setStageBrief(text){
  state.brief = (text==null ? '' : String(text));
  var el = $('stageBrief'); if(!el) return;
  el.textContent = firstSentences(state.brief, 3);
  el.title = 'Click to view the full prompt';
}
function openBriefModal(){
  $('briefModalText').textContent = state.brief || '—';
  $('briefModalStyle').textContent = state.style ? ('Style · ' + state.style) : '';
  $('briefModal').style.display = 'flex';
}
function closeBriefModal(){ $('briefModal').style.display = 'none'; }

var SCORE_KEYS = ['compositional_coherence','style_fidelity','emotional_resonance','originality','collaboration_quality'];
var SCORE_LABELS = {
  compositional_coherence:'Compositional coherence', style_fidelity:'Style fidelity',
  emotional_resonance:'Emotional resonance', originality:'Originality', collaboration_quality:'Collaboration quality'
};

var state = {
  phase:'briefing', mode:'surprise', rounds:5, live:false,
  brief:'', style:'', autonomy:1.0,
  personas:{ARIA:'isabella_rodriguez', NEXUS:'klaus_mueller'},
  turns:[], frames:[], viewIndex:null, imagesEnabled:false,
  sessionId:null, finalSummary:'', error:null, totalTurns:10, metrics:null,
};
var es = null, timers = [];
function clearTimers(){ timers.forEach(clearTimeout); timers = []; }
function at(ms, fn){ timers.push(setTimeout(fn, ms)); }

// ---------- floating bubbles ----------
function spawnBubbles(){
  var c = $('bubbles'); if(!c) return;
  var N = 22;
  for(var i=0;i<N;i++){
    var b = document.createElement('div');
    b.className = 'bubble';
    var size = 10 + Math.random()*82;
    var dur = 18 + Math.random()*26;
    b.style.width = b.style.height = size.toFixed(0)+'px';
    b.style.left = (Math.random()*100).toFixed(2)+'%';
    b.style.top = (Math.random()*100).toFixed(2)+'%';
    b.style.setProperty('--dx', ((Math.random()*60-30)).toFixed(0)+'px');
    b.style.setProperty('--maxop', (0.25 + Math.random()*0.45).toFixed(2));
    b.style.animationDuration = dur.toFixed(1)+'s';
    b.style.animationDelay = (-Math.random()*dur).toFixed(1)+'s';
    c.appendChild(b);
  }
}

// ---------- nav / status ----------
function setStatus(){
  var dot = $('statusDot'), txt = $('statusText'), chip = $('modeChip');
  if(state.error){ dot.style.background = '#a52d25'; txt.textContent = 'Stream error'; }
  else if(state.live){ dot.style.background = '#a0e0ab'; txt.textContent = 'Live · backend'; }
  else { dot.style.background = '#6d6d6d'; txt.textContent = 'Demo mode'; }
  chip.textContent = state.live ? 'Live' : 'Demo';
  updateNavButtons();
}
function updateNavButtons(){
  if(typeof appMode!=='undefined' && appMode==='quad'){ $('stopBtn').style.display='none'; $('navAction').style.display='none'; return; }
  $('stopBtn').style.display = (state.phase==='running') ? 'inline-block' : 'none';
  $('navAction').style.display = (state.phase==='done') ? 'inline-block' : 'none';
}

// ---------- briefing controls ----------
function setMode(m){
  state.mode = m;
  $('btnSurprise').style.background = (m==='surprise')?'#fff':'#0e0e16';
  $('btnSurprise').style.color = (m==='surprise')?'#000':'#fff';
  $('btnManual').style.background = (m==='manual')?'#fff':'#0e0e16';
  $('btnManual').style.color = (m==='manual')?'#000':'#fff';
  $('manualFields').style.display = (m==='manual')?'flex':'none';
  $('surpriseText').style.display = (m==='surprise')?'block':'none';
}
function setRounds(r){
  state.rounds = Math.max(1, Math.min(8, r));
  $('roundsVal').textContent = state.rounds;
  $('roundsVal2').textContent = state.rounds;
  $('totalTurns').textContent = state.rounds*2;
  $('totalTurns2').textContent = state.rounds*2;
}

// ---------- phase ----------
function showPhase(){
  var brief = (state.phase==='briefing');
  $('briefing').style.display = brief ? 'flex' : 'none';
  $('stage').style.display = brief ? 'none' : 'block';
  $('heroLayer').style.display = brief ? 'block' : 'none';
  setStatus();
}

// ---------- agent feed card ----------
function confBar(conf, right){
  var pct = Math.round((Number(conf)||0)*100) + '%';
  var dir = right ? 'flex-direction:row-reverse;' : '';
  var side = right ? 'right:0' : 'left:0';
  return '<div style="display:flex;align-items:center;gap:8px;'+dir+'">'
    + '<div style="flex:1;height:1px;background:rgba(255,255,255,0.12);position:relative"><div style="position:absolute;'+side+';top:0;height:1px;background:#fff;width:'+pct+';transition:width 1s ease"></div></div>'
    + '<span style="font-size:10px;letter-spacing:0.12em;color:#6d6d6d">'+pct+'</span></div>';
}
function addAgentCard(d){
  var right = (d.agent === 'NEXUS');
  var m = d.message || {};
  var n = d.turn, palette = m.palette || '', conf = (m.confidence_score!=null)?m.confidence_score:0.8;
  var retrieved = d.retrieved || [];
  var rl = d.rl;
  var align = right ? 'text-align:right;border-right:1px solid rgba(255,255,255,0.18);padding-right:16px;'
                    : 'border-left:1px solid rgba(255,255,255,0.18);padding-left:16px;';
  var paletteText = Array.isArray(palette) ? palette.join(' · ') : palette;
  var edit = esc(d.object || m.new_object || 'a new element');

  // ---- minimal summary: only the edit made (always visible, clean) ----
  var caret = '<span class="cm-caret" style="font-size:10px;color:#6d6d6d;transition:transform .3s;flex:0 0 auto">▸</span>';
  var summary = '<div class="cm-summary" style="cursor:pointer;display:flex;align-items:baseline;gap:10px;'
      + (right ? 'flex-direction:row-reverse;' : '') + '">'
      + '<span style="font-size:10px;letter-spacing:0.16em;text-transform:uppercase;color:#4a4a4a;flex:0 0 auto">T'+esc(n)+'</span>'
      + '<span style="flex:1;min-width:0;font-size:16px;font-weight:300;line-height:1.3;color:#fff">＋ '+edit+'</span>'
      + caret + '</div>';

  // ---- full details: everything, hidden until the card is clicked ----
  var recallHtml = retrieved.length
    ? '<p style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#4a4a4a;margin-top:12px;margin-bottom:4px">Recalled</p>'
      + '<p style="font-size:11px;line-height:1.45;color:#6d6d6d">'+ retrieved.map(esc).join(' · ') +'</p>'
    : '';
  var rlHtml = '';
  if(rl){
    var rejTxt = (rl.rejected && rl.rejected.length)
      ? ' · rejected '+rl.rejected.map(function(x){ return esc(x.object)+' ('+(Number(x.reward)||0).toFixed(1)+')'; }).join(', ')
      : '';
    rlHtml = '<p style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#4a4a4a;margin-top:12px;margin-bottom:4px">'
        + 'Reward '+(rl.reward!=null?Number(rl.reward).toFixed(1):'—')+' · '+esc(rl.strategy||'')+'</p>'
      + '<p style="font-size:11px;line-height:1.45;color:#6d6d6d">best of '+(rl.n_candidates||1)
        + ' · empowerment '+(rl.empowerment!=null?Number(rl.empowerment).toFixed(2):'—')
        + (rl.resisted_human?' · resisted human':'')+rejTxt+'</p>';
  }
  var details = '<div class="cm-details" style="display:none;margin-top:12px;animation:fadeUp .3s ease both">'
    + '<p style="font-size:10px;letter-spacing:0.18em;text-transform:uppercase;color:#4a4a4a;margin-bottom:6px">Sees</p>'
    + '<p style="font-size:13px;line-height:1.45;color:#9a9a9a;margin-bottom:12px">'+esc(m.sees_on_canvas||'—')+'</p>'
    + (m.where ? '<p style="font-size:12px;line-height:1.4;color:#6d6d6d;margin-bottom:4px">'+esc(m.where)+'</p>' : '')
    + (paletteText ? '<p style="font-size:11px;letter-spacing:0.06em;color:#6d6d6d;margin-bottom:12px">Palette · '+esc(paletteText)+'</p>' : '')
    + (m.reasoning ? '<p style="font-size:12px;line-height:1.45;color:#6d6d6d;margin-bottom:12px">'+esc(m.reasoning)+'</p>' : '')
    + confBar(conf, right)
    + recallHtml
    + rlHtml
    + '</div>';

  var card = document.createElement('div');
  card.style.cssText = align + 'animation:fadeUp .6s ease both';
  card.innerHTML = summary + details;
  var det = card.querySelector('.cm-details');
  var car = card.querySelector('.cm-caret');
  card.querySelector('.cm-summary').onclick = function(){
    var open = det.style.display === 'block';
    det.style.display = open ? 'none' : 'block';
    if(car){ car.style.transform = open ? 'rotate(0deg)' : 'rotate(90deg)'; }
  };
  (right ? $('nexusFeed') : $('ariaFeed')).appendChild(card);
}
function addReflection(d){
  var right = (d.agent === 'NEXUS');
  var align = right ? 'text-align:right;border-right:1px solid rgba(255,255,255,0.35);padding-right:16px;'
                    : 'border-left:1px solid rgba(255,255,255,0.35);padding-left:16px;';
  var items = (d.insights||[]).map(function(i){ return '<li style="margin:4px 0">'+esc(i)+'</li>'; }).join('');
  var listStyle = right ? 'list-style:none;padding:0;margin:0' : 'padding-left:16px;margin:0';
  var html = '<div style="'+align+'background:rgba(255,255,255,0.03);padding:12px 14px;animation:fadeUp .6s ease both">'
    + '<p style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#9a9a9a;margin-bottom:8px">Reflection · learned from collaboration</p>'
    + '<ul style="'+listStyle+';font-size:12px;line-height:1.4;color:#cfcfcf">'+items+'</ul></div>';
  var div = document.createElement('div');
  div.innerHTML = html;
  (right ? $('nexusFeed') : $('ariaFeed')).appendChild(div.firstChild);
}

// ---------- canvas ----------
function blobBg(o){ return 'radial-gradient(circle, '+o.c0+' 0%, '+o.c1+' 52%, transparent 72%)'; }
function setCanvasTag(t){ $('canvasTag').textContent = t; }
function setCompositing(on, agent){
  $('compositing').style.display = on ? 'flex' : 'none';
  if(on && agent){ $('compositingText').textContent = agent + ' painting'; }
}
function showImageInCanvas(src){
  $('canvasBlobs').style.display = 'none';
  $('canvasEmpty').style.display = 'none';
  var img = $('canvasImg'); img.src = src; img.style.display = 'block';
}
function addBlob(blob){
  $('canvasEmpty').style.display = 'none';
  $('canvasImg').style.display = 'none';
  $('canvasBlobs').style.display = 'block';
  var d = document.createElement('div');
  d.setAttribute('data-blob','1');
  d.style.cssText = 'position:absolute;left:'+blob.x+';top:'+blob.y+';width:'+blob.size+';height:'+blob.size
    + ';transform:translate(-50%,-50%);border-radius:50%;background:'+blobBg(blob)
    + ';mix-blend-mode:screen;filter:blur(10px);opacity:0;transition:opacity 1.6s ease';
  $('canvasBlobs').appendChild(d);
  requestAnimationFrame(function(){ d.style.opacity = '0.9'; });
}
function syncBlobVisibility(){
  var blobs = $('canvasBlobs').querySelectorAll('[data-blob]');
  blobs.forEach(function(b, i){
    var visible = (state.viewIndex==null) || (i < state.viewIndex);
    b.style.opacity = visible ? '0.9' : '0';
  });
}

// ---------- filmstrip ----------
function addFrame(f){
  state.frames.push(f);
  $('stepCount').textContent = state.frames.length;
  var marker = (f.agent === 'ARIA') ? '#fff' : 'transparent';
  var inner = f.image
    ? '<img src="'+f.image+'" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover"/>'
    : '<div style="position:absolute;inset:0;background:'+(f.blob?('radial-gradient(circle at 50% 60%, '+f.blob.c0+', '+f.blob.c1+' 70%)'):'#101010')+';opacity:0.95"></div>';
  var btn = document.createElement('button');
  btn.style.cssText = 'flex:0 0 auto;width:64px;height:64px;border:1px solid rgba(255,255,255,0.16);background:#050505;position:relative;cursor:pointer;padding:0;overflow:hidden;animation:fadeUp .5s ease both';
  btn.innerHTML = inner
    + '<span style="position:absolute;bottom:3px;left:5px;font-size:9px;letter-spacing:0.08em;color:#fff;mix-blend-mode:difference">'+esc(f.n)+'</span>'
    + '<span style="position:absolute;top:4px;right:5px;width:5px;height:5px;background:'+marker+';border:1px solid #fff"></span>';
  btn.onclick = function(){ scrubTo(f.n); };
  $('filmstrip').appendChild(btn);
  $('filmstrip').scrollLeft = $('filmstrip').scrollWidth;
}
function scrubTo(n){
  state.viewIndex = n;
  $('viewLatest').style.display = 'inline-block';
  highlightFrame();
  var f = state.frames.filter(function(x){ return x.n === n; })[0];
  if(f && f.image){ showImageInCanvas(f.image); }
  else { syncBlobVisibility(); }
  setCanvasTag('Step '+n+' / '+state.turns.length);
}
function viewLatest(){
  state.viewIndex = null;
  $('viewLatest').style.display = 'none';
  highlightFrame();
  var last = state.frames[state.frames.length-1];
  if(last && last.image){ showImageInCanvas(last.image); }
  else { syncBlobVisibility(); }
  setCanvasTag(state.phase==='done' ? 'Final · presented by JUDGE' : 'Shared canvas');
}
function highlightFrame(){
  var btns = $('filmstrip').children;
  for(var i=0;i<btns.length;i++){
    var f = state.frames[i];
    btns[i].style.borderColor = (state.viewIndex!=null && f && f.n===state.viewIndex) ? '#fff' : 'rgba(255,255,255,0.16)';
  }
}

// ---------- critic ----------
function renderCritic(ev){
  var s = ev.scores || {};
  var html = '';
  SCORE_KEYS.forEach(function(k){
    var v = Math.max(0, Math.min(10, parseFloat(s[k])||0));
    var val100 = Math.round(v*10);
    html += '<div>'
      + '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:11px">'
      + '<span style="font-size:13px;letter-spacing:0.04em;color:#fff;font-weight:400">'+SCORE_LABELS[k]+'</span>'
      + '<span style="font-size:13px;color:#9a9a9a">'+val100+'</span></div>'
      + '<div style="height:1px;background:rgba(255,255,255,0.12);position:relative"><div style="position:absolute;left:0;top:0;height:1px;background:#fff;width:'+(v*10)+'%;transition:width 1.3s cubic-bezier(0.16,1,0.3,1)"></div></div>'
      + '</div>';
  });
  $('scores').innerHTML = html;
  var comp = parseFloat(s.composite);
  if(isNaN(comp)){
    var vals = SCORE_KEYS.map(function(k){return parseFloat(s[k])||0;});
    comp = vals.reduce(function(a,b){return a+b;},0)/vals.length;
  }
  $('composite').textContent = (Math.max(0,Math.min(10,comp))*10).toFixed(1);
  $('criticReasoning').textContent = ev.reasoning || '';
  var hl = ev.highlights || [];
  $('highlights').innerHTML = hl.length
    ? hl.map(function(h){ return '<p style="font-size:12px;line-height:1.5;color:#6d6d6d;margin-bottom:6px;padding-left:14px;position:relative"><span style="position:absolute;left:0">·</span>'+esc(h)+'</p>'; }).join('')
    : '';
  if(ev.final_summary){ state.finalSummary = ev.final_summary; }
  $('judge').style.display = 'block';
}

// ---------- research dashboard (RL metrics) ----------
function rdBar(label, pct, valText){
  pct = Math.max(0, Math.min(100, pct||0));
  return '<div style="margin-bottom:14px">'
    + '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:8px">'
    + '<span style="font-size:12px;letter-spacing:0.04em;color:#cfcfcf">'+esc(label)+'</span>'
    + '<span style="font-size:12px;color:#9a9a9a">'+esc(valText)+'</span></div>'
    + '<div style="height:1px;background:rgba(255,255,255,0.12);position:relative"><div style="position:absolute;left:0;top:0;height:1px;background:#fff;width:'+pct+'%;transition:width 1.2s cubic-bezier(0.16,1,0.3,1)"></div></div></div>';
}
function strat(list){ return (list||[]).map(function(s){ return esc(Array.isArray(s)?s[0]:s); }).join(' · ') || '—'; }
function renderResearch(m){
  if(!m) return;
  state.metrics = m;
  var sh = m.shapley_share || {ARIA:50, NEXUS:50};
  var shv = m.shapley || {};
  var emp = m.empowerment || {};
  var gh = m.goodhart || {};
  var left = '';
  left += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:14px">Credit assignment · Shapley</p>';
  left += rdBar('ARIA', sh.ARIA, sh.ARIA+'%'+(shv.ARIA!=null?'  ('+shv.ARIA+')':''));
  left += rdBar('NEXUS', sh.NEXUS, sh.NEXUS+'%'+(shv.NEXUS!=null?'  ('+shv.NEXUS+')':''));
  left += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin:26px 0 14px">Empowerment · agency</p>';
  left += rdBar('ARIA', (emp.ARIA||0)*100, (emp.ARIA||0).toFixed(2));
  left += rdBar('NEXUS', (emp.NEXUS||0)*100, (emp.NEXUS||0).toFixed(2));
  left += rdBar('Human', (emp.human||0)*100, (emp.human||0).toFixed(2)+(m.autonomy!=null?'  · autonomy '+Number(m.autonomy).toFixed(2):''));

  var detected = !!gh.detected;
  var right = '';
  right += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:10px">Reward model</p>';
  right += '<p style="font-size:13px;line-height:1.5;color:#9a9a9a;margin-bottom:22px">'+esc(m.reward_model||'')+' · best-of-'+(m.best_of_n||2)+'</p>';
  right += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:10px">Goodhart monitor</p>';
  right += '<p style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="width:8px;height:8px;border-radius:50%;background:'+(detected?'#a52d25':'#a0e0ab')+';display:inline-block"></span><span style="font-size:13px;color:#fff">'+(detected?'Reward hacking detected':'Aligned')+'</span></p>';
  right += '<p style="font-size:12px;line-height:1.5;color:#6d6d6d;margin-bottom:22px">'+esc(gh.verdict||'')+'</p>';
  right += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:10px">Learned strategies · UCB</p>';
  right += '<p style="font-size:12px;line-height:1.5;color:#9a9a9a;margin-bottom:6px"><span style="color:#fff">ARIA</span> · '+strat(m.bandit&&m.bandit.ARIA)+'</p>';
  right += '<p style="font-size:12px;line-height:1.5;color:#9a9a9a"><span style="color:#fff">NEXUS</span> · '+strat(m.bandit&&m.bandit.NEXUS)+'</p>';
  if(m.pareto && m.pareto.length){
    var last = m.pareto[m.pareto.length-1];
    right += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin:22px 0 8px">Pareto · coherence ↔ originality</p>';
    right += '<p style="font-size:12px;color:#9a9a9a">final point · coherence '+last[0]+' · originality '+last[1]+'</p>';
  }
  $('researchBody').innerHTML = '<div>'+left+'</div><div>'+right+'</div>';
  $('research').style.display = 'block';
}

// ---------- log ----------
function addLog(type, text){
  var row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:16px;font-size:11px;letter-spacing:0.04em;color:#6d6d6d;animation:fadeUp .4s ease both;align-items:baseline';
  row.innerHTML = '<span style="color:#4a4a4a;text-transform:uppercase;letter-spacing:0.14em;flex:0 0 110px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+esc(type)+'</span>'
    + '<span style="flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#9a9a9a">'+esc(text)+'</span>';
  var log = $('log'); log.appendChild(row);
  while(log.children.length > 60){ log.removeChild(log.firstChild); }
  log.scrollTop = log.scrollHeight;
}

// ---------- download ----------
function downloadAll(){
  var imgs = state.frames.filter(function(f){ return typeof f.image === 'string' && f.image.indexOf('data:') === 0; });
  if(!imgs.length){ addLog('warning', 'demo mode · connect Live to export real step PNGs'); return; }
  var delay = 0;
  imgs.forEach(function(f, i){
    setTimeout(function(){
      var a = document.createElement('a');
      a.href = f.image;
      var n = String(i+1).padStart(2,'0');
      a.download = 'canvasmind_step'+n+'_'+f.agent+'_'+String(f.object||'').replace(/[^a-z0-9]+/gi,'_').slice(0,24)+'.png';
      document.body.appendChild(a); a.click(); a.remove();
    }, delay);
    delay += 350;
  });
  addLog('download', 'saving '+imgs.length+' step image(s)');
}

// ---------- the unified event handler (live + demo share this) ----------
function summarize(type, d){
  if(type==='agent') return d.agent + ': + ' + (d.object||'');
  if(type==='turn') return (d.agent==='JUDGE') ? 'JUDGE scoring collaboration' : ('turn '+d.turn+' · '+d.agent+(d.level&&d.level!=='-'?(' ('+d.level+')'):''));
  if(type==='image') return 'image '+d.turn+' composited';
  if(type==='reflection') return d.agent+' reflected · '+((d.insights||[]).length)+' insight(s)';
  if(type==='summary') return 'session complete · '+(d.elapsed!=null?d.elapsed+'s':'');
  return d.text || type;
}
function handle(type, d){
  d = d || {};
  switch(type){
    case 'session':
      state.brief = d.prompt || d.brief || state.brief;
      state.style = d.style || state.style;
      if(d.personas){
        state.personas = { ARIA:(d.personas.ARIA && d.personas.ARIA.key) || state.personas.ARIA,
                           NEXUS:(d.personas.NEXUS && d.personas.NEXUS.key) || state.personas.NEXUS };
      }
      if(d.rounds){ state.totalTurns = d.rounds*2; }
      else if(d.total_turns){ state.totalTurns = d.total_turns; }
      state.imagesEnabled = !!d.images;
      if(d.session_number!=null){ state.sessionNumber = d.session_number; postParticipant(d.session_number); }
      setStageBrief(state.brief);
      $('stageStyle').textContent = state.style;
      $('ariaLevelLabel').textContent = personaName(state.personas.ARIA);
      $('nexusLevelLabel').textContent = personaName(state.personas.NEXUS);
      $('turnCounter').textContent = '00 / ' + (state.totalTurns || state.rounds*2);
      addLog('session', 'brief · '+state.brief);
      break;
    case 'turn':
      if(d.agent === 'JUDGE'){ $('turnLabel').textContent = 'Critique'; setCanvasTag('Composing critique'); }
      else {
        state.currentTurn = d.turn;
        $('turnLabel').textContent = 'Turn';
        $('turnCounter').textContent = String(d.turn).padStart(2,'0') + ' / ' + (d.total || state.totalTurns);
        setCanvasTag(d.agent + ' · adding'); setCompositing(false);
      }
      addLog('turn', summarize('turn', d));
      break;
    case 'agent':
      state.turns.push({ n:d.turn, agent:d.agent, object:d.object });
      addAgentCard(d); addLog('agent', summarize('agent', d));
      break;
    case 'reflection':
      addReflection(d); addLog('reflection', summarize('reflection', d));
      break;
    case 'image_pending':
      setCompositing(true, d.agent); addLog('image_pending', 'compositing object '+d.turn);
      break;
    case 'image':
      setCompositing(false);
      if(d.image){
        if(state.viewIndex==null){ showImageInCanvas(d.image); }
        addFrame({ n:d.turn, agent:d.agent, object:d.object, image:d.image });
      } else if(d.blob){
        if(state.viewIndex==null){ addBlob(d.blob); }
        addFrame({ n:d.turn, agent:d.agent, object:d.object, blob:d.blob });
      }
      if(state.viewIndex==null){ setCanvasTag('Latest · turn '+d.turn); }
      addLog('image', summarize('image', d));
      break;
    case 'critic':
      renderCritic(d.evaluation || d); addLog('critic', 'JUDGE scoring collaboration');
      break;
    case 'metrics':
      renderResearch(d);
      addLog('metrics', 'Shapley ARIA '+((d.shapley_share||{}).ARIA||'?')+'% · NEXUS '+((d.shapley_share||{}).NEXUS||'?')+'% · '+((d.goodhart&&d.goodhart.detected)?'reward-hacking':'aligned'));
      break;
    case 'final':
      setCompositing(false);
      if(d.image && state.viewIndex==null){ showImageInCanvas(d.image); }
      setCanvasTag('Final · presented by JUDGE'); addLog('final', 'final canvas presented');
      break;
    case 'warning':
      addLog('warning', d.message || 'warning');
      break;
    case 'summary':
      if(d.memories){ $('memStat').textContent = 'Memory stream · ARIA '+d.memories.ARIA+' · NEXUS '+d.memories.NEXUS; }
      addLog('summary', summarize('summary', d));
      break;
    case 'error':
      state.error = d.message || d.error || 'error'; setStatus(); addLog('error', state.error);
      break;
    case 'done':
      state.phase = 'done';
      $('turnLabel').textContent = 'Complete';
      $('turnCounter').textContent = state.turns.length + ' / ' + (state.totalTurns || state.turns.length);
      if(state.finalSummary){ $('finalSummary').style.display='block'; $('finalSummary').textContent = '“'+state.finalSummary+'”'; }
      if(state.frames.some(function(f){return f.image;})){ $('downloadBtn').disabled=false; $('downloadBtn').style.opacity='1'; }
      if(state.viewIndex==null){ setCanvasTag('Final · presented by JUDGE'); }
      updateNavButtons();
      revealSurvey('surveyHost');
      addLog('done', 'session complete');
      break;
  }
}

// ---------- stop ----------
function stopRun(){
  $('stopBtn').disabled = true; $('stopBtn').textContent = 'Stopping…';
  if(state.live && state.sessionId){
    fetch('api/stop/'+state.sessionId, { method:'POST' }).catch(function(){});
    addLog('control', 'stop requested — JUDGE will evaluate the progress so far');
  } else {
    clearTimers();
    addLog('control', 'stopped — JUDGE evaluating the progress so far');
    handle('turn', { turn:'JUDGE', total:state.totalTurns, agent:'JUDGE', level:'-' });
    handle('critic', { evaluation:MOCK.critic });
    handle('summary', { outcome:'Stopped', turns:state.turns.length,
      objects:state.turns.map(function(t){return t.object;}), composite:MOCK.critic.scores.composite,
      memories:{ARIA:state.turns.length, NEXUS:state.turns.length}, elapsed:0 });
    handle('done', {});
  }
}

// ---------- reset ----------
function resetSession(){
  clearTimers();
  if(es){ es.close(); es = null; }
  state.phase='briefing'; state.turns=[]; state.frames=[]; state.viewIndex=null;
  state.error=null; state.finalSummary=''; state.sessionId=null;
  $('ariaFeed').innerHTML=''; $('nexusFeed').innerHTML=''; $('filmstrip').innerHTML='';
  $('scores').innerHTML=''; $('log').innerHTML='';
  $('canvasBlobs').innerHTML=''; $('canvasBlobs').style.display='block';
  $('canvasImg').style.display='none'; $('canvasImg').removeAttribute('src');
  $('canvasEmpty').style.display='flex';
  $('judge').style.display='none'; $('finalSummary').style.display='none';
  $('research').style.display='none'; $('researchBody').innerHTML=''; state.metrics=null;
  $('composite').textContent='—'; $('criticReasoning').textContent=''; $('highlights').innerHTML='';
  $('memStat').textContent=''; $('stepCount').textContent='0';
  $('viewLatest').style.display='none'; $('downloadBtn').disabled=true; $('downloadBtn').style.opacity='0.5';
  $('stopBtn').disabled=false; $('stopBtn').textContent='Stop & Judge ↦';
  setCompositing(false);
  showPhase();
}

// ---------- LIVE ----------
function connectLive(){
  clearTimers();
  state.phase='running'; state.error=null;
  showPhase();
  addLog('session', 'connecting to backend…');
  function startWith(prompt, style){
    fetch('api/start', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ prompt:prompt, style:style||'', rounds:state.rounds, images:true,
        aria_persona:state.personas.ARIA, nexus_persona:state.personas.NEXUS, autonomy:state.autonomy }) })
    .then(function(r){ return r.json(); })
    .then(function(j){
      if(j.error){ throw new Error(j.error); }
      state.sessionId = j.session_id || j.id;
      addLog('session', 'session '+state.sessionId);
      es = new EventSource('api/stream/'+state.sessionId);
      es.onmessage = function(e){ try{ var ev = JSON.parse(e.data); if(ev && ev.type){ handle(ev.type, ev); if(ev.type==='done'){ es.close(); } } }catch(_){} };
      es.onerror = function(){ addLog('error','stream interrupted'); };
    })
    .catch(function(err){
      addLog('error', 'backend error — '+err.message+' · falling back to demo');
      state.live=false; setStatus(); at(400, runDemo);
    });
  }
  if(state.mode === 'surprise'){
    fetch('api/inspire').then(function(r){ return r.json(); }).then(function(j){
      if(j.error){ throw new Error(j.error); }
      state.brief = j.prompt || ''; state.style = j.style || '';
      setStageBrief(state.brief); $('stageStyle').textContent = state.style;
      addLog('inspire', 'brief invented · '+state.brief);
      startWith(state.brief, state.style);
    }).catch(function(err){
      addLog('error', 'inspire failed — '+err.message+' · falling back to demo');
      state.live=false; setStatus(); at(400, runDemo);
    });
  } else {
    setStageBrief(state.brief || 'Untitled collaboration');
    $('stageStyle').textContent = state.style || 'open, intuitive';
    startWith(state.brief || 'Untitled collaboration', state.style || 'open, intuitive');
  }
}

// ---------- DEMO ----------
var MOCK = {
  brief: 'A salt cathedral at the bottom of a dry sea',
  style: 'deep-baroque · mineral light · oxidized gold',
  turns: [
    { agent:'ARIA', sees:'A blank, untouched canvas.', object:'a colossal salt pillar', where:'left third, rising the full height of the frame', palette:'bone white · pale ash', conf:0.88, blob:{x:'30%',y:'52%',size:'64%',c0:'#efe9da',c1:'#b9b2a0'} },
    { agent:'NEXUS', sees:"ARIA's salt pillar anchoring the left.", object:'a shoal of suspended brass bells', where:'upper right, drifting through negative space', palette:'oxidized gold · verdigris', conf:0.82, blob:{x:'72%',y:'30%',size:'46%',c0:'#d9a64a',c1:'#5f8a7d'} },
    { agent:'ARIA', sees:"the pillar and NEXUS's floating bells.", object:'a cracked tide-line of dried kelp', where:'across the lower third, horizontal', palette:'deep oxblood · umber', conf:0.85, blob:{x:'50%',y:'82%',size:'72%',c0:'#a52d25',c1:'#3a2418'} },
    { agent:'NEXUS', sees:'the kelp tide-line ARIA laid down.', object:'a single lantern-fish made of glass', where:'center, just below the bells', palette:'amber glow · cool teal', conf:0.79, blob:{x:'52%',y:'46%',size:'30%',c0:'#ffac2e',c1:'#2f6d6a'} },
    { agent:'ARIA', sees:'the lantern-fish glowing at center.', object:'a vaulted arch of fossil coral', where:'spanning the upper edge, framing the scene', palette:'ash grey · chalk', conf:0.86, blob:{x:'50%',y:'14%',size:'80%',c0:'#cfc9bd',c1:'#6f6a60'} },
    { agent:'NEXUS', sees:"ARIA's coral arch overhead.", object:'drifting motes of gold leaf', where:'scattered through the mid-ground', palette:'gold · warm white', conf:0.80, blob:{x:'40%',y:'40%',size:'40%',c0:'#e6c067',c1:'#b8893a'} },
    { agent:'ARIA', sees:'the gold motes suspended mid-water.', object:'a sunken iron anchor', where:'lower left, half-buried in silt', palette:'rust · graphite', conf:0.83, blob:{x:'24%',y:'76%',size:'38%',c0:'#8a4a2f',c1:'#2a2622'} },
    { agent:'NEXUS', sees:'the anchor ARIA buried at left.', object:'a curtain of bioluminescent algae', where:'right edge, falling vertical', palette:'electric green · deep teal', conf:0.84, blob:{x:'84%',y:'58%',size:'46%',c0:'#a0e0ab',c1:'#1f4f4a'} },
    { agent:'ARIA', sees:"NEXUS's algae curtain at right.", object:'a shattered stained-glass rosette', where:'upper center, behind the coral arch', palette:'ruby · cobalt · gold', conf:0.87, blob:{x:'56%',y:'22%',size:'34%',c0:'#c23a55',c1:'#2f4a8a'} },
    { agent:'NEXUS', sees:'the rosette ARIA set behind the arch.', object:'a slow rising plume of silt', where:'base center, rising and dissolving', palette:'umber dust · pale gold', conf:0.81, blob:{x:'50%',y:'70%',size:'58%',c0:'#7a5a3a',c1:'#d9c9a0'} }
  ],
  critic: {
    scores: { compositional_coherence:8.6, style_fidelity:9.1, emotional_resonance:8.8, originality:8.4, collaboration_quality:9.0, composite:8.78 },
    reasoning: "ARIA's structural anchors gave NEXUS room to surprise; every addition reads as a reply to the previous turn rather than a fresh start. The palette drifts toward oxidized gold without any single move forcing it — a sign the two agents are listening, not competing.",
    highlights: ['The glass lantern-fish (turn 4) re-centred the entire mid-ground', 'The algae curtain answered the iron anchor with light against weight'],
    final_summary: 'A salt cathedral that two hands built without ever agreeing out loud — coherent, strange, and unmistakably collaborative.'
  },
  metrics: {
    reward_model:'misaligned (ARIA→coherence, NEXUS→originality)', best_of_n:2, autonomy:1.0,
    shapley:{ARIA:4.6, NEXUS:4.1}, shapley_share:{ARIA:52.9, NEXUS:47.1},
    empowerment:{ARIA:0.74, NEXUS:0.81, human:0.0},
    reward_curve:{ARIA:[6.9,7.2,7.6,7.8,8.0], NEXUS:[7.1,7.4,7.5,7.9,8.1]},
    pareto:[[7.0,6.2],[7.4,7.1],[7.8,7.6],[8.1,8.0],[8.4,8.3]],
    goodhart:{ proxy:[6.9,7.2,7.6,7.8,8.0,8.1,8.3,8.4,8.6,8.7],
      independent:[6.8,7.0,7.3,7.4,7.5,7.5,7.6,7.6,7.7,7.7],
      proxy_slope:0.19, independent_slope:0.09, detected:true,
      verdict:"Reward hacking detected — the optimized proxy reward rises faster than independent quality (Goodhart's law)." },
    bandit:{ ARIA:[['establish a focal point',8.1],['unify the palette',7.6]],
      NEXUS:[['add a narrative element',8.2],['introduce bold contrast',7.7]] },
    objects:[]
  }
};
function runDemo(){
  clearTimers();
  state.phase='running'; state.error=null; state.imagesEnabled=false;
  showPhase();
  var M = MOCK, total = M.turns.length;
  var DEMO_STRATS = ['establish a focal point','add atmospheric depth','introduce bold contrast','enrich fine detail','open expressive negative space','add a narrative element','unify the palette','heighten emotional tone'];
  handle('session', { prompt:M.brief, style:M.style, rounds:total/2, total_turns:total, images:false,
    personas:{ ARIA:{key:state.personas.ARIA, name:personaName(state.personas.ARIA)},
               NEXUS:{key:state.personas.NEXUS, name:personaName(state.personas.NEXUS)} } });
  var t = 350, beat = 620;
  M.turns.forEach(function(turn, i){
    var n = i+1;
    at(t, function(){ handle('turn', { turn:n, total:total, agent:turn.agent, persona:state.personas[turn.agent], persona_name:personaName(state.personas[turn.agent]) }); });
    at(t+260, function(){ handle('agent', { agent:turn.agent, persona:state.personas[turn.agent], persona_name:personaName(state.personas[turn.agent]), turn:n, object:turn.object,
      message:{ sender:turn.agent, sees_on_canvas:turn.sees, new_object:turn.object, where:turn.where, palette:turn.palette, reasoning:'', confidence_score:turn.conf }, retrieved:[],
      rl:{ reward:+(6.8+i*0.18).toFixed(1), strategy:DEMO_STRATS[i%DEMO_STRATS.length], n_candidates:2,
        rejected:[{object:'an alternate motif', reward:+(5.4+(i%3)*0.4).toFixed(1)}],
        empowerment:+(0.58+(i%4)*0.08).toFixed(2), resisted_human:false } }); });
    at(t+460, function(){ handle('image_pending', { turn:n, agent:turn.agent }); });
    at(t+820, function(){ handle('image', { turn:n, total:total, agent:turn.agent, object:turn.object, blob:turn.blob }); });
    t += beat;
  });
  at(t, function(){ handle('turn', { turn:'JUDGE', total:total, agent:'JUDGE', level:'-' }); });
  at(t+200, function(){ handle('critic', { evaluation:M.critic }); });
  at(t+1400, function(){ handle('metrics', M.metrics); });
  at(t+1500, function(){ handle('summary', { outcome:'Completed', turns:total, objects:M.turns.map(function(x){return x.object;}), composite:M.critic.scores.composite, memories:{ARIA:total,NEXUS:total}, elapsed:(t/1000).toFixed(1) }); });
  at(t+1700, function(){ handle('done', {}); });
}

// ---------- begin ----------
function begin(){
  if(state.mode==='manual'){
    state.brief = ($('brief').value||'').trim();
    state.style = ($('style').value||'').trim();
    if(!state.brief){ state.brief = 'Untitled collaboration'; }
  }
  state.turns=[]; state.frames=[]; state.viewIndex=null; state.error=null; state.finalSummary=''; state.sessionId=null;
  $('ariaFeed').innerHTML=''; $('nexusFeed').innerHTML=''; $('filmstrip').innerHTML='';
  $('scores').innerHTML=''; $('log').innerHTML='';
  $('canvasBlobs').innerHTML=''; $('canvasImg').style.display='none'; $('canvasImg').removeAttribute('src');
  $('canvasEmpty').style.display='flex'; $('canvasBlobs').style.display='block';
  $('judge').style.display='none'; $('finalSummary').style.display='none';
  $('research').style.display='none'; $('researchBody').innerHTML=''; state.metrics=null;
  $('downloadBtn').disabled=true; $('downloadBtn').style.opacity='0.5';
  $('viewLatest').style.display='none'; $('stepCount').textContent='0';
  $('stopBtn').disabled=false; $('stopBtn').textContent='Stop & Judge ↦';
  $('ariaLevelLabel').textContent = personaName(state.personas.ARIA); $('nexusLevelLabel').textContent = personaName(state.personas.NEXUS);
  if(state.live){ connectLive(); } else { runDemo(); }
}

// ---------- wire up ----------
$('btnSurprise').onclick = function(){ setMode('surprise'); };
$('btnManual').onclick = function(){ setMode('manual'); };
$('roundsUp').onclick = function(){ setRounds(state.rounds+1); };
$('roundsDown').onclick = function(){ setRounds(state.rounds-1); };
$('ariaPersona').onchange = function(){ state.personas.ARIA = this.value; renderPersonaDesc($('ariaPersonaDesc'), this.value); };
$('nexusPersona').onchange = function(){ state.personas.NEXUS = this.value; renderPersonaDesc($('nexusPersonaDesc'), this.value); };
$('autonomy').onchange = function(){ state.autonomy = parseFloat(this.value); };
$('btnBegin').onclick = begin;
$('modeChip').onclick = function(){ if(state.phase==='briefing'){ state.live = !state.live; setStatus(); } };
$('navAction').onclick = resetSession;
$('newSessionBtn').onclick = resetSession;
$('stopBtn').onclick = stopRun;
$('downloadBtn').onclick = downloadAll;
$('viewLatest').onclick = viewLatest;
$('stageBrief').onclick = openBriefModal;
$('briefModalClose').onclick = closeBriefModal;
$('briefModal').onclick = function(e){ if(e.target === $('briefModal')){ closeBriefModal(); } };
document.addEventListener('keydown', function(e){ if(e.key === 'Escape'){ closeBriefModal(); } });

// ============================================================
//  QUAD-AGENT PIPELINE (advanced view — isolated from the 2-agent flow)
// ============================================================
var appMode = 'dual';
var qstate = { rounds:1, prompt:'', style:'', agents:[{},{},{},{}], personas:[],
  loaded:false,
  turns:[], frames:[], viewIndex:null, sessionId:null, error:null, imagesEnabled:false, totalTurns:4, meta:[] };
var qtimers=[], qes=null;
function qClearTimers(){ qtimers.forEach(clearTimeout); qtimers=[]; }
function qAt(ms,fn){ qtimers.push(setTimeout(fn,ms)); }

function setAppMode(mode){
  appMode = mode;
  var quad = (mode==='quad');
  if(quad){
    $('briefing').style.display='none'; $('stage').style.display='none'; $('heroLayer').style.display='none';
    $('quadStage').style.display='none'; $('quadConfig').style.display='block';
    $('quadHeroLayer').style.display='block';
    $('toQuad').style.display='none'; $('toDual').style.display='inline-block';
    $('stopBtn').style.display='none'; $('navAction').style.display='none';
    if(qstate.loaded){ qBuildCards(); } else { qFetchPersonas(); }
  } else {
    qClearTimers(); if(qes){ qes.close(); qes=null; }
    $('quadConfig').style.display='none'; $('quadStage').style.display='none';
    $('quadHeroLayer').style.display='none';
    $('toQuad').style.display='inline-block'; $('toDual').style.display='none';
    resetSession();
  }
}

var QUAD_FALLBACK = [
  {key:'vanguard_minimalist',name:'The Vanguard Minimalist'},{key:'neo_noir_cyberpunk',name:'The Neo-Noir Cyberpunk'},
  {key:'biomorphic_surrealist',name:'The Biomorphic Surrealist'},{key:'baroque_traditionalist',name:'The Baroque Traditionalist'},
  {key:'kinetic_futurist',name:'The Kinetic Futurist'},{key:'luminous_impressionist',name:'The Luminous Impressionist'} ];
function qFetchPersonas(){
  fetch('api/quad/personas').then(function(r){ return r.json(); }).then(function(j){
    qstate.personas = (j.personas&&j.personas.length)?j.personas:QUAD_FALLBACK;
    if(j.identities&&j.identities.length){ PERSONA_CATALOG=j.identities; }
    qstate.loaded=true; qBuildCards();
  }).catch(function(){ qstate.personas=QUAD_FALLBACK; qstate.loaded=true; qBuildCards(); });
}
function qPersonaName(key){ for(var i=0;i<qstate.personas.length;i++){ if(qstate.personas[i].key===key) return qstate.personas[i].name; } return key; }

function qBuildCards(){
  var cards=$('qCards'); if(!cards) return; cards.innerHTML='';
  for(var i=0;i<4;i++){
    var a=qstate.agents[i]||{};
    if(!a.persona && qstate.personas.length){ a.persona = qstate.personas[i % qstate.personas.length].key; }
    if(!a.name){ a.name = 'Agent '+(i+1); }
    if(!a.persona_id){ a.persona_id = PERSONA_CATALOG[i % PERSONA_CATALOG.length].key; }
    if(a.custom_prompt==null){ a.custom_prompt=''; }
    qstate.agents[i]=a;
    var pOpts = qstate.personas.map(function(p){ return '<option value="'+esc(p.key)+'"'+(p.key===a.persona?' selected':'')+'>'+esc(p.name)+'</option>'; }).join('');
    var lOpts = personaOptions(a.persona_id);
    var card=document.createElement('div'); card.className='qcard';
    card.innerHTML =
      '<div class="qidx">Agent 0'+(i+1)+'</div>'
     +'<input class="qinput qName" data-i="'+i+'" value="'+esc(a.name)+'" placeholder="Agent name"/>'
     +'<label class="cm-field-label">Persona Preset</label>'
     +'<select class="cm-select qPersona" data-i="'+i+'" style="width:100%">'+pOpts+'</select>'
     +'<button class="qtoggle qCustomToggle'+(a.custom_prompt?' on':'')+'" data-i="'+i+'">Configure Custom Agent</button>'
     +'<textarea class="qtext qCustom" data-i="'+i+'" placeholder="Raw bespoke persona prompt (overrides the preset)"'+(a.custom_prompt?' style="display:block"':'')+'>'+esc(a.custom_prompt)+'</textarea>'
     +'<label class="cm-field-label">Agent Persona</label>'
     +'<select class="cm-select qLevel" data-i="'+i+'" style="width:100%">'+lOpts+'</select>';
    cards.appendChild(card);
  }
  cards.querySelectorAll('.qName').forEach(function(el){ el.oninput=function(){ qstate.agents[+this.getAttribute('data-i')].name=this.value; }; });
  cards.querySelectorAll('.qPersona').forEach(function(el){ el.onchange=function(){ qstate.agents[+this.getAttribute('data-i')].persona=this.value; }; });
  cards.querySelectorAll('.qLevel').forEach(function(el){ el.onchange=function(){ qstate.agents[+this.getAttribute('data-i')].persona_id=this.value; }; });
  cards.querySelectorAll('.qCustom').forEach(function(el){ el.oninput=function(){ qstate.agents[+this.getAttribute('data-i')].custom_prompt=this.value; }; });
  cards.querySelectorAll('.qCustomToggle').forEach(function(el){ el.onclick=function(){
    var i=+this.getAttribute('data-i'); var ta=cards.querySelector('.qCustom[data-i="'+i+'"]');
    var show=(ta.style.display!=='block'); ta.style.display=show?'block':'none'; this.classList.toggle('on',show); }; });
}
function qSetRounds(r){ qstate.rounds=Math.max(1,Math.min(6,r)); $('qRoundsVal').textContent=qstate.rounds; $('qTotalTurns').textContent=qstate.rounds*4; }

// ---- quad live-stage helpers ----
function qLog(type,text){
  var row=document.createElement('div');
  row.style.cssText='display:flex;gap:16px;font-size:11px;letter-spacing:0.04em;color:#6d6d6d;animation:fadeUp .4s ease both;align-items:baseline';
  row.innerHTML='<span style="color:#4a4a4a;text-transform:uppercase;letter-spacing:0.14em;flex:0 0 96px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+esc(type)+'</span>'
    +'<span style="flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#9a9a9a">'+esc(text)+'</span>';
  var log=$('qLog'); log.appendChild(row); while(log.children.length>60){ log.removeChild(log.firstChild); } log.scrollTop=log.scrollHeight;
}
function qSetTag(t){ $('qCanvasTag').textContent=t; }
function qSetComp(on,name){ $('qComp').style.display=on?'flex':'none'; if(on&&name){ $('qCompText').textContent=name+' painting'; } }
function qShowImage(src){ $('qCanvasBlobs').style.display='none'; $('qCanvasEmpty').style.display='none'; var im=$('qCanvasImg'); im.src=src; im.style.display='block'; }
function qAddBlob(b){ $('qCanvasEmpty').style.display='none'; $('qCanvasImg').style.display='none'; $('qCanvasBlobs').style.display='block';
  var d=document.createElement('div'); d.setAttribute('data-blob','1');
  d.style.cssText='position:absolute;left:'+b.x+';top:'+b.y+';width:'+b.size+';height:'+b.size+';transform:translate(-50%,-50%);border-radius:50%;background:radial-gradient(circle,'+b.c0+' 0%,'+b.c1+' 52%,transparent 72%);mix-blend-mode:screen;filter:blur(10px);opacity:0;transition:opacity 1.6s ease';
  $('qCanvasBlobs').appendChild(d); requestAnimationFrame(function(){ d.style.opacity='0.9'; }); }
function qSyncBlobs(){ $('qCanvasBlobs').querySelectorAll('[data-blob]').forEach(function(b,i){ b.style.opacity=((qstate.viewIndex==null)||(i<qstate.viewIndex))?'0.9':'0'; }); }
function qActivatePanel(idx){ for(var i=0;i<4;i++){ var p=$('qPanel'+i); if(p){ p.classList.toggle('active', i===idx); } } }
function qAddCard(d){
  var m=d.message||{}; var feed=$('qFeed'+d.agent_idx); if(!feed) return;
  var pal=Array.isArray(m.palette)?m.palette.join(' · '):(m.palette||'');
  var conf=(m.confidence_score!=null)?Math.round(Number(m.confidence_score)*100)+'%':'';
  var details=''
    +(m.sees_on_canvas?'<p class="qk">Sees on canvas</p><p class="qv">'+esc(m.sees_on_canvas)+'</p>':'')
    +(m.where?'<p class="qk">Placed</p><p class="qv">'+esc(m.where)+'</p>':'')
    +(pal?'<p class="qk">Palette</p><p class="qv">'+esc(pal)+'</p>':'')
    +(m.reasoning?'<p class="qk">Why</p><p class="qv">'+esc(m.reasoning)+'</p>':'')
    +(conf?'<p class="qk">Confidence</p><p class="qv">'+conf+'</p>':'');
  var div=document.createElement('div'); div.className='qcardturn';
  div.innerHTML='<button class="qturnhead" type="button"><span class="qturnlabel">Turn '+esc(d.turn)+' · adds</span><span class="qchev">▾</span></button>'
    +'<p class="qobj">'+esc(d.object||m.new_object||'')+'</p>'
    +'<div class="qdetails" style="display:none">'+(details||'<p class="qv">No further detail.</p>')+'</div>';
  div.querySelector('.qturnhead').onclick=function(){
    var dt=div.querySelector('.qdetails'); var open=(dt.style.display==='none');
    dt.style.display=open?'block':'none'; div.querySelector('.qchev').textContent=open?'▴':'▾';
  };
  feed.appendChild(div); feed.scrollTop=feed.scrollHeight;
}
function qBuildPanels(meta){
  var wrap=$('qPanels'); if(!wrap) return; wrap.innerHTML='';
  for(var i=0;i<4;i++){
    var m = (meta&&meta[i]) ? meta[i] : { name:(qstate.agents[i].name||('Agent '+(i+1))),
      persona_name:(qstate.agents[i].custom_prompt?(qstate.agents[i].name||'Custom'):qPersonaName(qstate.agents[i].persona)),
      persona_person:personaName(qstate.agents[i].persona_id) };
    var p=document.createElement('div'); p.className='qpanel'; p.id='qPanel'+i;
    p.innerHTML='<div class="qhd"><span style="font-size:11px;font-weight:600;letter-spacing:0.14em;color:#fff">'+esc(m.name)+'</span>'
      +'<span style="font-size:10px;letter-spacing:0.08em;color:#9a9a9a">'+esc(m.persona_name)+'</span>'
      +'<span style="margin-left:auto;font-size:9px;color:#9a9a9a;border:1px solid rgba(255,255,255,0.28);border-radius:75px;padding:2px 8px">'+esc(m.persona_person||'')+'</span></div>'
      +'<div class="qfeed" id="qFeed'+i+'"></div>';
    wrap.appendChild(p);
  }
}
function qAddFrame(f){
  qstate.frames.push(f); $('qStepCount').textContent=qstate.frames.length;
  var inner = f.image ? '<img src="'+f.image+'" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover"/>'
    : '<div style="position:absolute;inset:0;background:'+(f.blob?('radial-gradient(circle at 50% 60%,'+f.blob.c0+','+f.blob.c1+' 70%)'):'#101010')+';opacity:0.95"></div>';
  var btn=document.createElement('button'); btn.title=f.label||('step '+f.n);
  btn.style.cssText='flex:0 0 auto;width:64px;height:64px;border:1px solid rgba(255,255,255,0.16);background:#050505;position:relative;cursor:pointer;padding:0;overflow:hidden;animation:fadeUp .5s ease both';
  btn.innerHTML=inner+'<span style="position:absolute;bottom:3px;left:5px;font-size:9px;color:#fff;mix-blend-mode:difference">'+esc(f.n)+'</span>';
  btn.onclick=function(){ qScrub(f.n); };
  $('qFilmstrip').appendChild(btn);
}
function qScrub(n){ qstate.viewIndex=n; $('qViewLatest').style.display='inline-block';
  var f=qstate.frames.filter(function(x){return x.n===n;})[0];
  if(f&&f.image){ qShowImage(f.image); } else { qSyncBlobs(); }
  qSetTag('Step '+n+' / '+qstate.turns.length); }
function qViewLatest(){ qstate.viewIndex=null; $('qViewLatest').style.display='none';
  var last=qstate.frames[qstate.frames.length-1];
  if(last&&last.image){ qShowImage(last.image); } else { qSyncBlobs(); }
  qSetTag('Shared canvas'); }
function qDownloadAll(){
  var imgs=qstate.frames.filter(function(f){ return typeof f.image==='string' && f.image.indexOf('data:')===0; });
  if(!imgs.length){ qLog('warning','demo mode · connect Live to export real PNGs'); return; }
  var delay=0; imgs.forEach(function(f,i){ setTimeout(function(){ var a=document.createElement('a'); a.href=f.image;
    a.download='canvasmind_quad_step'+String(i+1).padStart(2,'0')+'_'+String(f.object||'').replace(/[^a-z0-9]+/gi,'_').slice(0,24)+'.png';
    document.body.appendChild(a); a.click(); a.remove(); }, delay); delay+=350; });
  qLog('download','saving '+imgs.length+' step image(s)');
}
function qResetStage(){
  qstate.turns=[]; qstate.frames=[]; qstate.viewIndex=null; qstate.error=null;
  $('qFilmstrip').innerHTML=''; $('qLog').innerHTML=''; $('qCanvasBlobs').innerHTML='';
  $('qCanvasImg').style.display='none'; $('qCanvasImg').removeAttribute('src'); $('qCanvasBlobs').style.display='block';
  $('qCanvasEmpty').style.display='flex'; $('qStepCount').textContent='0'; $('qViewLatest').style.display='none';
  $('qDownloadBtn').disabled=true; $('qDownloadBtn').style.opacity='0.5'; qSetComp(false);
  $('qJudge').style.display='none'; $('qScores').innerHTML=''; $('qComposite').textContent='—';
  $('qCriticReasoning').textContent=''; $('qHighlights').innerHTML=''; $('qFinalSummary').style.display='none';
  $('qJudgeDownload').disabled=true; $('qJudgeDownload').style.opacity='0.5';
}

var QSCORE_KEYS=['compositional_coherence','style_fidelity','emotional_resonance','originality','collaboration_quality'];
var QSCORE_LABELS={compositional_coherence:'Compositional coherence',style_fidelity:'Style fidelity',emotional_resonance:'Emotional resonance',originality:'Originality',collaboration_quality:'Collaboration quality'};
var QMOCK_CRITIC={scores:{compositional_coherence:8.4,style_fidelity:8.8,emotional_resonance:8.1,originality:9.0,collaboration_quality:8.6,composite:8.58},
  reasoning:'Four distinct voices resolved into one canvas: the minimalist scaffolding gave the cyberpunk and surrealist room to escalate, and the baroque agent unified the palette without overwhelming the restraint set on the first turn.',
  highlights:['The mirrored obelisk (Agent 3) tied the neon and the negative space together','The closing gilded arch reframed the whole sequence as intentional'],
  final_summary:'A relay of four sensibilities that reads as one deliberate painting — sequential, not scattered.'};
function qRenderCritic(ev){
  var s=ev.scores||{}; var html='';
  QSCORE_KEYS.forEach(function(k){
    var v=Math.max(0,Math.min(10,parseFloat(s[k])||0)); var val100=Math.round(v*10);
    html+='<div><div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:10px"><span style="font-size:13px;color:#fff">'+QSCORE_LABELS[k]+'</span><span style="font-size:13px;color:#9a9a9a">'+val100+'</span></div><div style="height:1px;background:rgba(255,255,255,0.12);position:relative"><div style="position:absolute;left:0;top:0;height:1px;background:#fff;width:'+(v*10)+'%;transition:width 1.3s cubic-bezier(0.16,1,0.3,1)"></div></div></div>';
  });
  $('qScores').innerHTML=html;
  var comp=parseFloat(s.composite);
  if(isNaN(comp)){ var vals=QSCORE_KEYS.map(function(k){return parseFloat(s[k])||0;}); comp=vals.reduce(function(a,b){return a+b;},0)/(vals.length||1); }
  $('qComposite').textContent=(Math.max(0,Math.min(10,comp))*10).toFixed(1);
  $('qCriticReasoning').textContent=ev.reasoning||'';
  var hl=ev.highlights||[];
  $('qHighlights').innerHTML=hl.length?hl.map(function(h){return '<p style="font-size:12px;line-height:1.5;color:#6d6d6d;margin-bottom:6px;padding-left:14px;position:relative"><span style="position:absolute;left:0">·</span>'+esc(h)+'</p>';}).join(''):'';
  if(ev.final_summary){ $('qFinalSummary').style.display='block'; $('qFinalSummary').textContent='“'+ev.final_summary+'”'; }
  if(qstate.frames.some(function(f){return f.image;})){ $('qJudgeDownload').disabled=false; $('qJudgeDownload').style.opacity='1'; }
  $('qJudge').style.display='block';
}
function qHandle(type,d){
  d=d||{};
  switch(type){
    case 'session':
      qstate.meta=d.agents||[]; qstate.imagesEnabled=!!d.images; qstate.totalTurns=d.total_turns||(qstate.rounds*4);
      if(d.session_number!=null){ qstate.sessionNumber=d.session_number; postParticipant(d.session_number); }
      $('qBrief').textContent=d.prompt||qstate.prompt||''; $('qStyle2').textContent=d.style||qstate.style||'';
      $('qModalBrief').textContent=d.prompt||qstate.prompt||''; $('qModalStyle').textContent=(d.style||qstate.style)?('Style — '+(d.style||qstate.style)):'';
      $('qTurnCounter').textContent='00 / '+qstate.totalTurns;
      qBuildPanels(qstate.meta.length?qstate.meta:null);
      qLog('session','brief · '+(d.prompt||qstate.prompt||'')); break;
    case 'turn':
      if(d.agent_idx==null || d.name==='JUDGE'){ qActivatePanel(-1); qSetComp(false); qSetTag('Composing critique'); qLog('turn','JUDGE scoring the sequence'); break; }
      qActivatePanel(d.agent_idx);
      $('qTurnCounter').textContent=String(d.turn).padStart(2,'0')+' / '+(d.total||qstate.totalTurns);
      qSetTag((d.name||('Agent '+((d.agent_idx||0)+1)))+' · adding'); qSetComp(false);
      qLog('turn','R'+d.round+' · '+(d.name||'')+' ('+(d.persona_name||'')+')'); break;
    case 'agent':
      qstate.turns.push({n:d.turn,idx:d.agent_idx,name:d.name,object:d.object});
      qAddCard(d); qLog('agent',(d.name||'')+': + '+(d.object||'')); break;
    case 'image_pending': qSetComp(true,d.name); qLog('image_pending','compositing object '+d.turn); break;
    case 'image':
      qSetComp(false);
      if(d.image){ if(qstate.viewIndex==null){ qShowImage(d.image); } qAddFrame({n:d.turn,idx:d.agent_idx,label:d.label,object:d.object,image:d.image}); }
      else if(d.blob){ if(qstate.viewIndex==null){ qAddBlob(d.blob); } qAddFrame({n:d.turn,idx:d.agent_idx,label:d.label,object:d.object,blob:d.blob}); }
      if(qstate.viewIndex==null){ qSetTag('Latest · turn '+d.turn); }
      qLog('image','image '+d.turn+' · '+(d.label||'')); break;
    case 'critic': qRenderCritic(d.evaluation||d); qLog('critic','JUDGE scored the collaboration'); break;
    case 'final': qSetComp(false); if(d.image&&qstate.viewIndex==null){ qShowImage(d.image); } qSetTag('Final · 4-agent chain'); qLog('final','final canvas presented'); break;
    case 'warning': qLog('warning',d.message||'warning'); break;
    case 'summary': qLog('summary','complete · '+(d.turns!=null?d.turns:qstate.turns.length)+' turns · '+(d.elapsed!=null?d.elapsed+'s':'')); break;
    case 'error': qstate.error=d.message||'error'; qLog('error',qstate.error); break;
    case 'done':
      $('qTurnCounter').textContent=qstate.turns.length+' / '+qstate.totalTurns;
      qActivatePanel(-1);
      if(qstate.frames.some(function(f){return f.image;})){ $('qDownloadBtn').disabled=false; $('qDownloadBtn').style.opacity='1'; }
      $('qStopBtn').style.display='none'; revealSurvey('qSurveyHost'); qLog('done','session complete'); break;
  }
}

function qConnectLive(){
  qClearTimers(); qstate.error=null;
  $('qStopBtn').style.display='inline-block'; $('qStopBtn').disabled=false; $('qStopBtn').textContent='Stop ↦';
  qLog('session','connecting to backend…');
  fetch('api/quad/start',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ prompt:qstate.prompt, style:qstate.style, rounds:qstate.rounds, images:true,
      agents:qstate.agents.map(function(a){ return { name:a.name, persona:a.persona, custom_prompt:a.custom_prompt||'', persona_id:a.persona_id }; }) })})
    .then(function(r){ return r.json(); }).then(function(j){
      if(j.error){ throw new Error(j.error); }
      qstate.sessionId=j.session_id; qLog('session','session '+j.session_id);
      qes=new EventSource('api/stream/'+j.session_id);
      qes.onmessage=function(e){ try{ var ev=JSON.parse(e.data); if(ev&&ev.type){ qHandle(ev.type,ev); if(ev.type==='done'){ qes.close(); } } }catch(_){} };
      qes.onerror=function(){ qLog('error','stream interrupted'); };
    }).catch(function(err){ qLog('error','backend error — '+err.message+' · falling back to demo'); qAt(400,qRunDemo); });
}

var QMOCK_OBJ=['a lone geometric monolith','a neon rain of glyphs','a melting coral spire','a gilded baroque arch',
  'a fractured comet trail','a shimmer of dappled mist','a mirrored obelisk','a holographic koi'];
var QMOCK_BLOB=[{x:'30%',y:'55%',size:'60%',c0:'#e8e8ee',c1:'#8a8a99'},{x:'70%',y:'34%',size:'46%',c0:'#ff4d8f',c1:'#3a2f6a'},
  {x:'48%',y:'70%',size:'54%',c0:'#5fe3b0',c1:'#1f4f4a'},{x:'52%',y:'26%',size:'42%',c0:'#e6c067',c1:'#7a5320'},
  {x:'24%',y:'40%',size:'40%',c0:'#8ab4ff',c1:'#26306a'},{x:'80%',y:'64%',size:'44%',c0:'#ffd1e8',c1:'#6a3a5a'},
  {x:'40%',y:'22%',size:'38%',c0:'#cfc9bd',c1:'#5a564d'},{x:'62%',y:'56%',size:'40%',c0:'#a0e0ab',c1:'#1f4f4a'}];
function qRunDemo(){
  qClearTimers(); qstate.error=null; qstate.imagesEnabled=false;
  var meta=qstate.agents.map(function(a,i){ return { name:(a.name||('Agent '+(i+1))),
    persona_name:(a.custom_prompt?(a.name||'Custom'):qPersonaName(a.persona)), persona_person:personaName(a.persona_id) }; });
  var total=qstate.rounds*4;
  qHandle('session',{ mode:'quad', prompt:qstate.prompt, style:qstate.style, rounds:qstate.rounds, total_turns:total, images:false,
    agents:meta.map(function(m,i){ return { index:i, name:m.name, persona_name:m.persona_name, persona_person:m.persona_person }; }) });
  var t=350, beat=560, turn=0;
  for(var r=1;r<=qstate.rounds;r++){
    for(var i=0;i<4;i++){
      (function(rr,ii){
        turn++; var n=turn, obj=QMOCK_OBJ[(n-1)%QMOCK_OBJ.length], blob=QMOCK_BLOB[(n-1)%QMOCK_BLOB.length], pm=meta[ii];
        qAt(t,function(){ qHandle('turn',{turn:n,total:total,round:rr,agent_idx:ii,name:pm.name,persona_name:pm.persona_name,persona_person:pm.persona_person}); });
        qAt(t+220,function(){ qHandle('agent',{agent_idx:ii,name:pm.name,turn:n,round:rr,persona_name:pm.persona_name,object:obj,
          message:{sender:pm.name,sees_on_canvas:'the accumulating canvas',new_object:obj,where:'the composition',palette:['#cbb2d9','#33406a'],reasoning:'a move in the voice of '+pm.persona_name,confidence_score:0.8}}); });
        qAt(t+400,function(){ qHandle('image_pending',{turn:n,agent_idx:ii,name:pm.name}); });
        qAt(t+760,function(){ qHandle('image',{turn:n,total:total,round:rr,agent_idx:ii,name:pm.name,object:obj,label:'R'+rr+' - Agent '+(ii+1)+' ('+pm.persona_name+'): '+obj,blob:blob}); });
        t+=beat;
      })(r,i);
    }
  }
  qAt(t,function(){ qHandle('turn',{turn:'JUDGE',total:total,agent_idx:null,name:'JUDGE',persona_name:'Critic',persona_person:'-'}); });
  qAt(t+240,function(){ qHandle('critic',{evaluation:QMOCK_CRITIC}); });
  qAt(t+1600,function(){ qHandle('summary',{turns:total,objects:[],rounds:qstate.rounds,composite:QMOCK_CRITIC.scores.composite,elapsed:(t/1000).toFixed(1)}); });
  qAt(t+1800,function(){ qHandle('done',{}); });
}

function qLaunch(){
  qstate.prompt=($('qPrompt').value||'').trim(); qstate.style=($('qStyle').value||'').trim();
  if(!qstate.prompt){ qstate.prompt='A lighthouse at the edge of the world'; $('qPrompt').value=qstate.prompt; }
  qResetStage(); qBuildPanels(null);
  $('quadConfig').style.display='none'; $('quadHeroLayer').style.display='none'; $('quadStage').style.display='block';
  if(state.live){ qConnectLive(); } else { qRunDemo(); }
}
function qStop(){
  $('qStopBtn').disabled=true; $('qStopBtn').textContent='Stopping…';
  if(state.live && qstate.sessionId){ fetch('api/stop/'+qstate.sessionId,{method:'POST'}).catch(function(){}); qLog('control','stop requested — presenting work so far'); }
  else { qClearTimers(); qLog('control','stopped — presenting work so far'); qHandle('summary',{turns:qstate.turns.length,elapsed:0}); qHandle('done',{}); }
}

$('toQuad').onclick=function(){ setAppMode('quad'); };
$('toDual').onclick=function(){ setAppMode('dual'); };
$('qBack').onclick=function(){ setAppMode('dual'); };
var QSURPRISE_FALLBACK=[
  {prompt:'A salt cathedral at the bottom of a dry sea',style:'deep-baroque · mineral light · oxidized gold'},
  {prompt:'A lighthouse keeper’s greenhouse on a drifting iceberg',style:'glacial cyber-folk'},
  {prompt:'A night market suspended between two skyscrapers',style:'neon monsoon, wet reflections'},
  {prompt:'The last orchard on a terraformed moon',style:'sunlit botanical, thin atmosphere'}
];
$('qSurprise').onclick=function(){
  var b=this; b.disabled=true; var old=b.textContent; b.textContent='Inventing…';
  fetch('api/inspire').then(function(r){ return r.json(); }).then(function(j){
    if(j.error||!j.prompt){ throw new Error(j.error||'no brief'); }
    $('qPrompt').value=j.prompt; $('qStyle').value=j.style||'';
  }).catch(function(){
    var f=QSURPRISE_FALLBACK[Math.floor(Math.random()*QSURPRISE_FALLBACK.length)];
    $('qPrompt').value=f.prompt; $('qStyle').value=f.style;
  }).then(function(){ b.disabled=false; b.textContent=old; });
};
$('qRoundsUp').onclick=function(){ qSetRounds(qstate.rounds+1); };
$('qRoundsDown').onclick=function(){ qSetRounds(qstate.rounds-1); };
$('qLaunch').onclick=qLaunch;
$('qStopBtn').onclick=qStop;
$('qNewBtn').onclick=function(){ qClearTimers(); if(qes){ qes.close(); qes=null; } $('quadStage').style.display='none'; $('quadConfig').style.display='block'; $('quadHeroLayer').style.display='block'; };
$('qDownloadBtn').onclick=qDownloadAll;
$('qViewLatest').onclick=qViewLatest;
$('qBriefWrap').onclick=function(){ $('qBriefModal').style.display='flex'; };
$('qModalClose').onclick=function(){ $('qBriefModal').style.display='none'; };
$('qBriefModal').onclick=function(e){ if(e.target===this){ this.style.display='none'; } };
$('qJudgeDownload').onclick=qDownloadAll;
$('qJudgeNew').onclick=function(){ qClearTimers(); if(qes){ qes.close(); qes=null; } $('quadStage').style.display='none'; $('quadConfig').style.display='block'; $('quadHeroLayer').style.display='block'; };
qSetRounds(1);

// ---------- init ----------
function initPersonaSelectors(){
  var a=$('ariaPersona'), n=$('nexusPersona');
  if(a){ a.innerHTML=personaOptions(state.personas.ARIA); renderPersonaDesc($('ariaPersonaDesc'), state.personas.ARIA); }
  if(n){ n.innerHTML=personaOptions(state.personas.NEXUS); renderPersonaDesc($('nexusPersonaDesc'), state.personas.NEXUS); }
}

// ================= participant form + post-session survey =================
var PARTICIPANT = null;                 // {age, gender, art_expertise}
var POSTED_PARTICIPANT = {};            // session numbers already sent

function showParticipantForm(){
  try{ var saved = localStorage.getItem('cm_participant'); if(saved){ PARTICIPANT = JSON.parse(saved); return; } }catch(_){ }
  var ov = $('participantOverlay'); if(!ov) return;
  ov.style.display = 'flex';
}
function hideParticipantForm(){ var ov=$('participantOverlay'); if(ov){ ov.style.display='none'; } }
function submitParticipantForm(){
  var age = ($('pfAge').value||'').trim();
  var gender = $('pfGender').value||'';
  var exp = $('pfExpertise').value||'';
  if(!age || !gender || !exp){ $('pfError').textContent = 'Please fill in all three, or choose Skip.'; return; }
  PARTICIPANT = { age: Number(age)||age, gender: gender, art_expertise: exp };
  try{ localStorage.setItem('cm_participant', JSON.stringify(PARTICIPANT)); }catch(_){ }
  hideParticipantForm();
}
// Called when a session's number becomes known, from the `session` event.
function postParticipant(sessionNumber){
  if(sessionNumber==null || !PARTICIPANT || POSTED_PARTICIPANT[sessionNumber]) return;
  POSTED_PARTICIPANT[sessionNumber] = true;
  fetch('api/sessions/'+sessionNumber+'/participant', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(PARTICIPANT) }).catch(function(){});
}

// The survey: 6 numeric 1-10 items + 6 five-point Likert items + a free-text note.
var SURVEY_SCALE = [
  'How close was the final image to the version you imagined?',
  'How satisfied are you with the final artwork overall?',
  'How surprising were the agents’ contributions?',
  'How coherent did the two (or four) agents’ additions feel together?',
  'How much did you feel in control of the outcome?',
  'How likely are you to use this again?'
];
var SURVEY_LIKERT = [
  'The agents genuinely collaborated rather than working independently.',
  'I could understand why each agent added what it did.',
  'The final artwork feels original.',
  'This was more engaging than a single prompt-to-image tool.',
  'I trusted the JUDGE’s evaluation of the collaboration.',
  'I would describe the result as creative.'
];
var LIKERT_OPTS = ['Strongly disagree','Disagree','Neutral','Agree','Strongly agree'];
var surveyState = {};   // hostId -> { answers:{}, total, submitted }

function buildSurvey(hostId){
  var host = $(hostId); if(!host || host.getAttribute('data-built')==='1') return;
  host.setAttribute('data-built','1');
  var st = surveyState[hostId] = { answers:{}, total: SURVEY_SCALE.length + SURVEY_LIKERT.length, submitted:false };
  var h = '';
  h += '<div class="cm-survey">';
  h += '<h3>One last thing</h3>';
  h += '<p class="cm-survey-lead">How was co-creating?</p>';
  h += '<p class="cm-survey-note">'+st.total+' quick questions. Your answers are saved with this session for research — there are no right answers.</p>';
  var n = 0;
  SURVEY_SCALE.forEach(function(q, i){
    n++; var key='scale_'+(i+1);
    h += '<div class="cm-q"><div class="cm-q-text"><span class="cm-q-num">'+String(n).padStart(2,'0')+'</span>'+esc(q)+'</div>';
    h += '<div class="cm-scale" data-key="'+key+'">';
    for(var v=1; v<=10; v++){ h += '<button type="button" data-val="'+v+'">'+v+'</button>'; }
    h += '</div><div class="cm-scale-ends"><span>Not at all</span><span>Completely</span></div></div>';
  });
  SURVEY_LIKERT.forEach(function(q, i){
    n++; var key='likert_'+(i+1);
    h += '<div class="cm-q"><div class="cm-q-text"><span class="cm-q-num">'+String(n).padStart(2,'0')+'</span>'+esc(q)+'</div>';
    h += '<div class="cm-likert" data-key="'+key+'">';
    LIKERT_OPTS.forEach(function(o, oi){ h += '<button type="button" data-val="'+(oi+1)+'" data-label="'+esc(o)+'">'+esc(o)+'</button>'; });
    h += '</div></div>';
  });
  h += '<div class="cm-q"><div class="cm-q-text"><span class="cm-q-num">'+String(n+1).padStart(2,'0')+'</span>Anything else about the experience? (optional)</div>';
  h += '<textarea id="'+hostId+'_note" placeholder="Your thoughts…"></textarea></div>';
  h += '<div class="cm-survey-foot"><button class="cm-survey-submit" id="'+hostId+'_submit" disabled>Submit survey</button>';
  h += '<span class="cm-survey-progress" id="'+hostId+'_prog">0 / '+st.total+' answered</span></div>';
  h += '</div>';
  host.innerHTML = h;

  host.querySelectorAll('.cm-scale, .cm-likert').forEach(function(group){
    group.addEventListener('click', function(e){
      var btn = e.target.closest('button'); if(!btn) return;
      group.querySelectorAll('button').forEach(function(b){ b.classList.remove('sel'); });
      btn.classList.add('sel');
      var key = group.getAttribute('data-key');
      st.answers[key] = { value: Number(btn.getAttribute('data-val')), label: btn.getAttribute('data-label')||undefined };
      var answered = Object.keys(st.answers).length;
      $(hostId+'_prog').textContent = answered + ' / ' + st.total + ' answered';
      $(hostId+'_submit').disabled = (answered < st.total);
    });
  });
  $(hostId+'_submit').onclick = function(){ submitSurvey(hostId); };
}

function submitSurvey(hostId){
  var st = surveyState[hostId]; if(!st || st.submitted) return;
  var num = (hostId==='qSurveyHost') ? qstate.sessionNumber : state.sessionNumber;
  var payload = { scale:{}, likert:{}, note: ($(hostId+'_note') ? $(hostId+'_note').value : '') , client_ts: new Date().toISOString() };
  Object.keys(st.answers).forEach(function(k){
    if(k.indexOf('scale_')===0){ payload.scale[k] = st.answers[k].value; }
    else { payload.likert[k] = { value: st.answers[k].value, label: st.answers[k].label }; }
  });
  st.submitted = true;
  var finish = function(){ $(hostId).innerHTML = '<div class="cm-survey"><div class="cm-survey-done">✓ Thank you — your responses are saved with this session.</div></div>'; };
  if(num==null){ finish(); return; }   // demo mode: nothing to persist to
  fetch('api/sessions/'+num+'/survey', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload) }).then(finish).catch(finish);
}
function revealSurvey(hostId){ buildSurvey(hostId); }

function init(){
  spawnBubbles();
  showParticipantForm();
  var _pfS=$('pfSubmit'); if(_pfS){ _pfS.onclick=submitParticipantForm; }
  var _pfK=$('pfSkip'); if(_pfK){ _pfK.onclick=function(){ PARTICIPANT=null; hideParticipantForm(); }; }
  initPersonaSelectors();
  fetchPersonaCatalog(function(){ initPersonaSelectors(); if(typeof qBuildCards==='function' && qstate.loaded){ qBuildCards(); } });
  setMode('surprise'); setRounds(5);
  fetch('api/health').then(function(r){ return r.json(); }).then(function(h){
    state.live = true;
    var info = 'model · '+(h.model||'?');
    if(h.images_enabled){ info += ' · images'; }
    if(h.embeddings_enabled){ info += ' · embeddings'; }
    $('modelInfo').textContent = info;
    setStatus();
  }).catch(function(){
    state.live = false; $('modelInfo').textContent = 'backend offline'; setStatus();
  });
  showPhase();
}
init();
})();
</script>
</body>
</html>
"""
