/* Портал БГИТУ — минимальный клиентский слой без зависимостей. */
(function () {
  'use strict';

  var burger = document.getElementById('burger');
  var nav = document.getElementById('cabNav');
  var backdrop = document.getElementById('navBackdrop');
  var navClose = document.getElementById('navClose');

  function setMenu(open) {
    if (!burger || !nav || !backdrop) return;
    burger.setAttribute('aria-expanded', String(open));
    nav.classList.toggle('is-open', open);
    backdrop.classList.toggle('is-open', open);
    backdrop.hidden = !open;
    document.body.classList.toggle('nav-open', open);
    if (open && navClose) navClose.focus();
  }

  if (burger && nav && backdrop) {
    burger.addEventListener('click', function () {
      setMenu(!nav.classList.contains('is-open'));
    });
    backdrop.addEventListener('click', function () {
      setMenu(false);
      burger.focus();
    });
    if (navClose) {
      navClose.addEventListener('click', function () {
        setMenu(false);
        burger.focus();
      });
    }
    nav.addEventListener('click', function (event) {
      if (event.target.closest('a') && window.matchMedia('(max-width: 1000px)').matches) {
        setMenu(false);
      }
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && nav.classList.contains('is-open')) {
        setMenu(false);
        burger.focus();
      }
    });
  }

  var head = document.getElementById('siteHead');
  if (head) {
    var onScroll = function () {
      head.classList.toggle('is-stuck', window.scrollY > 24);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // Сообщения не мешают работе: плавно убираем через 7 секунд.
  var flashes = document.querySelectorAll('.flash');
  if (flashes.length) {
    window.setTimeout(function () {
      flashes.forEach(function (node) {
        node.style.transition = 'opacity .4s ease';
        node.style.opacity = '0';
        window.setTimeout(function () { node.remove(); }, 420);
      });
    }, 7000);
  }
})();
