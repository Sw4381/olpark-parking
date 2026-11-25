// 올팍 주차예보 공통: 데이터 읽기와 시간·혼잡 단계 계산
const OP = (() => {
  const LIVE_URL = 'https://www.ksponco.or.kr/online/main/parkingorsApi.do?apiKey=PARKING21803504';
  // 수용 대수와 단계 기준은 올림픽공원 누리집 "주차장 예상 이용률 서비스" 표기를 따른다(동2·남2·북2문 기준).
  const CAPACITY = 2200;
  const FULL = 0.9 * CAPACITY;
  // 실시간 API 값은 2025년 입출차 기록으로 복원한 주차 대수보다 일정하게 크다(출차 기록이 없는 차량이 쌓인 것으로 추정).
  // 그 차이를 data/forecast.json 의 live_offset 으로 받아 빼고 쓴다.
  let OFFSET = 0;
  const setOffset = v => { OFFSET = Number.isFinite(+v) ? +v : 0; };
  const offset = () => OFFSET;
  const core = v => Math.max(0, v - OFFSET);
  const LEVELS = ['여유', '다소 혼잡', '혼잡', '만차'];
  const level = pct => (pct >= 90 ? 3 : pct >= 70 ? 2 : pct >= 50 ? 1 : 0);
  const pctOf = n => Math.round((n / CAPACITY) * 100);

  const kstParts = (d = new Date()) => {
    const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(d).map(x => [x.type, x.value]));
    return { date: `${p.year}-${p.month}-${p.day}`, hm: `${p.hour}:${p.minute}`, min: +p.hour * 60 + +p.minute };
  };
  const kstDate = s => new Date(s.replace(' ', 'T') + '+09:00');
  const DOW = ['일', '월', '화', '수', '목', '금', '토'];
  const dow = date => DOW[new Date(date + 'T12:00:00+09:00').getUTCDay()];
  const shortDate = date => `${+date.slice(5, 7)}월 ${+date.slice(8, 10)}일(${dow(date)})`;
  const addDays = (date, n) => {
    const d = new Date(date + 'T12:00:00+09:00'); d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  };
  const hmText = hm => { const [h, m] = hm.split(':').map(Number); return m ? `${h}시 ${m}분` : `${h}시`; };

  const getText = async url => {
    const r = await fetch(url + (url.includes('?') ? '&' : '?') + 't=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(url + ' ' + r.status);
    return r.text();
  };
  const getJSON = async url => { try { return JSON.parse(await getText(url)); } catch { return null; } };
  const parseCSV = t => {
    const [head, ...rows] = t.trim().split(/\r?\n/).map(l => l.split(','));
    return rows.filter(r => r.length === head.length).map(r => Object.fromEntries(head.map((h, i) => [h, r[i]])));
  };
  const getCSV = async url => { try { return parseCSV(await getText(url)); } catch { return []; } };

  // 10분 간격 수집 기록
  const loadLog = async () => (await getCSV('data/parking_log.csv'))
    .map(r => ({ at: r.collected_at_kst, t: kstDate(r.collected_at_kst), v: +r.parking_sum }))
    .filter(r => Number.isFinite(r.v) && !isNaN(r.t));

  // 지금 값: 기관 API를 직접 부르고, 막히면 수집 기록의 마지막 값을 쓴다.
  const loadLive = async log => {
    try {
      const r = await fetch(LIVE_URL, { cache: 'no-store' });
      const v = +(await r.json())[0].parking_sum;
      if (!Number.isFinite(v)) throw new Error('bad value');
      return { v, at: kstParts().hm, live: true };
    } catch {
      const last = log[log.length - 1];
      return last ? { v: last.v, at: last.at.slice(5, 16), live: false } : null;
    }
  };

  // 06:00~24:00을 30분 36칸으로 나눈 하루 띠
  const SLOT0 = 360, SLOTS = 36;
  const slotOf = min => Math.floor((min - SLOT0) / 30);
  const hmToMin = hm => { const [h, m] = hm.split(':').map(Number); return h * 60 + m; };
  const daySlots = (log, date) => {
    const out = new Array(SLOTS).fill(null);
    for (const r of log) {
      if (r.at.slice(0, 10) !== date) continue;
      const i = slotOf(hmToMin(r.at.slice(11, 16)));
      if (i >= 0 && i < SLOTS) out[i] = Math.max(out[i] ?? 0, pctOf(core(r.v)));
    }
    return out;
  };
  const renderBand = (el, { actual = [], forecast = [], nowMin = null, showMins = [] }) => {
    const nowI = nowMin == null ? -1 : slotOf(nowMin);
    const showI = new Set(showMins.map(slotOf));
    let html = '';
    for (let i = 0; i < SLOTS; i++) {
      const a = actual[i], f = forecast[i];
      const v = a ?? f, cls = [a == null && f != null ? 'fc' : '', i === nowI ? 'now' : '', showI.has(i) ? 'show' : ''].filter(Boolean).join(' ');
      const hm = `${String(Math.floor((SLOT0 + i * 30) / 60)).padStart(2, '0')}:${i % 2 ? '30' : '00'}`;
      const label = v == null ? `${hm} 기록 없음` : `${hm} ${a == null ? '예상 ' : ''}${v}% ${LEVELS[level(v)]}`;
      const h = v == null ? 0 : Math.max(3, Math.min(v, 130) / 130 * 100);
      html += `<i ${v == null ? '' : `data-l="${level(v)}"`} class="${cls}" style="--h:${h.toFixed(1)}" title="${label}"></i>`;
    }
    el.innerHTML = html;
    el.setAttribute('role', 'img');
    // 막대를 누르거나 가리키면 아래 칸에 그 시각의 값을 보여 준다.
    const out = el.parentNode && el.parentNode.querySelector('.readout');
    if (out) {
      out.textContent = '';
      const pick = ev => {
        const b = ev.target.closest('i'); if (!b || !el.contains(b)) return;
        el.querySelectorAll('.sel').forEach(x => x.classList.remove('sel'));
        b.classList.add('sel'); out.textContent = b.title;
      };
      el.onclick = pick; el.onpointerover = pick;
    }
  };
  const forecastSlots = day => {
    const out = new Array(SLOTS).fill(null);
    for (const s of (day && day.slots) || []) {
      const i = slotOf(hmToMin(s.t));
      if (i >= 0 && i < SLOTS) out[i] = s.pct;
    }
    return out;
  };

  // 당일 보정: 지금 실측이 패턴보다 r대 많으면 t시각 예보에 k[s][t]*r 을 더한다. 계수는 data/model.json.
  const nowcast = (model, fday, obs, nowMin) => {
    if (!model || !fday) return null;
    const p = model.profiles[fday.key]; if (!p) return null;
    const s = Math.min(model.slots - 1, Math.max(0, Math.floor(nowMin / 30)));
    const r = obs - p.mean[s], k = model.k[s], first = model.slots - fday.slots.length;
    const slots = fday.slots.map((x, i) => {
      const j = first + i;
      if (j < s) return { ...x, past: true };
      const n = Math.max(0, Math.round(j === s ? obs : x.n + k[j] * r));
      return { ...x, n, pct: Math.round(n / CAPACITY * 100) };
    });
    const future = slots.filter(x => !x.past);
    const peak = future.reduce((a, b) => (b.n > a.n ? b : a), future[0]);
    return { s, r: Math.round(r), usual: p.mean[s], z: r / (model.resid_sd[s] || 1), slots, peak, cross: future.find(x => x.n >= FULL) || null };
  };

  // 공연 안내문에서 시작 시각을 뽑는다. 못 읽으면 빈 배열(문구는 그대로 보여 준다).
  const showTimes = text => {
    const out = new Set();
    const re = /(오전|오후|AM|PM)?\s*(\d{1,2})\s*(?:시|:)\s*(\d{2})?\s*(?:분)?\s*(AM|PM)?/gi;
    for (const m of text.matchAll(re)) {
      if (!/시|:/.test(m[0]) ) continue;
      let h = +m[2]; const mm = +(m[3] || 0); const ap = (m[1] || m[4] || '').toUpperCase();
      if (h > 24 || mm > 59) continue;
      if ((ap === '오후' || ap === 'PM') && h < 12) h += 12;
      if (h >= 10 && h <= 22) out.add(h * 60 + mm);
    }
    for (const m of text.matchAll(/(\d{1,2})\s*(AM|PM)/gi)) {
      let h = +m[1]; if (m[2].toUpperCase() === 'PM' && h < 12) h += 12;
      if (h >= 10 && h <= 22) out.add(h * 60);
    }
    return [...out].sort((a, b) => a - b);
  };

  // 밝은·어두운 화면 전환
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('theme'); if (!btn) return;
    btn.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('op-theme', next); } catch {}
    });
  });

  // 숫자가 올라가며 바뀌는 표시
  const countTo = (el, to, ms = 900) => {
    const from = +el.dataset.v || 0; el.dataset.v = to;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches || from === to) { el.textContent = to.toLocaleString(); return; }
    const t0 = performance.now();
    const step = t => {
      const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(from + (to - from) * e).toLocaleString();
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
    setTimeout(() => { el.textContent = to.toLocaleString(); }, ms + 200);  // 탭이 가려져 있어도 끝값은 맞춘다
  };

  // 요일 x 시각 히트맵. 2025년 요일별 평균 패턴(06~24시)
  const renderHeat = (el, model, today) => {
    const names = ['월', '화', '수', '목', '금', '토', '일'], first = model.slots - SLOTS;
    let html = '<div class="heat-hours"><span></span>' + [6, 9, 12, 15, 18, 21].map(h => `<span>${h}시</span>`).join('') + '</div>', best = null, calm = null;
    for (let d = 0; d < 7; d++) {
      const p = model.profiles[String(d)]; if (!p) continue;
      html += `<div class="heat-row${d === today ? ' today' : ''}"><b>${names[d]}</b>`;
      for (let i = 0; i < SLOTS; i++) {
        const pct = Math.round(p.mean[first + i] / CAPACITY * 100), hm = `${String(Math.floor((SLOT0 + i * 30) / 60)).padStart(2, '0')}:${i % 2 ? '30' : '00'}`;
        if (!best || pct > best.pct) best = { d, hm, pct };
        if (i >= 8 && i <= 28 && (!calm || pct < calm.pct)) calm = { d, hm, pct };
        html += `<i data-l="${level(pct)}" style="--o:${(0.28 + Math.min(pct, 100) / 100 * 0.72).toFixed(2)}" title="${names[d]}요일 ${hm} 평균 ${pct}% ${LEVELS[level(pct)]}"></i>`;
      }
      html += '</div>';
    }
    el.innerHTML = html;
    const out = el.parentNode.querySelector('.readout');
    const pick = ev => { const b = ev.target.closest('i'); if (!b) return; el.querySelectorAll('.sel').forEach(x => x.classList.remove('sel')); b.classList.add('sel'); if (out) out.textContent = b.title; };
    el.onclick = pick; el.onpointerover = pick;
    return { best: best && { ...best, name: names[best.d] }, calm: calm && { ...calm, name: names[calm.d] } };
  };

  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  return { CAPACITY, FULL, setOffset, offset, core, nowcast, LEVELS, level, pctOf, kstParts, kstDate, shortDate, addDays, hmText, hmToMin, getJSON, getCSV,
    loadLog, loadLive, countTo, renderHeat, daySlots, forecastSlots, renderBand, showTimes, esc };
})();
