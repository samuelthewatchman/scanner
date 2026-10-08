/* RÜVA shared helpers, inlined into scanner.html and sell.html by ruva_tickets.py
   - UI      : popups (modals) instead of browser alerts
   - QRCam   : camera QR reader
   - Sales   : "sales code" encode / decode / merge (how sold tickets travel to the gate)
   - sha256, parseQR, normSerial, copyText, downloadText, fmtMin                                  */

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ---------- SHA-256 (works on plain http / file:// too) ---------- */
function sha256(str) {
  const K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const bytes = Array.from(new TextEncoder().encode(str));
  const l = bytes.length * 8;
  bytes.push(0x80);
  while (bytes.length % 64 !== 56) bytes.push(0);
  const hi = Math.floor(l / 4294967296), lo = l >>> 0;
  for (const v of [hi, lo]) bytes.push((v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255);
  let h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const rotr = (x, n) => (x >>> n) | (x << (32 - n));
  for (let i = 0; i < bytes.length; i += 64) {
    const w = new Array(64);
    for (let t = 0; t < 16; t++) w[t] = (bytes[i+4*t] << 24) | (bytes[i+4*t+1] << 16) | (bytes[i+4*t+2] << 8) | bytes[i+4*t+3];
    for (let t = 16; t < 64; t++) {
      const s0 = rotr(w[t-15],7) ^ rotr(w[t-15],18) ^ (w[t-15] >>> 3);
      const s1 = rotr(w[t-2],17) ^ rotr(w[t-2],19) ^ (w[t-2] >>> 10);
      w[t] = (w[t-16] + s0 + w[t-7] + s1) | 0;
    }
    let [a,b,c,d,e,f,g,hh] = h;
    for (let t = 0; t < 64; t++) {
      const S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (hh + S1 + ch + K[t] + w[t]) | 0;
      const S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) | 0;
      hh = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    h = [(h[0]+a)|0,(h[1]+b)|0,(h[2]+c)|0,(h[3]+d)|0,(h[4]+e)|0,(h[5]+f)|0,(h[6]+g)|0,(h[7]+hh)|0];
  }
  return h.map(x => (x >>> 0).toString(16).padStart(8, '0')).join('');
}

/* ---------- ticket text helpers ---------- */
// ticket QR looks like  S-001.BB891F01B2207BCD  (serial, dot, 16-character signature)
function parseQR(text) {
  const m = String(text).trim().toUpperCase().match(/^([SD]-\d{3,5})\.([0-9A-F]{16})$/);
  return m ? { serial: m[1], sig: m[2].toLowerCase() } : null;
}
// "s14", "S-14", "d 7" -> "S-014", "D-007"; anything else -> ""
function normSerial(s) {
  const m = String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '').match(/^([SD])(\d{1,5})$/);
  return m ? m[1] + '-' + m[2].padStart(3, '0') : '';
}
const typeName = t => (t === 'S' ? 'Single' : 'Double');
const fmtMin = m => new Date(m * 60000).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
const fmtTime = iso => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/* ---------- popups (modals) ---------- */
const UI = (() => {
  const CSS = `
  .mdl-ov{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;padding:18px;background:rgba(0,0,0,.74);backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);opacity:0;transition:opacity .15s}
  .mdl-ov.show{opacity:1}
  .mdl-card{width:100%;max-width:400px;max-height:92vh;overflow:auto;background:#161616;border:1px solid #2a2a2a;border-radius:20px;padding:22px 20px 18px;text-align:center;color:#f2f2f2;transform:translateY(10px) scale(.97);transition:transform .15s;box-shadow:0 20px 60px rgba(0,0,0,.6);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
  .mdl-ov.show .mdl-card{transform:none}
  .mdl-icon{width:54px;height:54px;border-radius:50%;margin:0 auto 12px;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:800;background:#2a2a2a}
  .tone-ok .mdl-icon{background:#1fa75a;color:#fff}.tone-bad .mdl-icon{background:#d23b3b;color:#fff}
  .tone-warn .mdl-icon{background:#d99a1d;color:#1a1200}.tone-info .mdl-icon{background:#c8a04a;color:#111}
  .mdl-title{font-size:21px;font-weight:800;letter-spacing:.02em;margin-bottom:6px}
  .mdl-body{font-size:15px;line-height:1.55;color:#d6d6d6;word-break:break-word}
  .mdl-body b{color:#fff}
  .mdl-extra{margin-top:12px}
  .mdl-extra video{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:14px;background:#000;display:block}
  .mdl-in{width:100%;margin-top:14px;padding:12px;border-radius:12px;border:1px solid #333;background:#0f0f0f;color:#fff;font:inherit;font-size:16px}
  textarea.mdl-in{min-height:110px;resize:vertical;font-family:ui-monospace,Menlo,monospace;font-size:13px;text-align:left}
  .mdl-btns{display:flex;gap:10px;margin-top:18px}
  .mdl-btns button{flex:1;font:inherit;font-weight:700;font-size:15px;border:0;border-radius:12px;padding:13px 10px;cursor:pointer;background:#c8a04a;color:#111}
  .mdl-btns button.ghost{background:transparent;color:#f2f2f2;border:1px solid #3a3a3a}
  .mdl-btns button.danger{background:#d23b3b;color:#fff}
  .mdl-card.solid{border:0;padding:30px 20px 22px}
  .mdl-card.solid.tone-ok{background:#1fa75a;color:#fff}.mdl-card.solid.tone-bad{background:#d23b3b;color:#fff}
  .mdl-card.solid.tone-warn{background:#d99a1d;color:#1a1200}.mdl-card.solid.tone-info{background:#c8a04a;color:#111}
  .solid .mdl-icon{background:rgba(255,255,255,.24);color:inherit;width:68px;height:68px;font-size:38px}
  .solid .mdl-title{font-size:32px}
  .solid .mdl-body{color:inherit;font-size:17px}.solid .mdl-body b{color:inherit}
  .solid .mdl-btns button{background:rgba(0,0,0,.28);color:inherit}
  .mdl-bar{height:4px;background:rgba(255,255,255,.3);border-radius:2px;margin-top:16px;overflow:hidden}
  .mdl-bar i{display:block;height:100%;background:rgba(255,255,255,.95);transform-origin:left;transform:scaleX(1)}
  @media (prefers-reduced-motion:reduce){.mdl-ov,.mdl-card{transition:none}}`;
  const st = document.createElement('style');
  st.textContent = CSS;
  document.head.appendChild(st);

  const DEFAULT_ICON = { ok: '✓', bad: '✕', warn: '!', info: 'i' };
  const stack = [];
  let z = 1000;

  /* modal({tone, solid, icon, title, body, node, input, buttons, autoClose, backdropClose, onOpen, onClose})
     -> Promise<{value, text}>  (value = clicked button's value, null if dismissed). The promise has .close(value). */
  function modal(o) {
    o = o || {};
    let closeFn = () => {};
    const p = new Promise(resolve => {
      const ov = document.createElement('div');
      ov.className = 'mdl-ov';
      ov.style.zIndex = ++z;
      const tone = o.tone || 'info';
      const card = document.createElement('div');
      card.className = 'mdl-card tone-' + tone + (o.solid ? ' solid' : '');
      card.setAttribute('role', 'dialog');
      card.setAttribute('aria-modal', 'true');
      const icon = o.icon === undefined ? DEFAULT_ICON[tone] : o.icon;
      let h = '';
      if (icon) h += '<div class="mdl-icon">' + icon + '</div>';
      if (o.title) h += '<div class="mdl-title">' + o.title + '</div>';
      if (o.body) h += '<div class="mdl-body">' + o.body + '</div>';
      card.innerHTML = h;
      if (o.node) {
        const w = document.createElement('div');
        w.className = 'mdl-extra';
        w.appendChild(o.node);
        card.appendChild(w);
      }
      let inp = null;
      if (o.input) {
        inp = document.createElement(o.input.rows ? 'textarea' : 'input');
        inp.className = 'mdl-in';
        if (o.input.rows) inp.rows = o.input.rows; else inp.type = o.input.type || 'text';
        if (o.input.placeholder) inp.placeholder = o.input.placeholder;
        if (o.input.value) inp.value = o.input.value;
        if (o.input.readonly) inp.readOnly = true;
        if (o.input.upper) inp.style.textTransform = 'uppercase';
        inp.setAttribute('autocomplete', 'off');
        inp.setAttribute('autocapitalize', o.input.upper ? 'characters' : 'off');
        inp.setAttribute('spellcheck', 'false');
        card.appendChild(inp);
      }
      const buttons = o.buttons || [{ label: 'OK', value: true }];
      let primary = null;
      if (buttons.length) {
        const row = document.createElement('div');
        row.className = 'mdl-btns';
        buttons.forEach(b => {
          const el = document.createElement('button');
          el.type = 'button';
          el.className = b.kind || '';
          el.textContent = b.label;
          el.addEventListener('click', () => closeFn(b.value));
          if (!primary && b.kind !== 'ghost') primary = { el, value: b.value };
          row.appendChild(el);
        });
        card.appendChild(row);
      }
      let timer = null, done = false;
      const bar = o.autoClose ? document.createElement('div') : null;
      if (bar) { bar.className = 'mdl-bar'; bar.innerHTML = '<i></i>'; card.appendChild(bar); }
      const prevFocus = document.activeElement;
      const onKey = e => {
        if (stack[stack.length - 1] !== ov) return;
        if (e.key === 'Escape' && o.cancelable !== false) { e.stopPropagation(); closeFn(null); }
        else if (e.key === 'Enter' && inp && inp.tagName === 'INPUT' && primary) { e.preventDefault(); primary.el.click(); }
      };
      closeFn = value => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        document.removeEventListener('keydown', onKey, true);
        const i = stack.indexOf(ov); if (i >= 0) stack.splice(i, 1);
        ov.classList.remove('show');
        setTimeout(() => ov.remove(), 170);
        try { if (prevFocus && prevFocus.focus && document.contains(prevFocus)) prevFocus.focus(); } catch (e) {}
        if (o.onClose) { try { o.onClose(); } catch (e) {} }
        resolve({ value: value === undefined ? null : value, text: inp ? inp.value : '' });
      };
      ov.addEventListener('click', e => {
        if (o.backdropClose && (e.target === ov || o.solid)) closeFn(o.solid ? 'tap' : null);
      });
      ov.appendChild(card);
      document.body.appendChild(ov);
      stack.push(ov);
      document.addEventListener('keydown', onKey, true);
      requestAnimationFrame(() => ov.classList.add('show'));
      if (o.autoClose) {
        timer = setTimeout(() => closeFn('auto'), o.autoClose);
        const i = bar.firstChild;
        i.style.transition = 'transform ' + o.autoClose + 'ms linear';
        requestAnimationFrame(() => requestAnimationFrame(() => { i.style.transform = 'scaleX(0)'; }));
      }
      setTimeout(() => {
        try { (inp || (primary && primary.el) || card).focus({ preventScroll: true }); } catch (e) {}
        if (o.onOpen) { try { o.onOpen({ card, input: inp, close: closeFn }); } catch (e) {} }
      }, 30);
    });
    p.close = v => closeFn(v);
    return p;
  }

  async function confirm(o) {
    const r = await modal(Object.assign({
      icon: '?',
      buttons: [{ label: o.no || 'Cancel', value: false, kind: 'ghost' }, { label: o.yes || 'Yes', value: true, kind: o.danger ? 'danger' : '' }],
    }, o));
    return r.value === true;
  }
  return { modal, confirm, isOpen: () => stack.length > 0 };
})();

