/* 共用：導覽列、資料載入。每一頁都能單獨進入，所以導覽由 JS 統一注入。 */
const PAGES = [
  ['index.html',     '摘要'],
  ['customers.html', '客戶'],
  ['basket.html',    '商品'],
  ['voice.html',     '客訴'],
  ['supply.html',    '庫存'],
  ['delivery.html',  '配送'],
  ['agent.html',     '自動化'],
  ['method.html',    '方法'],
];

function mountNav(current) {
  const nav = PAGES.map(([h, t]) =>
    `<a href="${h}" class="${h === current ? 'on' : ''}">${t}</a>`).join('');
  document.body.insertAdjacentHTML('afterbegin', `
    <header class="top"><div class="top-in">
      <div class="brand">AI 智慧營運決策中樞</div>
      <nav class="nav">${nav}</nav>
    </div></header>`);
}

const _cache = {};
async function load(name) {
  if (_cache[name]) return _cache[name];
  const r = await fetch(`data/${name}.json`);
  if (!r.ok) throw new Error(`載入 ${name} 失敗`);
  return (_cache[name] = await r.json());
}

function nextLink(href, label, why) {
  return `<div class="next">接下來值得看的是 <a href="${href}">${label}</a>——${why}</div>`;
}

function footer(builtAt) {
  return `<div class="foot">
    本頁所有數字由 <code>build_static.py</code> 實際計算產生，無預先寫入的結果。
    ${builtAt ? `最後計算於 ${builtAt}。` : ''}
    資料為課程模擬生成，用於驗證分析流程；換成實際營運資料後同一套流程可直接重跑。
  </div>`;
}

function fail(box, e) {
  box.innerHTML = `<div class="panel">資料載入失敗：${e.message}<br>
    <span class="cap">若你是用檔案總管直接開啟 index.html，瀏覽器會擋住本機讀檔。
    請改用網址開啟，或在資料夾內執行 <code>python -m http.server</code>。</span></div>`;
}
