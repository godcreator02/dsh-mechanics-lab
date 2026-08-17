/* 说明页的运行时验收：门禁静态扫不到的那部分。

   pagegate.py 读文件，看不见「点下去会不会炸」。三次事故都是这么漏出去的：
   config-delivery 的 initPicker 撞 null、字段表第三列被挤到 48px、树里的行点开
   是空的。所以每批页面落盘后都要在浏览器里跑一遍这个。

   用法：本地起静态服务器（`python -m http.server 8791 --bind 127.0.0.1
   --directory <仓库根>`），逐页 navigate 到
   `http://127.0.0.1:8791/experiments/<组>/<项>/index.html?v=N`
   （改过文件一定要换 `?v=`，否则读缓存），然后把本文件内容整段注入执行。

   ⚠️ 页内样式的体量**不在这里量**。浏览器扩展会往 <head> 注入自己的 <style>，
   实测能有 8 个、七千多字节，把页面自己的 1259 字节淹掉一个数量级——照这个数
   去对 agent 的自报值，会得出「它虚报了十倍」的结论，而页面是干净的。
   样式体量在磁盘上量：pagegate.py 或直接数文件里的 <style> 块。 */

(() => {
  const out = {
    errs: [],          // onerror 与 console.error
    extern: [],        // 外部资源，应当只有 lab.css / lab.js
    picks: 0,          // .pick 枚举项，逐个点过
    tws: 0,            // 折叠开关，点开再点回
    fileCount: 0,      // 树里的可点文件行
    dead: [],          // 点开之后文件窗是空的——树上的死行
    wrapped: [],       // 折了行的短标签：版面挤坏的信号
    overflowX: 0,      // 正文横向溢出，应当为 0
  };

  window.addEventListener('error', (e) => out.errs.push('onerror: ' + e.message));
  const oe = console.error;
  console.error = (...a) => { out.errs.push('console.error: ' + a.join(' ')); oe.apply(console, a); };

  out.extern = [...document.querySelectorAll('link[href],script[src],img[src]')]
    .map((e) => e.getAttribute('href') || e.getAttribute('src'));

  const picks = [...document.querySelectorAll('.pick')];
  out.picks = picks.length;
  picks.forEach((p) => { try { p.click(); } catch (err) { out.errs.push('pick: ' + err.message); } });

  // 点开再点回：两轮都不该报错，且不该把树的状态搞乱
  const tws = [...document.querySelectorAll('.ft .tw')];
  out.tws = tws.length;
  tws.forEach((t) => t.click());
  tws.forEach((t) => t.click());

  // 每个文件行都点一遍，文件窗必须真的有内容。空的就是死行——读者分不清是
  // 页面没做还是那个位置本来没文件，而这正是「所有文件都要能点开」要防的。
  const vcode = document.getElementById('vcode');
  const fls = [...document.querySelectorAll('.ft .fl')];
  out.fileCount = fls.length;
  fls.forEach((f) => {
    try { f.click(); } catch (err) { out.errs.push('file: ' + err.message); }
    const len = vcode ? vcode.textContent.length : -1;
    if (len <= 0) out.dead.push(f.textContent.replace(/[├└─│▾▸]/g, '').trim() + ' → ' + len);
  });

  // 折行检测比宽度阈值准：窄本身不是毛病，同一组标签里只有一个折了才是。
  // 拿实际高度跟行高比，超过 1.6 倍就是折了。
  document.querySelectorAll('td,th,.k,.nm,.hd,.name,.file,.c-name').forEach((e) => {
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4;
    if (r.height > lh * 1.6 && e.textContent.trim().length > 3) {
      out.wrapped.push(
        e.tagName + '.' + e.className + ' ' + Math.round(r.width) + 'x' + Math.round(r.height)
        + ' «' + e.textContent.trim().slice(0, 20) + '»'
      );
    }
  });

  out.overflowX = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  return JSON.stringify(out, null, 1);
})();