/* ---------- camera QR reader ---------- */
const QRCam = {
  // Resolves to {stop()}. Rejects with an Error whose .code is nohttps | nosupport | denied | other
  async start(video, onText) {
    const fail = code => Object.assign(new Error(code), { code });
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw fail('nohttps');
    const hasNative = 'BarcodeDetector' in window;
    const hasJs = typeof jsQR === 'function';
    if (!hasNative && !hasJs) throw fail('nosupport');
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } }, audio: false });
    } catch (e) {
      throw fail(e && (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? 'denied' : 'other');
    }
    video.srcObject = stream;
    video.setAttribute('playsinline', '');
    video.muted = true;
    try { await video.play(); } catch (e) {}
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const det = hasNative ? new BarcodeDetector({ formats: ['qr_code'] }) : null;
    let busy = false;
    const id = setInterval(async () => {
      if (busy || video.readyState < 2) return;
      busy = true;
      try {
        if (det) {
          const codes = await det.detect(video);
          if (codes.length) onText(codes[0].rawValue);
        } else {
          canvas.width = video.videoWidth; canvas.height = video.videoHeight;
          ctx.drawImage(video, 0, 0);
          const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const r = jsQR(img.data, img.width, img.height);
          if (r) onText(r.data);
        }
      } catch (e) {}
      busy = false;
    }, 160);
    return { stop() { clearInterval(id); stream.getTracks().forEach(t => t.stop()); video.srcObject = null; } };
  },
  // friendly popup text for a failed start()
  errorPopup(code) {
    const m = {
      nohttps: ['Camera needs the secure link', 'Open this page from the hosted <b>https</b> link, not from a file or an http link. Until then, type the ticket serial instead.'],
      nosupport: ['This browser cannot scan', 'Use <b>Chrome on Android</b> for camera scanning. Meanwhile you can type the ticket serial instead.'],
      denied: ['Camera is blocked', 'Allow camera access for this site in the browser settings, then try again.'],
      other: ['Could not open the camera', 'Close other apps that use the camera, then try again.'],
    }[code] || ['Could not open the camera', 'Try again.'];
    return { tone: 'warn', title: m[0], body: m[1] };
  },
};

