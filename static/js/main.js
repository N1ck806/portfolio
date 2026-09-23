/* ══════════════════════════════════════════════════════════════
   KHOREZM FOLIO · main.js
   Спокойные, осмысленные скрипты под editorial-портфолио.
   Управление: 1) хедер  2) reveal  3) фильтр  4) якоря  5) view transitions
   ══════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  /* Предпочтения пользователя: если он отключил анимации — уважаем */
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ══════════════════════════════════════════════════════════
     1. STICKY-ХЕДЕР — тонкая граница при скролле
     ══════════════════════════════════════════════════════════ */
  const header = document.getElementById('site-header');
  if (header) {
    let ticking = false;
    const apply = () => {
      header.classList.toggle('is-scrolled', window.scrollY > 8);
      ticking = false;
    };
    const onScroll = () => {
      if (!ticking) {
        requestAnimationFrame(apply);
        ticking = true;
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    apply();
  }

  /* ══════════════════════════════════════════════════════════
     2. REVEAL — появление блоков при попадании в viewport
     ══════════════════════════════════════════════════════════ */
  const reveals = document.querySelectorAll('.reveal');

  if (reduceMotion || !('IntersectionObserver' in window)) {
    reveals.forEach((el) => el.classList.add('is-in'));
  } else {
    const revealIO = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-in');
            revealIO.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );
    reveals.forEach((el) => revealIO.observe(el));
  }

  /* ══════════════════════════════════════════════════════════
     3. ФИЛЬТР ПО ТЕГАМ
     Работает с новой разметкой: .filters + .work-card + data-tags
     (оставлена поддержка и старых классов .filter-bar / .card)
     ══════════════════════════════════════════════════════════ */
  const filterBar =
    document.querySelector('.filters') ||
    document.querySelector('.filter-bar');

  const worksGrid =
    document.getElementById('works-grid') ||
    document.querySelector('.grid');

  const emptyMsg = document.getElementById('filter-empty');

  if (filterBar && worksGrid) {
    const buttons = Array.from(
      filterBar.querySelectorAll('.filter, .filter-chip')
    );

    const cards = Array.from(
      worksGrid.querySelectorAll('.work-card, .card')
    );

    const applyFilter = (value) => {
      let visible = 0;

      cards.forEach((card) => {
        const raw = card.dataset.tags || '';
        const tags = raw
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean);

        const show = value === 'all' || tags.includes(value);

        if (show) {
          card.classList.remove('is-hidden');
          // мягкое появление без скачков layout
          card.style.opacity = '0';
          card.style.transform = 'translateY(6px)';
          requestAnimationFrame(() => {
            card.style.opacity = '';
            card.style.transform = '';
          });
          visible++;
        } else {
          card.classList.add('is-hidden');
        }
      });

      if (emptyMsg) emptyMsg.hidden = visible !== 0;
    };

    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        buttons.forEach((b) => {
          const active = b === btn;
          b.classList.toggle('is-active', active);
          if (b.hasAttribute('aria-pressed')) {
            b.setAttribute('aria-pressed', String(active));
          }
        });

        // поддержка активной клавиатурной фокусировки
        btn.focus({ preventScroll: true });

        applyFilter(btn.dataset.filter || 'all');
      });
    });
  }

  /* ══════════════════════════════════════════════════════════
     4. ПЛАВНЫЙ СКРОЛЛ К ЯКОРЯМ
     Работает и для "/#works" (со страницы проекта), и для "#works"
     ══════════════════════════════════════════════════════════ */
  const anchorLinks = document.querySelectorAll(
    'a[href^="#"], a[href^="/#"]'
  );

  anchorLinks.forEach((link) => {
    link.addEventListener('click', (e) => {
      const href = link.getAttribute('href') || '';
      const hashIndex = href.indexOf('#');
      if (hashIndex === -1) return;

      const id = href.slice(hashIndex + 1);
      if (!id) return;

      const target = document.getElementById(id);
      if (!target) return;

      // если ссылка ведёт на другой путь (например, /#works со страницы
      // проекта) — не мешаем браузеру, он сам перейдёт и проскроллит
      const path = href.slice(0, hashIndex);
      if (path && path !== '' && path !== '/') return;

      e.preventDefault();

      const top =
        target.getBoundingClientRect().top +
        window.scrollY -
        (header ? header.offsetHeight + 16 : 80);

      window.scrollTo({
        top,
        behavior: reduceMotion ? 'auto' : 'smooth',
      });

      // обновляем hash в адресной строке без прыжка
      if (history.replaceState) {
        history.replaceState(null, '', '#' + id);
      }
    });
  });

  /* ══════════════════════════════════════════════════════════
     5. VIEW TRANSITIONS — плавный переход «архив → проект»
     ══════════════════════════════════════════════════════════ */
  if (document.startViewTransition && !reduceMotion) {
    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[href^="/project/"]');
      if (!link) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (e.button !== 0) return;

      // якорные ссылки внутри страницы игнорируем
      const href = link.getAttribute('href');
      if (!href || href.startsWith('#')) return;

      e.preventDefault();
      document.startViewTransition(() => {
        window.location.href = link.href;
      });
    });
  }

  /* ══════════════════════════════════════════════════════════
     6. КЛАВИАТУРА — быстрые переходы по секциям на главной
     G → works, A → about, C → contact (только если не в поле ввода)
     ══════════════════════════════════════════════════════════ */
  document.addEventListener('keydown', (e) => {
    // не срабатываем, если пользователь печатает в поле
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) {
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    const map = { g: 'works', a: 'about', c: 'contact' };
    const id = map[e.key.toLowerCase()];
    if (!id) return;

    const target = document.getElementById(id);
    if (!target) return;

    e.preventDefault();
    const top =
      target.getBoundingClientRect().top +
      window.scrollY -
      (header ? header.offsetHeight + 16 : 80);

    window.scrollTo({
      top,
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
  });

  /* ══════════════════════════════════════════════════════════
     7. ВНЕШНИЕ ССЫЛКИ — добавляем rel="noopener" и метку
     на всякий случай, если где-то в шаблоне её забыли
     ══════════════════════════════════════════════════════════ */
  document.querySelectorAll('a[target="_blank"]').forEach((a) => {
    const rel = a.getAttribute('rel') || '';
    if (!rel.includes('noopener')) {
      a.setAttribute('rel', (rel + ' noopener').trim());
    }
  });

  /* ══════════════════════════════════════════════════════════
     8. ГОД В ФУТЕРЕ — если где-то стоит data-year
     (на случай, если захочется обновлять автоматически)
     ══════════════════════════════════════════════════════════ */
  document.querySelectorAll('[data-year]').forEach((el) => {
    el.textContent = String(new Date().getFullYear());
  });

})();