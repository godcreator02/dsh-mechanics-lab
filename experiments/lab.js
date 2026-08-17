/* 实验说明页共用的脚本：ASCII 文件树、枚举选择器、侧边文件窗。

   页内 <script> 排在本文件之后、按序执行，所以页内可以直接调 initPicker()。
   本文件放在 body 末尾，树绘制跑起来时 DOM 已就绪。*/

/* 树：ASCII 连接线从嵌套结构算出来。每行前缀只取决于各级祖先「是不是最后一个兄弟」，
   是静态的——折叠只隐藏子树、不改前缀，所以连接线和折叠并存不冲突。 */
(() => {
  const rowOf = li => {
    let r = li.querySelector(':scope > button, :scope > .flabel');
    if (r) return r;
    r = document.createElement('span');
    r.className = 'txt';
    while (li.firstChild && li.firstChild.nodeName !== 'UL') r.appendChild(li.firstChild);
    li.insertBefore(r, li.firstChild);
    return r;
  };
  const paint = (ul, pad, root) => {
    const items = [...ul.children].filter(e => e.tagName === 'LI');
    items.forEach((li, i) => {
      const last = i === items.length - 1;
      const sub = li.querySelector(':scope > ul');
      const row = rowOf(li);
      const cv = document.createElement('span');
      cv.className = 'cv';
      // 箭头单独占两列：没有子树的留两个空格，名字列才对得齐
      cv.textContent = sub ? (li.classList.contains('shut') ? '▸ ' : '▾ ') : '  ';
      const pf = document.createElement('span');
      pf.className = 'pf';
      pf.textContent = root ? '' : pad + (last ? '└─ ' : '├─ ');
      row.insertBefore(cv, row.firstChild);
      row.insertBefore(pf, row.firstChild);
      if (sub) paint(sub, root ? '' : pad + (last ? '   ' : '│  '), false);
    });
  };
  document.querySelectorAll('.ft').forEach(ft => paint(ft, '', true));

  document.querySelectorAll('.ft .tw').forEach(b => {
    b.addEventListener('click', () => {
      const li = b.parentElement;
      li.classList.toggle('shut');
      const cv = b.querySelector('.cv');
      if (cv) cv.textContent = li.classList.contains('shut') ? '▸ ' : '▾ ';
    });
  });
})();
/* 枚举选择器：一排可选项 ＋ 一个详情面板。点哪个看哪个——能跳着看的内容
   不该逼读者按序经过，所以这里没有上一步／下一步。
   opts.hover 打开时，hover 只是临时预览：它不动 cur，鼠标移开回落到选中那项。 */
function initPicker(root, render, opts = {}){
  const picks = [...root.querySelectorAll('.pick')];
  const body = root.querySelector('.pickbody');
  let cur = 0;
  const paint = i => {
    picks.forEach((p, k) => { p.classList.toggle('on', k === i); p.classList.toggle('dim', k !== i); });
    render(body, i);
  };
  picks.forEach((p, i) => {
    p.tabIndex = 0;
    p.addEventListener('click', () => { cur = i; paint(cur); });
    p.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { cur = i; paint(cur); e.preventDefault(); }
    });
    if (opts.hover){
      p.addEventListener('mouseenter', () => paint(i));
      p.addEventListener('focus', () => paint(i));
    }
  });
  if (opts.hover) root.addEventListener('mouseleave', () => paint(cur));
  paint(0);
  return { select: i => { cur = i; paint(cur); } };
}
const side = document.querySelector('.side');
const vhint = document.getElementById('vhint'), vmeta = document.getElementById('vmeta');
const vname = document.getElementById('vname'), vsrc = document.getElementById('vsrc');
const vwhy = document.getElementById('vwhy'), vcode = document.getElementById('vcode');
document.querySelectorAll('.ft .fl').forEach(b => {
  b.addEventListener('click', () => {
    const box = document.getElementById('fc-' + b.dataset.k);
    document.querySelectorAll('.ft .fl.on').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    vname.textContent = box.dataset.name;
    vsrc.textContent = box.dataset.src;
    vwhy.textContent = box.dataset.why;
    // 克隆，别搬走 stash 里的原件——它是校验脚本比对的对象
    vcode.replaceChildren(box.querySelector('pre').cloneNode(true));
    vhint.hidden = true; vmeta.hidden = false;
    side.classList.add('has-file');
  });
});
