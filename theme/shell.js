/* Sheet / Dex / Calc without reloading anything.

   The dex and the calculator each live in an iframe that is built once and
   from then on only ever hidden, and the split pages are swapped in over
   fetch instead of navigated to. So whatever you have typed into the
   calculator survives moving around the sheet, and neither tool is ever
   loaded twice. */
(function () {
  var bar = document.querySelector('.mode-bar');
  var navbar = document.querySelector('.navbar');
  if (!bar) return;

  var VIEWS = { dex: 'dex.html', calc: 'calc.html' };
  var frames = {};
  var mode = 'sheet';

  /* A switcher that is always on screen, so you never scroll up to change
     view -- and it sits above the tool iframes, so it works from inside
     the calculator too. */
  var fab = document.createElement('div');
  fab.className = 'mode-fab';
  fab.innerHTML =
    '<button type="button" class="mode-fab-main" aria-label="Switch view" ' +
    'aria-expanded="false">&#8646;</button>' +
    '<div class="mode-fab-menu">' +
    '<a href="#sheet" data-mode="sheet">Trainer Sheet</a>' +
    '<a href="#dex" data-mode="dex">Pok\u00e9dex</a>' +
    '<a href="#calc" data-mode="calc">Calculator</a>' +
    '</div>';
  document.body.appendChild(fab);

  function fabOpen(on) {
    fab.classList.toggle('is-open', on);
    fab.querySelector('.mode-fab-main').setAttribute('aria-expanded', on ? 'true' : 'false');
  }

  var pages = {};
  if (navbar) {
    [].forEach.call(navbar.querySelectorAll('a[href$=".html"]'), function (a) {
      pages[a.getAttribute('href')] = a;
    });
  }

  function view(name) {
    if (frames[name]) return frames[name];
    var wrap = document.createElement('div');
    wrap.className = 'mode-view';
    wrap.setAttribute('data-view', name);
    var f = document.createElement('iframe');
    f.src = VIEWS[name];
    f.title = name === 'dex' ? 'Pokédex' : 'Damage calculator';
    wrap.appendChild(f);
    document.body.appendChild(wrap);
    frames[name] = wrap;
    return wrap;
  }

  function place() {
    /* the split nav sticks below the mode bar, which can wrap when narrow */
    document.documentElement.style.setProperty(
      '--mode-h', Math.round(bar.getBoundingClientRect().height) + 'px');

    var top = 0;
    if (navbar) top = navbar.getBoundingClientRect().bottom;
    else top = bar.getBoundingClientRect().bottom;
    for (var k in frames) frames[k].style.top = Math.max(0, Math.round(top)) + 'px';
  }

  function show(next) {
    mode = next;
    if (next !== 'sheet') view(next);
    place();
    for (var k in frames) frames[k].classList.toggle('is-open', k === next);
    document.body.classList.toggle('mode-open', next !== 'sheet');
    [].forEach.call(document.querySelectorAll('a[data-mode]'), function (a) {
      a.classList.toggle('is-active', a.getAttribute('data-mode') === next);
    });
    fabOpen(false);
    try { sessionStorage.setItem('nullMode', next); } catch (e) {}
  }

  function here() {
    return location.pathname.split('/').pop() || 'resources.html';
  }

  function swap(html, href) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var next = doc.querySelector('.pfx-panel');
    var cur = document.querySelector('.pfx-panel');
    if (!next || !cur) { location.href = href; return; }

    cur.replaceWith(next);

    /* the home page carries a reference panel the split pages don't */
    [].forEach.call(document.querySelectorAll('.ref-panel'), function (n) {
      n.remove();
    });
    var ref = doc.querySelector('.ref-panel');
    if (ref) next.after(ref);

    document.title = doc.title;
    for (var k in pages) pages[k].classList.toggle('on', k === href);
    window.scrollTo(0, 0);
    if (typeof decorateSplitTables === 'function') decorateSplitTables();
  }

  function go(href, push) {
    fetch(href).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.text();
    }).then(function (html) {
      swap(html, href);
      if (push) history.pushState({ href: href }, '', href);
    })['catch'](function () {
      location.href = href;
    });
  }

  document.addEventListener('click', function (e) {
    var main = e.target.closest ? e.target.closest('.mode-fab-main') : null;
    if (main) {
      e.preventDefault();
      fabOpen(!fab.classList.contains('is-open'));
      return;
    }
    if (fab.classList.contains('is-open') &&
        !(e.target.closest && e.target.closest('.mode-fab'))) {
      fabOpen(false);
    }

    var a = e.target.closest ? e.target.closest('a') : null;
    if (!a) return;

    var m = a.getAttribute('data-mode');
    if (m) {
      e.preventDefault();
      show(m);
      return;
    }

    var href = a.getAttribute('href');
    if (!href || !pages.hasOwnProperty(href)) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;

    e.preventDefault();
    show('sheet');
    if (href === here()) { window.scrollTo(0, 0); return; }
    go(href, true);
  });

  window.addEventListener('popstate', function () {
    show('sheet');
    go(here(), false);
  });
  window.addEventListener('resize', place);

  place();

  try {
    var saved = sessionStorage.getItem('nullMode');
    if (saved && saved !== 'sheet') show(saved);
  } catch (e) {}
})();
