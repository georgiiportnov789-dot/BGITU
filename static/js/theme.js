/* БГИТУ — темы оформления (paper/surik/latun/brass).
   Порядок: ?theme= в адресе → сохранённый выбор → «Бумага» (data-theme на <html>). */
(function () {
  'use strict';

  var THEMES = ['paper', 'surik', 'latun', 'brass'];
  var COOKIE = 'bgitu-theme';
  var META_COLORS = { paper: '#f2eee6', surik: '#0d0d0d', latun: '#0d0d0d', brass: '#f2eee6' };
  var root = document.documentElement;

  /* Тему задаёт сервер (профиль пользователя или cookie) — до отрисовки.
     ?theme= остаётся для предпросмотра. */
  var q = new URLSearchParams(window.location.search);
  var theme = q.get('theme');
  if (THEMES.indexOf(theme) !== -1) root.dataset.theme = theme;

  function cookie(name) {
    return document.cookie.split('; ').reduce(function (acc, part) {
      var i = part.indexOf('=');
      return part.slice(0, i) === name ? decodeURIComponent(part.slice(i + 1)) : acc;
    }, '');
  }

  /* Тема пришла с сервера (профиль) — продублируем её в cookie,
     чтобы выбор остался и после выхода из кабинета. */
  (function syncCookie() {
    var current = root.dataset.theme || 'paper';
    if (cookie(COOKIE) !== current) {
      document.cookie = COOKIE + '=' + current + '; max-age=' + (365 * 24 * 3600) + '; path=/; samesite=Lax';
    }
  })();

  /* Запомнить выбор: cookie на год + профиль (если пользователь вошёл). */
  function persist(name) {
    document.cookie = COOKIE + '=' + name + '; max-age=' + (365 * 24 * 3600) + '; path=/; samesite=Lax';
    if (root.dataset.auth !== '1') return;
    var token = cookie('csrftoken');
    fetch('/theme/', {
      method: 'POST',
      credentials: 'same-origin',
      keepalive: true,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': token },
      body: 'theme=' + encodeURIComponent(name)
    }).catch(function () {});
  }

  function syncMeta() {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', META_COLORS[root.dataset.theme] || META_COLORS.paper);
  }

  function syncRadios() {
    var current = root.dataset.theme || 'paper';
    document.querySelectorAll('[data-theme-set]').forEach(function (btn) {
      btn.setAttribute('aria-checked', String(btn.getAttribute('data-theme-set') === current));
    });
  }

  function setTheme(name) {
    root.classList.add('theme-anim');
    setTimeout(function () { root.classList.remove('theme-anim'); }, 500);
    root.dataset.theme = name;
    persist(name);
    syncRadios();
    syncMeta();
    document.dispatchEvent(new Event('bgitu:palette'));
  }

  document.addEventListener('DOMContentLoaded', function () {
    syncMeta();
    syncRadios();

    document.addEventListener('click', function (event) {
      var btn = event.target.closest('[data-theme-set]');
      if (!btn) return;
      setTheme(btn.getAttribute('data-theme-set'));
      var pop = document.getElementById('theme-pop');
      if (pop && pop.matches(':popover-open')) {
        setTimeout(function () { pop.hidePopover(); }, 180);
      }
    });

    /* Стрелки внутри группы тем. */
    document.addEventListener('keydown', function (event) {
      var target = event.target;
      var btn = target.closest ? target.closest('[data-theme-set]') : null;
      if (!btn || !/Arrow(Up|Down)/.test(event.key)) return;
      var all = Array.prototype.slice.call(btn.parentElement.querySelectorAll('[data-theme-set]'));
      var i = all.indexOf(btn);
      var next = all[(i + (event.key === 'ArrowDown' ? 1 : all.length - 1)) % all.length];
      if (next) next.focus();
      event.preventDefault();
    });
  });
})();
