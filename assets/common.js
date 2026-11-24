// 올팍 주차예보 공통: 데이터 읽기와 시간·혼잡 단계 계산
const OP = (() => {
  const LIVE_URL = 'https://www.ksponco.or.kr/online/main/parkingorsApi.do?apiKey=PARKING21803504';
  // 수용 대수와 단계 기준은 올림픽공원 누리집 "주차장 예상 이용률 서비스" 표기를 따른다.
  const CAPACITY = 2200;
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
      if (i >= 0 && i < SLOTS) out[i] = Math.max(out[i] ?? 0, pctOf(r.v));
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
      html += `<i ${v == null ? '' : `data-l="${level(v)}"`} class="${cls}" title="${label}"></i>`;
    }
    el.innerHTML = html;
    el.setAttribute('role', 'img');
  };
  const forecastSlots = day => {
    const out = new Array(SLOTS).fill(null);
    for (const s of (day && day.slots) || []) {
      const i = slotOf(hmToMin(s.t));
      if (i >= 0 && i < SLOTS) out[i] = s.pct;
    }
    return out;
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

  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  return { CAPACITY, LEVELS, level, pctOf, kstParts, kstDate, shortDate, addDays, hmText, hmToMin, getJSON, getCSV,
    loadLog, loadLive, daySlots, forecastSlots, renderBand, showTimes, esc };
})();
