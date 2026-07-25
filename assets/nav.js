/* 因果鏈導覽：每頁標出自己在哪一段，讓人隨時知道正在看什麼、為什麼要看 */
const CHAIN = [
  {k:'customers', href:'customers.html', s:'01　客戶',
   t:'最有錢的一群<strong>正在流失</strong>'},
  {k:'basket',    href:'basket.html',    s:'02　商品',
   t:'想推的搭配組合<strong>指向起司</strong>'},
  {k:'supply',    href:'supply.html',    s:'03　庫存',
   t:'起司<strong>缺 743 件</strong>，且是冷藏品'},
  {k:'delivery',  href:'delivery.html',  s:'04　配送',
   t:'冷藏運能<strong>只剩 138 公斤</strong>'},
];

function topbar(cur) {
  const items = [
    ['index.html','摘要'],['customers.html','客戶'],['basket.html','商品'],
    ['voice.html','客訴'],['supply.html','庫存'],['delivery.html','配送'],
    ['agent.html','自動化'],['method.html','方法'],
  ];
  return `<header class="top"><div class="top-in">
    <div class="brand">AI 智慧營運決策中樞</div>
    <nav class="nav">${items.map(([h,t]) =>
      `<a href="${h}"${h===cur?' class="on"':''}>${t}</a>`).join('')}</nav>
  </div></header>`;
}

function whereBar(key) {
  return `<div class="where">${CHAIN.map(c =>
    `<a href="${c.href}"${c.k===key?' class="on"':''}>
      <span class="s">${c.s}</span>${c.t}</a>`).join('')}</div>`;
}

/* 名詞＋白話：專有名詞留著，但旁邊立刻給一句人話 */
function term(name, plain) {
  return `<span class="term" title="${plain}">${name}</span>` +
    `<span class="gloss">（${plain}）</span>`;
}