/* ---------- sales codes ----------
   A sales record is  sales[serial] = { st: 1 (sold) | 0 (cancelled), t: minutes-since-1970, ...details }
   A "sales code" is plain text, e.g.  RUVA1|S-001:1:s8x2k;D-004:1:s8x3q|a1b2c3   (safe to send on WhatsApp)
   When two records disagree, the newer one (bigger t) wins.                                                   */
const Sales = {
  nowMin: () => Math.floor(Date.now() / 60000),
  encode(sales) {
    const body = Object.keys(sales).sort().map(k => k + ':' + sales[k].st + ':' + sales[k].t.toString(36)).join(';');
    return 'RUVA1|' + body + '|' + sha256(body).slice(0, 6);
  },
  decode(text) {
    const m = String(text).replace(/\s+/g, '').match(/RUVA1\|([A-Za-z0-9:;-]*)\|([0-9a-f]{6})/);
    if (!m) return { ok: false, why: 'format' };
    if (sha256(m[1]).slice(0, 6) !== m[2]) return { ok: false, why: 'damaged' };
    const recs = []; let bad = 0;
    for (const part of m[1].split(';')) {
      if (!part) continue;
      const r = part.match(/^([SD]-\d{3,5}):([01]):([0-9a-z]{1,8})$/);
      if (!r) { bad++; continue; }
      recs.push({ s: r[1], st: +r[2], t: parseInt(r[3], 36) });
    }
    return { ok: true, recs, bad };
  },
  // known = TICKETS (each may carry baseline sold flag .s). Returns counts of what changed.
  merge(sales, recs, known) {
    const out = { added: 0, voided: 0, same: 0, unknown: 0 };
    for (const r of recs) {
      if (!known[r.s]) { out.unknown++; continue; }
      const cur = sales[r.s];
      const before = cur ? cur.st === 1 : !!known[r.s].s;
      if (cur && r.t <= cur.t) { out.same++; continue; }
      if (cur) { cur.st = r.st; cur.t = r.t; } else sales[r.s] = { st: r.st, t: r.t, imp: 1 };
      const after = r.st === 1;
      if (before === after) out.same++; else if (after) out.added++; else out.voided++;
    }
    return out;
  },
};

/* ---------- small utilities ---------- */
function downloadText(name, text, mime) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: mime || 'text/plain' }));
  a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
}
async function copyText(text, why) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {}
  try {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.focus(); ta.select();
    const ok = document.execCommand('copy'); ta.remove();
    if (ok) return true;
  } catch (e) {}
  await UI.modal({
    tone: 'info', icon: '⧉', title: 'Copy this text',
    body: (why ? why + '<br>' : '') + 'Press and hold inside the box, choose <b>Select all</b>, then <b>Copy</b>.',
    input: { rows: 5, value: text, readonly: true },
    buttons: [{ label: 'Done', value: true }],
    onOpen: x => { if (x.input) x.input.select(); },
  });
  return false;
}
const storeApi = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } },
};
