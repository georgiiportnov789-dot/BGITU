/* ============================================================
   БГИТУ — логика личного кабинета
   Профиль (localStorage), роли, стипендия, расписание, задачи.
   Без зависимостей. Данные — assets/js/data.js.
   ============================================================ */

(function () {
  'use strict';

  var DATA = window.BGITU_DATA;
  var PORTAL = window.BGITU_PORTAL || { recordBook: { terms: [] }, debts: { open: [], history: [], rules: '' }, curriculum: { semesters: [], totalCredits: 240 }, requestTypes: [], requests: [], portfolio: [], portfolioCategories: [], portfolioLevels: [], mail: [] };
  var STORAGE_KEY = 'bgitu.cabinet.v1';
  var ROLE_SHORT = {
    student: 'студент',
    monitor: 'староста',
    teacher: 'преподаватель',
    dean: 'деканат',
    editor: 'редактор',
    rector: 'руководство',
    admin: 'администратор'
  };
  var DAYS = [
    { n: 1, short: 'Пн' },
    { n: 2, short: 'Вт' },
    { n: 3, short: 'Ср' },
    { n: 4, short: 'Чт' },
    { n: 5, short: 'Пт' },
    { n: 6, short: 'Сб' }
  ];

  /* Заголовки и подписи экранов кабинета. Разметка — константы проекта. */
  var VIEW_META = {
    overview: {
      crumb: 'Обзор',
      badge: 'демо-режим',
      title: 'Личный кабинет <span class="hl">студента</span>',
      lead: 'Данные о себе, предполагаемая стипендия и расписание группы — на одном экране. Правки профиля сохраняются в этом браузере.',
      doc: 'Личный кабинет — БГИТУ'
    },
    grades: {
      crumb: 'Оценки',
      badge: 'зачётная книжка',
      title: 'Оценки и <span class="hl">зачётная книжка</span>',
      lead: 'Оценки по семестрам, зачёты и средний балл. Текущий семестр обновляется по мере закрытия ведомостей.',
      doc: 'Оценки — личный кабинет БГИТУ'
    },
    debts: {
      crumb: 'Задолженности',
      badge: 'сессия',
      title: 'Задолженности и <span class="hl">пересдачи</span>',
      lead: 'Что не закрыто, когда пересдача и как записаться. История закрытых задолженностей сохраняется.',
      doc: 'Задолженности — личный кабинет БГИТУ'
    },
    plan: {
      crumb: 'Учебный план',
      badge: 'план обучения',
      title: 'Учебный <span class="hl">план</span>',
      lead: 'Дисциплины по семестрам, зачётные единицы и что уже освоено. План привязан к направлению и году набора.',
      doc: 'Учебный план — личный кабинет БГИТУ'
    },
    requests: {
      crumb: 'Справки',
      badge: 'документы',
      title: 'Справки и <span class="hl">заявления</span>',
      lead: 'Заказ справок и заявлений без похода в деканат: статус, срок изготовления и готовая электронная копия.',
      doc: 'Справки — личный кабинет БГИТУ'
    },
    portfolio: {
      crumb: 'Портфолио',
      badge: 'достижения',
      title: 'Портфолио <span class="hl">достижений</span>',
      lead: 'Олимпиады, публикации, спорт и волонтёрство — то, из чего стипендиальная комиссия собирает ПГАС.',
      doc: 'Портфолио — личный кабинет БГИТУ'
    },
    mail: {
      crumb: 'Почта',
      badge: 'входящие',
      title: 'Почта <span class="hl">кабинета</span>',
      lead: 'Письма деканата, преподавателей и учебного отдела. Непрочитанные отмечены акцентом.',
      doc: 'Почта — личный кабинет БГИТУ'
    }
  };

  var STATUS_LABEL = { work: 'в работе', ready: 'готова', done: 'получена', canceled: 'отменена' };
  var STATUS_CLASS = { work: 'work', ready: 'ready', done: 'done', canceled: 'done' };

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  var state = {
    profile: Object.assign({}, DATA.student),
    stipend: { boost: true, social: false, pgas: 'science' },
    tasks: DATA.tasks.map(function (t) { return Object.assign({}, t); }),
    group: DATA.student.group,
    week: 0,
    view: 'overview',
    term: currentTermId(),
    requests: PORTAL.requests.map(function (r) { return Object.assign({}, r); }),
    portfolio: PORTAL.portfolio.map(function (p) { return Object.assign({}, p); }),
    mailRead: {},
    mailSelected: null
  };

  var canStore = true;
  var toastTimer = null;

  /* ---------- localStorage ---------- */
  function storageAvailable() {
    try {
      var probe = '__bgitu_probe__';
      window.localStorage.setItem(probe, '1');
      window.localStorage.removeItem(probe);
      return true;
    } catch (err) {
      return false;
    }
  }

  function save() {
    if (!canStore) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
        profile: state.profile,
        stipend: state.stipend,
        tasks: state.tasks.map(function (t) { return { id: t.id, done: t.done }; }),
        group: state.group,
        requests: state.requests,
        portfolio: state.portfolio,
        mailRead: state.mailRead
      }));
    } catch (err) {
      canStore = false;
      updateStorageNote();
    }
  }

  function load() {
    if (!canStore) return;
    var raw;
    try { raw = window.localStorage.getItem(STORAGE_KEY); } catch (err) { return; }
    if (!raw) return;
    var saved;
    try { saved = JSON.parse(raw); } catch (err) { return; }
    if (!saved || typeof saved !== 'object') return;

    if (saved.profile && typeof saved.profile === 'object') {
      var p = saved.profile;
      if (typeof p.fullName === 'string' && p.fullName.trim()) state.profile.fullName = p.fullName.trim();
      if (typeof p.birthDate === 'string') state.profile.birthDate = p.birthDate;
      if (typeof p.email === 'string') state.profile.email = p.email;
      if (typeof p.phone === 'string') state.profile.phone = p.phone;
      if (typeof p.group === 'string' && DATA.groups.some(function (g) { return g.id === p.group; })) state.profile.group = p.group;
      if (typeof p.course === 'number' && p.course >= 1 && p.course <= 5) state.profile.course = p.course;
      if (typeof p.form === 'string') state.profile.form = p.form;
      if (typeof p.basis === 'string') state.profile.basis = p.basis;
      if (typeof p.role === 'string' && roleById(p.role)) state.profile.role = p.role;
    }

    if (saved.stipend && typeof saved.stipend === 'object') {
      state.stipend.boost = Boolean(saved.stipend.boost);
      state.stipend.social = Boolean(saved.stipend.social);
      if (DATA.stipend.pgas.some(function (x) { return x.id === saved.stipend.pgas; })) state.stipend.pgas = saved.stipend.pgas;
    }

    if (Array.isArray(saved.tasks)) {
      state.tasks = DATA.tasks.map(function (t) {
        var found = saved.tasks.filter(function (x) { return x && x.id === t.id; })[0];
        return Object.assign({}, t, { done: found ? Boolean(found.done) : t.done });
      });
    }

    if (Array.isArray(saved.requests)) {
      state.requests = saved.requests.filter(function (r) {
        return r && typeof r.id === 'string' && r.id && typeof r.type === 'string' && r.type;
      }).map(function (r) {
        return {
          id: r.id,
          type: r.type,
          purpose: typeof r.purpose === 'string' ? r.purpose : '',
          created: typeof r.created === 'string' ? r.created : '',
          status: STATUS_LABEL[r.status] ? r.status : 'work',
          ready: typeof r.ready === 'string' ? r.ready : '',
          delivery: typeof r.delivery === 'string' ? r.delivery : 'электронно'
        };
      });
    }

    if (Array.isArray(saved.portfolio)) {
      state.portfolio = saved.portfolio.filter(function (p) {
        return p && typeof p.title === 'string' && p.title.trim();
      }).map(function (p) {
        return {
          id: typeof p.id === 'string' && p.id ? p.id : 'p' + Math.random().toString(36).slice(2, 8),
          title: p.title,
          category: typeof p.category === 'string' ? p.category : 'science',
          level: typeof p.level === 'string' ? p.level : 'vuz',
          date: typeof p.date === 'string' ? p.date : '',
          status: p.status === 'confirmed' ? 'confirmed' : 'review',
          note: typeof p.note === 'string' ? p.note : ''
        };
      });
    }

    if (saved.mailRead && typeof saved.mailRead === 'object') {
      Object.keys(saved.mailRead).forEach(function (id) {
        if (saved.mailRead[id]) state.mailRead[id] = true;
      });
    }

    if (typeof saved.group === 'string' && DATA.schedule[saved.group]) state.group = saved.group;
    else if (DATA.schedule[state.profile.group]) state.group = state.profile.group;
  }

  /* ---------- Утилиты ---------- */
  function roleById(id) {
    return DATA.roles.filter(function (r) { return r.id === id; })[0] || null;
  }

  function initials(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'БГ';
    return (parts[0].charAt(0) + (parts[1] ? parts[1].charAt(0) : '')).toUpperCase();
  }

  function firstName(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    return parts[1] || parts[0] || 'студент';
  }

  function formatDate(iso) {
    if (!iso) return 'не указана';
    var d = new Date(iso + 'T12:00:00');
    if (isNaN(d.getTime())) return 'не указана';
    return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).format(d);
  }

  function formatMoney(n) {
    return new Intl.NumberFormat('ru-RU').format(n);
  }

  function greeting() {
    var h = new Date().getHours();
    if (h < 5) return 'доброй ночи';
    if (h < 12) return 'доброе утро';
    if (h < 18) return 'добрый день';
    return 'добрый вечер';
  }

  function toast(message) {
    var el = $('#toast');
    if (!el) return;
    el.textContent = message;
    el.classList.add('is-on');
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () { el.classList.remove('is-on'); }, 2600);
  }

  function pad(n) { return String(n).padStart(2, '0'); }

  function mondayOfCurrentWeek() {
    var now = new Date();
    var dow = now.getDay() || 7;
    return new Date(now.getFullYear(), now.getMonth(), now.getDate() - (dow - 1));
  }

  function dateOfDay(dayN, week) {
    var d = mondayOfCurrentWeek();
    d.setDate(d.getDate() + (dayN - 1) + week * 7);
    return pad(d.getDate()) + '.' + pad(d.getMonth() + 1);
  }

  function updateStorageNote() {
    var note = $('.profile-note');
    if (!note) return;
    if (canStore) {
      note.textContent = 'Демо: изменения сохраняются в localStorage этого браузера. Роль меняет набор разделов в навигации — это показывает, как кабинет выглядит для разных участников.';
    } else {
      note.textContent = 'Демо: браузер блокирует локальное хранилище — правки живут до перезагрузки страницы. Роль меняет набор разделов в навигации.';
    }
  }

  /* ---------- Профиль ---------- */
  function renderProfile() {
    var p = state.profile;
    var role = roleById(p.role) || DATA.roles[0];
    var values = {
      fullName: p.fullName,
      birthDate: formatDate(p.birthDate),
      group: p.group,
      institute: p.institute,
      program: p.program,
      course: p.course + ' курс',
      form: p.form,
      basis: p.basis,
      email: p.email,
      phone: p.phone.trim() || 'не указан',
      roleLabel: role.label
    };

    $$('[data-profile]').forEach(function (el) {
      var key = el.getAttribute('data-profile');
      if (key === 'phone') {
        el.textContent = values.phone;
        el.classList.toggle('dim', !p.phone.trim());
        return;
      }
      if (key === 'roleLabel') {
        el.textContent = role.label;
        return;
      }
      if (Object.prototype.hasOwnProperty.call(values, key)) el.textContent = values[key];
    });

    $('#idName').textContent = p.fullName;
    $('#idAvatar').textContent = initials(p.fullName);
    $('#idGroup').textContent = p.group;
    $('#idInstitute').textContent = p.institute.replace(/\s+институт$/i, '');
    $('#idCourseForm').textContent = p.course + ' курс · ' + p.form.toLowerCase();
    $('#idRecord').textContent = p.recordBook;
    $('#headInitials').textContent = initials(p.fullName);
    $('#heroGroup').textContent = p.group;
    $('#heroCourse').textContent = p.course;
    $('#heroHello').textContent = firstName(p.fullName) + ', ' + greeting();

    var note = $('[data-role-note]');
    if (note) note.textContent = role.note;
    $('#headRole').textContent = ROLE_SHORT[role.id] || 'студент';
  }

  function applyRole() {
    var role = roleById(state.profile.role) || DATA.roles[0];
    $$('[data-role]').forEach(function (el) {
      var allowed = String(el.getAttribute('data-role')).split(',').map(function (s) { return s.trim(); });
      el.hidden = allowed.indexOf(role.id) === -1;
    });
    $('#headRole').textContent = ROLE_SHORT[role.id] || 'студент';
    var note = $('[data-role-note]');
    if (note) note.textContent = role.note;
  }

  function fillSelects() {
    var groupSelect = $('#groupSelect');
    var formGroup = $('#fGroup');
    var roleSelect = $('#fRole');
    var pgasSelect = $('#pgasSelect');

    groupSelect.innerHTML = '';
    formGroup.innerHTML = '';
    DATA.groups.forEach(function (g) {
      var o1 = document.createElement('option');
      o1.value = g.id;
      o1.textContent = g.label;
      groupSelect.appendChild(o1);
      var o2 = document.createElement('option');
      o2.value = g.id;
      o2.textContent = g.label;
      formGroup.appendChild(o2);
    });
    groupSelect.value = state.group;
    formGroup.value = state.profile.group;

    roleSelect.innerHTML = '';
    DATA.roles.forEach(function (r) {
      var o = document.createElement('option');
      o.value = r.id;
      o.textContent = r.label;
      roleSelect.appendChild(o);
    });
    roleSelect.value = state.profile.role;

    pgasSelect.innerHTML = '';
    DATA.stipend.pgas.forEach(function (p) {
      var o = document.createElement('option');
      o.value = p.id;
      o.textContent = p.label;
      pgasSelect.appendChild(o);
    });
    pgasSelect.value = state.stipend.pgas;
  }

  function syncForm() {
    var p = state.profile;
    $('#fFullName').value = p.fullName;
    $('#fBirth').value = p.birthDate || '';
    $('#fEmail').value = p.email;
    $('#fPhone').value = p.phone;
    $('#fGroup').value = p.group;
    $('#fCourse').value = String(p.course);
    $('#fForm').value = p.form;
    $('#fBasis').value = p.basis;
    $('#fRole').value = p.role;
    var role = roleById(p.role);
    $('#roleHint').textContent = role ? role.note : 'Роль меняет набор разделов кабинета.';
    var error = $('#formError');
    error.hidden = true;
    error.textContent = '';
  }

  function openProfileDialog() {
    syncForm();
    var dialog = $('#profileDialog');
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
      window.requestAnimationFrame(function () { $('#fFullName').focus(); });
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function closeProfileDialog() {
    var dialog = $('#profileDialog');
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
  }

  function showFormError(message) {
    var error = $('#formError');
    error.textContent = message;
    error.hidden = false;
    if (typeof error.scrollIntoView === 'function') {
      error.scrollIntoView({ block: 'nearest' });
    }
  }

  function submitProfile(event) {
    event.preventDefault();
    var fullName = $('#fFullName').value.trim().replace(/\s+/g, ' ');
    var birthDate = $('#fBirth').value;
    var email = $('#fEmail').value.trim();
    var phone = $('#fPhone').value.trim();
    var group = $('#fGroup').value;
    var course = Number($('#fCourse').value);
    var form = $('#fForm').value;
    var basis = $('#fBasis').value;
    var roleId = $('#fRole').value;

    if (fullName.split(' ').length < 2) {
      showFormError('Укажите фамилию и имя — как в зачётной книжке.');
      $('#fFullName').focus();
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      showFormError('Проверьте e-mail: нужен адрес вида name@bgitu.ru.');
      $('#fEmail').focus();
      return;
    }
    if (phone && phone.replace(/\D/g, '').length < 10) {
      showFormError('Телефон: не меньше 10 цифр или оставьте поле пустым.');
      $('#fPhone').focus();
      return;
    }
    if (!DATA.groups.some(function (g) { return g.id === group; })) {
      showFormError('Выберите группу из списка.');
      $('#fGroup').focus();
      return;
    }
    if (!roleById(roleId)) {
      showFormError('Выберите роль из списка.');
      $('#fRole').focus();
      return;
    }

    state.profile = Object.assign({}, state.profile, {
      fullName: fullName,
      birthDate: birthDate,
      email: email,
      phone: phone,
      group: group,
      course: course,
      form: form,
      basis: basis,
      role: roleId
    });
    if (DATA.schedule[group]) state.group = group;

    save();
    renderAll();
    closeProfileDialog();
    toast(canStore ? 'Данные обновлены' : 'Данные обновлены до перезагрузки');
  }

  /* ---------- Стипендия ---------- */
  function renderStipend() {
    var s = DATA.stipend;
    var boost = state.stipend.boost;
    var acad = Math.round(s.academicBase * (boost ? s.academicBoost : 1));
    var pgasItem = s.pgas.filter(function (x) { return x.id === state.stipend.pgas; })[0] || s.pgas[0];
    var social = state.stipend.social ? s.social : 0;
    var total = acad + pgasItem.sum + social;

    $('#acadSum').textContent = formatMoney(acad) + ' ₽';
    $('#acadNote').textContent = boost ? 'повышенная, коэффициент ×1,8' : 'обычная, без повышения';
    $('#pgasSum').textContent = formatMoney(pgasItem.sum) + ' ₽';
    $('#pgasNote').textContent = pgasItem.id === 'none' ? 'не назначена' : 'основание: ' + pgasItem.label.split(' · ')[0].toLowerCase();
    $('#socialSum').textContent = formatMoney(social) + ' ₽';
    $('#socialNote').textContent = state.stipend.social ? 'назначена · +' + formatMoney(s.social) + ' ₽' : 'не назначена';
    $('#stipTotal').textContent = formatMoney(total);
    $('#stipSumTotal').textContent = formatMoney(total) + ' ₽';

    $('#acadBoost').checked = boost;
    $('#socialPay').checked = state.stipend.social;
    $('#pgasSelect').value = state.stipend.pgas;
  }

  /* ---------- Расписание ---------- */
  function buildPair(pair) {
    var wrap = document.createElement('div');
    wrap.className = 'sched-pair' + (pair.canceled ? ' is-canceled' : '');
    var bell = DATA.bells.filter(function (b) { return b.n === pair.n; })[0];

    var time = document.createElement('div');
    time.className = 'sched-pair__time';
    var timeText = document.createElement('span');
    timeText.textContent = pair.n + ' · ' + (bell ? bell.start : '');
    time.appendChild(timeText);
    if (pair.changed || pair.note === 'замена') {
      var tag = document.createElement('span');
      tag.className = 'tag-mini';
      tag.textContent = 'замена';
      time.appendChild(tag);
    }
    wrap.appendChild(time);

    var subj = document.createElement('div');
    subj.className = 'sched-pair__subj';
    subj.textContent = pair.subject;
    wrap.appendChild(subj);

    var meta = document.createElement('div');
    meta.className = 'sched-pair__meta';
    var room = pair.room === 'стадион' ? 'стадион' : 'ауд. ' + pair.room;
    meta.textContent = pair.kind + ' · ' + room + (pair.note && pair.note !== 'замена' ? ' · ' + pair.note : '');
    wrap.appendChild(meta);

    return wrap;
  }

  function renderSchedule() {
    var data = (DATA.schedule[state.group] && DATA.schedule[state.group][state.week]) || {};
    var todayN = new Date().getDay() || 7;
    var grid = $('#schedGrid');
    grid.innerHTML = '';

    DAYS.forEach(function (day) {
      var cell = document.createElement('div');
      cell.className = 'sched-day' + (state.week === 0 && day.n === todayN ? ' is-today' : '');

      var name = document.createElement('div');
      name.className = 'sched-day__name';
      var nameShort = document.createElement('span');
      nameShort.textContent = day.short;
      var nameDate = document.createElement('span');
      nameDate.textContent = dateOfDay(day.n, state.week);
      name.appendChild(nameShort);
      name.appendChild(nameDate);
      cell.appendChild(name);

      var pairs = data[day.n] || [];
      if (!pairs.length) {
        var empty = document.createElement('p');
        empty.className = 'sched-empty';
        empty.textContent = 'нет пар';
        cell.appendChild(empty);
      } else {
        pairs.forEach(function (pair) { cell.appendChild(buildPair(pair)); });
      }
      grid.appendChild(cell);
    });

    $('#schedMeta').textContent = 'ИЭИ · корпус №2 · ' + state.group;
    $('#groupSelect').value = state.group;
    $$('.sched-tab').forEach(function (btn) {
      btn.setAttribute('aria-pressed', String(Number(btn.getAttribute('data-week')) === state.week));
    });
  }

  function buildICS() {
    var group = state.group;
    var data = (DATA.schedule[group] && DATA.schedule[group][state.week]) || {};
    var monday = mondayOfCurrentWeek();
    monday.setDate(monday.getDate() + state.week * 7);
    var stamp = icsLocal(new Date());
    var lines = [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//BGITU//Cabinet demo//RU',
      'CALSCALE:GREGORIAN',
      'METHOD:PUBLISH',
      'X-WR-CALNAME:БГИТУ · ' + group
    ];

    DAYS.forEach(function (day) {
      (data[day.n] || []).forEach(function (pair) {
        var bell = DATA.bells.filter(function (b) { return b.n === pair.n; })[0];
        if (!bell) return;
        var d = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + (day.n - 1));
        var start = atTime(d, bell.start);
        var end = atTime(d, bell.end);
        lines.push('BEGIN:VEVENT');
        lines.push('UID:' + group + '-' + day.n + '-' + pair.n + '-' + start.getTime() + '@bgitu.demo');
        lines.push('DTSTAMP:' + stamp);
        lines.push('DTSTART;TZID=Europe/Moscow:' + icsLocal(start));
        lines.push('DTEND;TZID=Europe/Moscow:' + icsLocal(end));
        lines.push('SUMMARY:' + escapeICS(pair.subject + ' (' + pair.kind + ')'));
        lines.push('LOCATION:' + escapeICS(pair.room === 'стадион' ? 'стадион' : 'ауд. ' + pair.room));
        lines.push('END:VEVENT');
      });
    });

    lines.push('END:VCALENDAR');
    return lines.join('\r\n');
  }

  function atTime(date, hhmm) {
    var parts = hhmm.split(':');
    return new Date(date.getFullYear(), date.getMonth(), date.getDate(), Number(parts[0]), Number(parts[1]), 0);
  }

  function icsLocal(date) {
    return '' + date.getFullYear() + pad(date.getMonth() + 1) + pad(date.getDate()) +
      'T' + pad(date.getHours()) + pad(date.getMinutes()) + pad(date.getSeconds());
  }

  function escapeICS(value) {
    return String(value).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
  }

  function downloadICS() {
    var text = buildICS();
    var blob = new Blob([text], { type: 'text/calendar;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'bgitu-' + state.group + '-week' + (state.week + 1) + '.ics';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
    toast('Файл календаря сформирован');
  }

  /* ---------- Задачи ---------- */
  function renderTaskProgress() {
    var total = state.tasks.length;
    var done = state.tasks.filter(function (t) { return t.done; }).length;
    $('#taskCount').textContent = done + ' из ' + total;
    var bar = $('#taskBar');
    if (bar) bar.style.width = (total ? Math.round(done / total * 100) : 0) + '%';
  }

  function renderTasks() {
    var list = $('#taskList');
    list.innerHTML = '';
    state.tasks.forEach(function (task) {
      var label = document.createElement('label');
      label.className = 'task';
      var input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = task.done;
      input.setAttribute('data-task', task.id);

      var text = document.createElement('span');
      text.className = 'task__text';
      var title = document.createElement('b');
      title.textContent = task.title;
      var note = document.createElement('small');
      note.textContent = task.note;
      text.appendChild(title);
      text.appendChild(note);
      label.appendChild(input);
      label.appendChild(text);

      input.addEventListener('change', function () {
        task.done = input.checked;
        renderTaskProgress();
        save();
      });

      list.appendChild(label);
    });
    renderTaskProgress();
  }

  /* ============================================================
     РАЗДЕЛЫ: оценки, задолженности, план, заявки, портфолио, почта
     ============================================================ */

  function dateKey(value) {
    var m = /^(\d{2})\.(\d{2})\.(\d{4})/.exec(value || '');
    if (m) return m[3] + m[2] + m[1];
    m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value || '');
    if (m) return m[1] + m[2] + m[3];
    return '0';
  }

  function shortDate(value) {
    if (!value) return '';
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
    if (m) return m[3] + '.' + m[2] + '.' + m[1];
    return value;
  }

  function todayShort() {
    var d = new Date();
    return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' + d.getFullYear();
  }

  function todayISO() {
    var d = new Date();
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  function mailDate(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + ' · ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function mailFullDate(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return new Intl.DateTimeFormat('ru-RU', {
      day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit'
    }).format(d);
  }

  function termById(id) {
    var terms = PORTAL.recordBook.terms;
    return terms.filter(function (t) { return t.id === id; })[0] || null;
  }

  function currentTermId() {
    var terms = PORTAL.recordBook.terms;
    for (var i = terms.length - 1; i >= 0; i--) if (terms[i].status === 'текущий') return terms[i].id;
    return terms.length ? terms[terms.length - 1].id : '';
  }

  function controlLabel(control) {
    var map = { 'экзамен': 'экзамен', 'зачёт': 'зачёт', 'курсовая': 'курсовая работа', 'практика': 'практика' };
    return map[control] || control;
  }

  function gradeValue(grade) {
    return /^[345]$/.test(grade) ? Number(grade) : null;
  }

  function avgOf(items) {
    var nums = items.map(function (i) { return gradeValue(i.grade); }).filter(function (n) { return n !== null; });
    if (!nums.length) return null;
    return nums.reduce(function (a, b) { return a + b; }, 0) / nums.length;
  }

  function fmtAvg(value) {
    return value === null ? '—' : value.toFixed(2).replace('.', ',');
  }

  function allItems() {
    return PORTAL.recordBook.terms.reduce(function (acc, t) { return acc.concat(t.items || []); }, []);
  }

  function sumCredits(items) {
    return items.reduce(function (a, i) { return a + (i.credits || 0); }, 0);
  }

  function requestType(id) {
    return PORTAL.requestTypes.filter(function (t) { return t.id === id; })[0] || { id: id, label: 'Документ', term: '', note: '' };
  }

  function categoryById(id) {
    return PORTAL.portfolioCategories.filter(function (c) { return c.id === id; })[0] || { id: id, label: 'Достижение', pgas: '' };
  }

  function levelById(id) {
    return PORTAL.portfolioLevels.filter(function (l) { return l.id === id; })[0] || { id: id, label: 'Уровень не указан' };
  }

  function emptyBlock(title, text) {
    var box = document.createElement('div');
    box.className = 'empty';
    var b = document.createElement('b');
    b.textContent = title;
    var p = document.createElement('p');
    p.textContent = text;
    box.appendChild(b);
    box.appendChild(p);
    return box;
  }

  function addStat(box, label, value, note) {
    var cell = document.createElement('div');
    cell.className = 'stat';
    var l = document.createElement('p');
    l.className = 'mono dim';
    l.textContent = label;
    var v = document.createElement('b');
    v.textContent = value;
    var n = document.createElement('small');
    n.textContent = note;
    cell.appendChild(l);
    cell.appendChild(v);
    cell.appendChild(n);
    box.appendChild(cell);
  }

  function showError(sel, message) {
    var el = $(sel);
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
    if (el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
  }

  function hideError(sel) {
    var el = $(sel);
    if (!el) return;
    el.hidden = true;
    el.textContent = '';
  }

  function closeDialog(id) {
    var dialog = $(id);
    if (!dialog) return;
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
  }

  function downloadText(name, text, mime) {
    var blob = new Blob([text], { type: (mime || 'text/plain') + ';charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
  }

  /* ---------- Оценки ---------- */
  function gradeEl(grade) {
    var el = document.createElement('span');
    if (grade === 'зачтено') {
      el.className = 'grade grade--pass';
      el.textContent = 'зачтено';
    } else if (!grade || grade === '—') {
      el.className = 'grade grade--none';
      el.textContent = '—';
    } else {
      el.className = 'grade grade--' + grade;
      el.textContent = grade;
    }
    return el;
  }

  function renderGrades() {
    var terms = PORTAL.recordBook.terms;
    if (!terms.length) return;
    var all = allItems();

    var meta = $('#gradesMeta');
    if (meta) meta.textContent = '№ ' + PORTAL.recordBook.number + ' · обновлено ' + PORTAL.recordBook.updated;

    var stats = $('#gradeStats');
    if (stats) {
      stats.innerHTML = '';
      addStat(stats, 'средний балл', fmtAvg(avgOf(all)), 'по числовым оценкам');
      addStat(stats, 'отлично', String(all.filter(function (i) { return i.grade === '5'; }).length), 'оценок «5»');
      addStat(stats, 'хорошо', String(all.filter(function (i) { return i.grade === '4'; }).length), 'оценок «4»');
      addStat(stats, 'зачтено', String(all.filter(function (i) { return i.grade === 'зачтено'; }).length), 'зачётов без оценки');
    }

    var tabs = $('#termTabs');
    if (tabs) {
      tabs.innerHTML = '';
      terms.forEach(function (t) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'sched-tab';
        btn.setAttribute('data-term', t.id);
        btn.setAttribute('aria-pressed', String(t.id === state.term));
        btn.textContent = t.label;
        tabs.appendChild(btn);
      });
    }

    var term = termById(state.term) || terms[0];
    var body = $('#gradesBody');
    if (body) {
      body.innerHTML = '';
      (term.items || []).forEach(function (it) {
        var tr = document.createElement('tr');
        var td1 = document.createElement('td');
        td1.textContent = it.subject;
        var td2 = document.createElement('td');
        td2.textContent = controlLabel(it.control);
        var td3 = document.createElement('td');
        td3.className = 'ta-r';
        td3.textContent = it.credits + ' ЗЕ';
        var td4 = document.createElement('td');
        td4.className = 'ta-r';
        td4.appendChild(gradeEl(it.grade));
        tr.appendChild(td1);
        tr.appendChild(td2);
        tr.appendChild(td3);
        tr.appendChild(td4);
        body.appendChild(tr);
      });
    }

    var foot = $('#gradesFoot');
    if (foot) {
      foot.innerHTML = '';
      var left = document.createElement('span');
      left.textContent = term.status === 'закрыт' ? 'семестр закрыт ' + term.closed : 'семестр идёт · ' + term.period;
      var right = document.createElement('span');
      var avg = avgOf(term.items || []);
      if (avg !== null) {
        right.appendChild(document.createTextNode('средний балл '));
        var b = document.createElement('b');
        b.textContent = fmtAvg(avg);
        right.appendChild(b);
      } else {
        right.textContent = 'числовых оценок пока нет';
      }
      right.appendChild(document.createTextNode(' · ' + sumCredits(term.items || []) + ' ЗЕ'));
      foot.appendChild(left);
      foot.appendChild(right);
    }

    var note = $('#gradesNote');
    if (note) {
      note.textContent = term.status === 'закрыт'
        ? 'Оценки перенесены из зачётной книжки. Если видите расхождение — закажите копию зачётной книжки в разделе «Справки».'
        : 'Ведомости обновляются по мере закрытия. Итоговые оценки появятся после экзаменационной сессии — до этого в списке стоит прочерк.';
    }

    renderGradeChart();
  }

  function renderGradeChart() {
    var box = $('#gradeChart');
    if (!box) return;
    box.innerHTML = '';
    PORTAL.recordBook.terms.forEach(function (t) {
      var avg = avgOf(t.items || []);
      var col = document.createElement('div');
      col.className = 'grade-col' + (t.id === state.term ? ' is-current' : '') + (avg === null ? ' is-empty' : '');

      var bar = document.createElement('div');
      bar.className = 'grade-col__bar';
      var pct = avg === null ? 4 : Math.max(8, Math.round((avg - 3.5) / 1.5 * 100));
      bar.style.height = pct + '%';
      col.appendChild(bar);

      var val = document.createElement('p');
      val.className = 'grade-col__val';
      val.textContent = fmtAvg(avg);
      col.appendChild(val);

      var label = document.createElement('p');
      label.className = 'grade-col__label';
      label.textContent = t.label + ' · ' + sumCredits(t.items || []) + ' ЗЕ';
      col.appendChild(label);

      box.appendChild(col);
    });
  }

  /* ---------- Задолженности ---------- */
  function renderDebts() {
    var open = PORTAL.debts.open || [];
    var badge = $('#debtBadge');
    if (badge) {
      badge.textContent = open.length ? open.length + ' открыто' : 'всё закрыто';
      badge.className = 'badge' + (open.length ? ' badge--accent' : ' badge--soft');
    }

    var box = $('#debtsOpen');
    if (box) {
      box.innerHTML = '';
      if (!open.length) {
        box.appendChild(emptyBlock(
          'Задолженностей нет',
          'Все экзамены и зачёты закрыты. Сессия 3 семестра начинается 12 января 2027 — расписание появится в разделе «Расписание».'
        ));
      } else {
        open.forEach(function (d) {
          var item = document.createElement('div');
          item.className = 'req-item';
          var main = document.createElement('div');
          var title = document.createElement('p');
          title.className = 'req-item__title';
          title.textContent = d.subject;
          var meta = document.createElement('p');
          meta.className = 'req-item__meta';
          meta.textContent = d.term + ' · ' + controlLabel(d.control) + (d.deadline ? ' · закрыть до ' + d.deadline : '');
          main.appendChild(title);
          main.appendChild(meta);
          item.appendChild(main);
          box.appendChild(item);
        });
      }
    }

    var body = $('#debtsHistory');
    if (body) {
      body.innerHTML = '';
      (PORTAL.debts.history || []).forEach(function (d) {
        var tr = document.createElement('tr');
        var td1 = document.createElement('td');
        td1.textContent = d.subject;
        var sub = document.createElement('small');
        sub.className = 'cell-sub';
        sub.textContent = controlLabel(d.control) + (d.note ? ' · ' + d.note : '');
        td1.appendChild(sub);
        var td2 = document.createElement('td');
        td2.textContent = d.term;
        var td3 = document.createElement('td');
        td3.textContent = d.closed;
        var td4 = document.createElement('td');
        td4.className = 'ta-r';
        td4.appendChild(gradeEl(d.grade));
        tr.appendChild(td1);
        tr.appendChild(td2);
        tr.appendChild(td3);
        tr.appendChild(td4);
        body.appendChild(tr);
      });
    }

    var rules = $('#debtsRules');
    if (rules) rules.textContent = PORTAL.debts.rules || '';
  }

  /* ---------- Учебный план ---------- */
  function planItemsFor(sem) {
    if (sem.items && sem.items.length) return sem.items;
    var term = termById(sem.id);
    return term && term.items ? term.items : [];
  }

  function planDoneCredits() {
    var done = 0;
    PORTAL.recordBook.terms.forEach(function (t) {
      (t.items || []).forEach(function (i) {
        if (i.grade !== '—') done += i.credits || 0;
      });
    });
    return done;
  }

  function renderPlan() {
    var box = $('#planList');
    if (!box) return;
    var total = PORTAL.curriculum.totalCredits || 240;
    var done = planDoneCredits();
    var pct = total ? Math.round(done / total * 100) : 0;

    var percent = $('#planPercent');
    if (percent) percent.textContent = String(pct);
    var credits = $('#planCredits');
    if (credits) credits.textContent = done + ' из ' + total + ' ЗЕ';
    var bar = $('#planBar');
    if (bar) bar.style.width = pct + '%';

    var meta = $('#planMeta');
    if (meta) meta.textContent = '09.03.02 · ' + state.profile.course + ' курс · 2026/27';

    var facts = $('#planFacts');
    if (facts) {
      facts.innerHTML = '';
      [
        ['освоено', done + ' ЗЕ'],
        ['осталось', Math.max(0, total - done) + ' ЗЕ'],
        ['семестров пройдено', '2 из 8'],
        ['текущий семестр', '24 ЗЕ']
      ].forEach(function (pair) {
        var span = document.createElement('span');
        span.appendChild(document.createTextNode(pair[0] + ' '));
        var b = document.createElement('b');
        b.textContent = pair[1];
        span.appendChild(b);
        facts.appendChild(span);
      });
    }

    box.innerHTML = '';
    (PORTAL.curriculum.semesters || []).forEach(function (sem) {
      var items = planItemsFor(sem);
      var details = document.createElement('details');
      details.className = 'plan-block';
      if (sem.status === 'текущий') details.open = true;

      var summary = document.createElement('summary');
      var name = document.createElement('span');
      name.className = 'plan-block__name';
      name.textContent = sem.label;
      var small = document.createElement('small');
      small.textContent = sem.year + (sem.status ? ' · ' + sem.status : '');
      name.appendChild(small);
      var badge = document.createElement('span');
      badge.className = 'badge' + (sem.status === 'текущий' ? ' badge--accent' : '');
      badge.textContent = sem.status || 'план';
      var creditBox = document.createElement('span');
      creditBox.className = 'plan-block__credits';
      creditBox.textContent = sem.credits + ' ЗЕ';
      summary.appendChild(name);
      summary.appendChild(badge);
      summary.appendChild(creditBox);
      details.appendChild(summary);

      var body = document.createElement('div');
      body.className = 'plan-block__body';
      if (items.length) {
        var head = document.createElement('div');
        head.className = 'plan-row plan-row--head';
        ['дисциплина', 'часы', 'ЗЕ', 'контроль'].forEach(function (text) {
          var cell = document.createElement('span');
          cell.textContent = text;
          head.appendChild(cell);
        });
        body.appendChild(head);
        items.forEach(function (it) {
          var row = document.createElement('div');
          row.className = 'plan-row';
          var subject = document.createElement('span');
          subject.textContent = it.subject;
          var hours = document.createElement('span');
          hours.className = 'plan-row__hours';
          hours.textContent = (it.credits * 36) + ' ч';
          var cred = document.createElement('span');
          cred.className = 'plan-row__credits';
          cred.textContent = it.credits + ' ЗЕ';
          var control = document.createElement('span');
          control.className = 'plan-row__control';
          control.textContent = controlLabel(it.control);
          row.appendChild(subject);
          row.appendChild(hours);
          row.appendChild(cred);
          row.appendChild(control);
          body.appendChild(row);
        });
      } else {
        var comment = document.createElement('p');
        comment.className = 'plan-block__comment';
        comment.textContent = sem.summary || 'Дисциплины появятся позже.';
        body.appendChild(comment);
      }
      details.appendChild(body);
      box.appendChild(details);
    });

    var note = $('#planNote');
    if (note) {
      note.textContent = (PORTAL.curriculum.practice || '') + ' Демо-план: часы посчитаны как 36 ч на зачётную единицу, состав дисциплин — учебный макет.';
    }
  }

  /* ---------- Справки и заявления ---------- */
  function renderRequests() {
    var list = $('#reqList');
    if (!list) return;
    list.innerHTML = '';
    var items = state.requests.slice().sort(function (a, b) {
      return dateKey(b.created).localeCompare(dateKey(a.created));
    });

    if (!items.length) {
      list.appendChild(emptyBlock(
        'Заявок пока нет',
        'Закажите справку — она появится здесь со статусом «в работе», а готовая копия будет доступна для скачивания.'
      ));
    }

    items.forEach(function (req) {
      var type = requestType(req.type);
      var item = document.createElement('div');
      item.className = 'req-item';
      var main = document.createElement('div');

      var top = document.createElement('div');
      top.className = 'req-item__top';
      var num = document.createElement('span');
      num.className = 'req-item__num';
      num.textContent = req.id;
      var title = document.createElement('span');
      title.className = 'req-item__title';
      title.textContent = type.label;
      top.appendChild(num);
      top.appendChild(title);
      main.appendChild(top);

      var meta = document.createElement('p');
      meta.className = 'req-item__meta';
      meta.textContent = 'создана ' + req.created + ' · ' + req.delivery + ' · ' + req.purpose;
      main.appendChild(meta);

      var statusNote = document.createElement('p');
      statusNote.className = 'req-item__meta';
      if (req.status === 'ready') statusNote.textContent = 'Готова ' + req.ready + '. Электронная копия доступна для скачивания.';
      else if (req.status === 'work') statusNote.textContent = 'Срок изготовления — ' + (type.term || '3 рабочих дня') + '.';
      else if (req.status === 'done') statusNote.textContent = 'Получена ' + req.ready + '. Копию можно скачать повторно.';
      else if (req.status === 'canceled') statusNote.textContent = 'Заявка отменена.';
      if (statusNote.textContent) main.appendChild(statusNote);

      var side = document.createElement('div');
      side.className = 'req-item__side';
      var status = document.createElement('span');
      status.className = 'req-status req-status--' + (STATUS_CLASS[req.status] || 'work');
      status.textContent = STATUS_LABEL[req.status] || req.status;
      side.appendChild(status);

      var actions = document.createElement('div');
      actions.className = 'req-item__actions';
      if (req.status === 'ready' || req.status === 'done') {
        var dl = document.createElement('button');
        dl.type = 'button';
        dl.className = 'btn btn--ghost btn--sm';
        dl.setAttribute('data-download', req.id);
        dl.textContent = 'Скачать';
        actions.appendChild(dl);
      }
      if (req.status === 'work') {
        var cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'btn btn--ghost btn--sm';
        cancel.setAttribute('data-cancel', req.id);
        cancel.textContent = 'Отменить';
        actions.appendChild(cancel);
      }
      if (actions.children.length) side.appendChild(actions);

      item.appendChild(main);
      item.appendChild(side);
      list.appendChild(item);
    });

    renderRequestCatalog();
  }

  function renderRequestCatalog() {
    var box = $('#reqCatalog');
    if (!box) return;
    box.innerHTML = '';
    PORTAL.requestTypes.forEach(function (t) {
      var card = document.createElement('div');
      card.className = 'req-card';
      var h = document.createElement('h3');
      h.textContent = t.label;
      var p = document.createElement('p');
      p.textContent = t.note;
      var foot = document.createElement('div');
      foot.className = 'req-card__foot';
      var term = document.createElement('span');
      term.className = 'req-card__term';
      term.textContent = t.term;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'link-btn';
      btn.setAttribute('data-type', t.id);
      btn.textContent = 'Заказать';
      foot.appendChild(term);
      foot.appendChild(btn);
      card.appendChild(h);
      card.appendChild(p);
      card.appendChild(foot);
      box.appendChild(card);
    });
  }

  function fillRequestSelect() {
    var sel = $('#fRequestType');
    if (!sel) return;
    sel.innerHTML = '';
    PORTAL.requestTypes.forEach(function (t) {
      var o = document.createElement('option');
      o.value = t.id;
      o.textContent = t.label + ' · ' + t.term;
      sel.appendChild(o);
    });
  }

  function openRequestDialog(typeId) {
    fillRequestSelect();
    var sel = $('#fRequestType');
    if (sel && typeId) sel.value = typeId;
    $('#fRequestPurpose').value = '';
    $('#fRequestComment').value = '';
    $('#fDelivery').value = 'электронно';
    hideError('#requestError');
    var dialog = $('#requestDialog');
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
      window.requestAnimationFrame(function () { $('#fRequestPurpose').focus(); });
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function nextRequestId() {
    var max = 1000;
    state.requests.forEach(function (r) {
      var m = /(\d{3,})$/.exec(r.id || '');
      if (m) max = Math.max(max, Number(m[1]));
    });
    return 'SP-2026-' + (max + 1);
  }

  function submitRequest(event) {
    event.preventDefault();
    var typeId = $('#fRequestType').value;
    var purpose = $('#fRequestPurpose').value.trim().replace(/\s+/g, ' ');
    var delivery = $('#fDelivery').value;
    var comment = $('#fRequestComment').value.trim();

    if (!PORTAL.requestTypes.some(function (t) { return t.id === typeId; })) {
      showError('#requestError', 'Выберите документ из списка.');
      return;
    }
    if (purpose.length < 3) {
      showError('#requestError', 'Напишите, для чего нужна справка.');
      $('#fRequestPurpose').focus();
      return;
    }

    state.requests.unshift({
      id: nextRequestId(),
      type: typeId,
      purpose: purpose + (comment ? ' · ' + comment : ''),
      created: todayShort(),
      status: 'work',
      ready: '',
      delivery: delivery
    });
    save();
    renderRequests();
    updateQuick();
    closeDialog('#requestDialog');
    toast('Заявка отправлена в деканат — демо');
  }

  function cancelRequest(id) {
    var req = state.requests.filter(function (r) { return r.id === id; })[0];
    if (!req || req.status !== 'work') return;
    req.status = 'canceled';
    save();
    renderRequests();
    updateQuick();
    toast('Заявка ' + id + ' отменена');
  }

  function downloadRequest(id) {
    var req = state.requests.filter(function (r) { return r.id === id; })[0];
    if (!req) return;
    var type = requestType(req.type);
    var p = state.profile;
    var lines = [
      'БГИТУ · учебный макет личного кабинета',
      '',
      'СПРАВКА ' + req.id,
      'Документ: ' + type.label,
      '',
      'Выдана: ' + p.fullName,
      'Группа: ' + p.group + ', ' + p.course + ' курс',
      'Направление: ' + p.program,
      'Форма обучения: ' + p.form + ', ' + p.basis.toLowerCase() + ' основа',
      '',
      'Цель: ' + req.purpose,
      'Способ получения: ' + req.delivery,
      'Дата заявки: ' + req.created,
      'Статус: ' + (STATUS_LABEL[req.status] || req.status),
      req.ready ? 'Готова: ' + req.ready : '',
      '',
      'Демонстрационный документ. Не является официальным документом университета.',
      'Сформирован: ' + todayShort()
    ].filter(function (line) { return line !== ''; });

    downloadText('spravka-' + req.id + '.txt', lines.join('\r\n'), 'text/plain');
    toast('Справка ' + req.id + ' скачана (демо)');
  }

  /* ---------- Портфолио ---------- */
  function renderPortfolio() {
    var grid = $('#pfGrid');
    if (!grid) return;
    var items = state.portfolio.slice().sort(function (a, b) {
      return dateKey(b.date).localeCompare(dateKey(a.date));
    });
    var confirmed = items.filter(function (p) { return p.status === 'confirmed'; }).length;
    var review = items.length - confirmed;

    var stats = $('#pfStats');
    if (stats) {
      stats.innerHTML = '';
      var all = document.createElement('span');
      all.className = 'badge';
      all.textContent = 'всего ' + items.length;
      var ok = document.createElement('span');
      ok.className = 'badge';
      ok.textContent = 'подтверждено ' + confirmed;
      var wait = document.createElement('span');
      wait.className = 'badge' + (review ? ' badge--accent' : '');
      wait.textContent = 'на проверке ' + review;
      stats.appendChild(all);
      stats.appendChild(ok);
      stats.appendChild(wait);
    }

    grid.innerHTML = '';
    if (!items.length) {
      grid.appendChild(emptyBlock(
        'Портфолио пустое',
        'Добавьте первое достижение: олимпиаду, публикацию, спортивный разряд или волонтёрский проект.'
      ));
    }

    items.forEach(function (p) {
      var card = document.createElement('article');
      card.className = 'pf-card';
      var top = document.createElement('div');
      top.className = 'pf-card__top';
      var cat = document.createElement('span');
      cat.className = 'badge';
      cat.textContent = categoryById(p.category).label;
      var lvl = document.createElement('span');
      lvl.className = 'mono dim';
      lvl.textContent = levelById(p.level).label;
      top.appendChild(cat);
      top.appendChild(lvl);

      var title = document.createElement('h3');
      title.className = 'pf-card__title';
      title.textContent = p.title;
      card.appendChild(top);
      card.appendChild(title);

      if (p.note) {
        var note = document.createElement('p');
        note.className = 'pf-card__note';
        note.textContent = p.note;
        card.appendChild(note);
      }

      var foot = document.createElement('div');
      foot.className = 'pf-card__foot';
      var date = document.createElement('span');
      date.textContent = p.date ? shortDate(p.date) : 'без даты';
      var status = document.createElement('span');
      status.className = 'pf-card__status' + (p.status === 'review' ? ' pf-card__status--review' : '');
      status.textContent = p.status === 'confirmed' ? 'подтверждено' : 'на проверке';
      foot.appendChild(date);
      foot.appendChild(status);
      card.appendChild(foot);
      grid.appendChild(card);
    });

    var note = $('#pfNote');
    if (note) {
      note.textContent = 'Демо: достижения хранятся в этом браузере. В рабочем кабинете запись уходит на проверку в деканат, а подтверждённые попадают в выписку для стипендиальной комиссии.';
    }
  }

  function fillPortfolioSelects() {
    var cat = $('#fPfCategory');
    var lvl = $('#fPfLevel');
    if (!cat || !lvl) return;
    cat.innerHTML = '';
    PORTAL.portfolioCategories.forEach(function (c) {
      var o = document.createElement('option');
      o.value = c.id;
      o.textContent = c.label;
      cat.appendChild(o);
    });
    lvl.innerHTML = '';
    PORTAL.portfolioLevels.forEach(function (l) {
      var o = document.createElement('option');
      o.value = l.id;
      o.textContent = l.label;
      lvl.appendChild(o);
    });
  }

  function openPortfolioDialog() {
    fillPortfolioSelects();
    $('#fPfTitle').value = '';
    $('#fPfNote').value = '';
    $('#fPfDate').value = todayISO();
    hideError('#pfError');
    var dialog = $('#portfolioDialog');
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
      window.requestAnimationFrame(function () { $('#fPfTitle').focus(); });
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function submitPortfolio(event) {
    event.preventDefault();
    var title = $('#fPfTitle').value.trim().replace(/\s+/g, ' ');
    var category = $('#fPfCategory').value;
    var level = $('#fPfLevel').value;
    var date = $('#fPfDate').value || todayISO();
    var note = $('#fPfNote').value.trim();

    if (title.length < 3) {
      showError('#pfError', 'Напишите название достижения — хотя бы три символа.');
      $('#fPfTitle').focus();
      return;
    }
    if (!PORTAL.portfolioCategories.some(function (c) { return c.id === category; })) {
      showError('#pfError', 'Выберите категорию.');
      return;
    }

    state.portfolio.push({
      id: 'p' + Date.now(),
      title: title,
      category: category,
      level: level,
      date: date,
      status: 'review',
      note: note
    });
    save();
    renderPortfolio();
    updateQuick();
    closeDialog('#portfolioDialog');
    toast('Достижение добавлено — ждёт проверки');
  }

  /* ---------- Почта ---------- */
  function isUnread(mail) {
    return Boolean(mail.unread) && !state.mailRead[mail.id];
  }

  function unreadCount() {
    return PORTAL.mail.filter(isUnread).length;
  }

  function renderMail() {
    var list = $('#mailList');
    var reader = $('#mailRead');
    if (!list || !reader) return;
    var mails = PORTAL.mail.slice();
    var selected = state.mailSelected;
    if (!selected || !mails.some(function (m) { return m.id === selected; })) {
      var first = mails.filter(isUnread)[0] || mails[0];
      selected = first ? first.id : null;
      state.mailSelected = selected;
    }

    list.innerHTML = '';
    mails.forEach(function (mail) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'mail-item' + (isUnread(mail) ? ' is-unread' : '') + (mail.id === selected ? ' is-active' : '');
      btn.setAttribute('data-mail', mail.id);

      var top = document.createElement('span');
      top.className = 'mail-item__top';
      var from = document.createElement('span');
      from.className = 'mail-item__from';
      from.textContent = mail.from;
      var date = document.createElement('span');
      date.className = 'mail-item__date';
      date.textContent = mailDate(mail.date);
      top.appendChild(from);
      top.appendChild(date);

      var subject = document.createElement('span');
      subject.className = 'mail-item__subj';
      subject.textContent = mail.subject;

      btn.appendChild(top);
      btn.appendChild(subject);
      list.appendChild(btn);
    });

    reader.innerHTML = '';
    var mail = mails.filter(function (m) { return m.id === selected; })[0];
    if (!mail) {
      var empty = document.createElement('div');
      empty.className = 'mail-empty';
      var eb = document.createElement('b');
      eb.textContent = 'Писем нет';
      var ep = document.createElement('p');
      ep.textContent = 'Здесь появятся письма деканата и преподавателей.';
      empty.appendChild(eb);
      empty.appendChild(ep);
      reader.appendChild(empty);
    } else {
      var head = document.createElement('div');
      head.className = 'mail-read__head';
      var subject = document.createElement('h3');
      subject.className = 'mail-read__subject';
      subject.textContent = mail.subject;
      var meta = document.createElement('p');
      meta.className = 'mail-read__meta';
      meta.textContent = mail.from + ' · ' + mailFullDate(mail.date);
      head.appendChild(subject);
      head.appendChild(meta);
      reader.appendChild(head);

      var body = document.createElement('div');
      body.className = 'mail-read__body';
      (mail.body || []).forEach(function (text) {
        var p = document.createElement('p');
        p.textContent = text;
        body.appendChild(p);
      });
      reader.appendChild(body);

      if (mail.attachments && mail.attachments.length) {
        var attach = document.createElement('div');
        attach.className = 'mail-attach';
        mail.attachments.forEach(function (name) {
          var b = document.createElement('button');
          b.type = 'button';
          b.className = 'btn btn--ghost btn--sm';
          b.setAttribute('data-attach', name);
          b.textContent = name;
          attach.appendChild(b);
        });
        reader.appendChild(attach);
      }
    }

    var unread = unreadCount();
    var metaBox = $('#mailMeta');
    if (metaBox) metaBox.textContent = unread ? 'входящие · ' + unread + ' новых' : 'входящие · все прочитаны';
    var badge = $('#navMailCount');
    if (badge) {
      badge.textContent = String(unread);
      badge.hidden = unread === 0;
    }
    var bell = $('#bellBtn');
    if (bell) {
      bell.classList.toggle('icon-btn--dot', unread > 0);
      bell.setAttribute('aria-label', unread ? 'Уведомления: ' + unread + ' новых' : 'Уведомления');
    }
  }

  function openMail(id) {
    if (!PORTAL.mail.some(function (m) { return m.id === id; })) return;
    state.mailSelected = id;
    state.mailRead[id] = true;
    save();
    renderMail();
  }

  /* ---------- Сводка для обзора ---------- */
  function updateQuick() {
    var avg = $('#quickAvg');
    if (avg) avg.textContent = fmtAvg(avgOf(allItems()));
    var debts = $('#quickDebts');
    if (debts) debts.textContent = String((PORTAL.debts.open || []).length);
    var plan = $('#quickPlan');
    if (plan) {
      var total = PORTAL.curriculum.totalCredits || 240;
      plan.textContent = (total ? Math.round(planDoneCredits() / total * 100) : 0) + '%';
    }
    var reqs = $('#quickRequests');
    if (reqs) reqs.textContent = String(state.requests.filter(function (r) {
      return r.status === 'work' || r.status === 'ready';
    }).length);
    var portfolio = $('#quickPortfolio');
    if (portfolio) portfolio.textContent = String(state.portfolio.length);
  }

  /* ---------- Роутер разделов ---------- */
  function currentRoute() {
    var hash = (window.location.hash || '').replace(/^#/, '');
    if (hash === 'profile' || hash === 'stipend' || hash === 'schedule') {
      return { view: 'overview', anchor: hash };
    }
    if (VIEW_META[hash]) return { view: hash, anchor: '' };
    return { view: 'overview', anchor: '' };
  }

  function showView(name, anchor, instant) {
    var view = VIEW_META[name] ? name : 'overview';
    var meta = VIEW_META[view];
    state.view = view;
    document.body.classList.toggle('is-subview', view !== 'overview');

    $$('[data-view-panel]').forEach(function (panel) {
      panel.hidden = panel.getAttribute('data-view-panel') !== view;
    });

    var title = $('#cabTitle');
    if (title) title.innerHTML = meta.title;
    var lead = $('#heroLead');
    if (lead) lead.textContent = meta.lead;
    var badge = $('#heroBadge');
    if (badge) badge.textContent = meta.badge;
    var crumb = $('#crumbCurrent');
    if (crumb) crumb.textContent = meta.crumb;
    document.title = meta.doc;

    $$('.cab-nav a[data-view]').forEach(function (link) {
      var sameView = link.getAttribute('data-view') === view;
      var linkAnchor = link.getAttribute('data-anchor') || '';
      var isCurrent = sameView && (anchor ? linkAnchor === anchor : !linkAnchor);
      if (isCurrent) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });

    if (view !== 'overview') {
      $$('#view-' + view + ' [data-reveal]').forEach(function (el) { el.classList.add('is-in'); });
    }

    if (view === 'mail' && state.mailSelected && !state.mailRead[state.mailSelected]) {
      state.mailRead[state.mailSelected] = true;
      save();
      renderMail();
    }

    if (anchor) {
      var target = document.getElementById(anchor);
      if (target) {
        var revealBox = target.closest('[data-reveal]');
        if (revealBox) revealBox.classList.add('is-in');
        window.setTimeout(function () {
          try { target.scrollIntoView({ block: 'start', behavior: instant ? 'auto' : 'smooth' }); }
          catch (err) { target.scrollIntoView(); }
        }, instant ? 0 : 60);
      }
    } else if (!instant) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  function initRouter() {
    var route = currentRoute();
    showView(route.view, route.anchor, true);
    window.addEventListener('hashchange', function () {
      var next = currentRoute();
      showView(next.view, next.anchor, false);
    });
  }

  /* ---------- Общие рендеры ---------- */
  function renderAll() {
    renderProfile();
    applyRole();
    renderStipend();
    renderSchedule();
    renderTasks();
    renderGrades();
    renderDebts();
    renderPlan();
    renderRequests();
    renderPortfolio();
    renderMail();
    updateQuick();
    updateStorageNote();
  }

  /* ---------- События ---------- */
  function bindEvents() {
    $('#editProfileBtn').addEventListener('click', openProfileDialog);
    $('#headAvatar').addEventListener('click', openProfileDialog);
    $('#closeDialog').addEventListener('click', closeProfileDialog);
    $('#cancelDialog').addEventListener('click', closeProfileDialog);
    $('#profileForm').addEventListener('submit', submitProfile);

    $('#profileDialog').addEventListener('click', function (e) {
      if (e.target === e.currentTarget) closeProfileDialog();
    });

    $('#fRole').addEventListener('change', function () {
      var role = roleById($('#fRole').value);
      if (role) $('#roleHint').textContent = role.note;
    });

    $('#fGroup').addEventListener('change', function () {
      var group = DATA.groups.filter(function (g) { return g.id === $('#fGroup').value; })[0];
      if (group) $('#fCourse').value = String(group.course);
    });

    $('#acadBoost').addEventListener('change', function () {
      state.stipend.boost = $('#acadBoost').checked;
      renderStipend();
      save();
    });
    $('#socialPay').addEventListener('change', function () {
      state.stipend.social = $('#socialPay').checked;
      renderStipend();
      save();
    });
    $('#pgasSelect').addEventListener('change', function () {
      state.stipend.pgas = $('#pgasSelect').value;
      renderStipend();
      save();
    });

    $('#groupSelect').addEventListener('change', function () {
      state.group = $('#groupSelect').value;
      renderSchedule();
      save();
    });

    $$('.sched-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        state.week = Number(btn.getAttribute('data-week')) || 0;
        renderSchedule();
      });
    });

    $('#icsBtn').addEventListener('click', downloadICS);

    var burger = $('#burger');
    var menu = $('#mobileMenu');
    function setMenu(open) {
      burger.setAttribute('aria-expanded', String(open));
      menu.classList.toggle('is-open', open);
      menu.setAttribute('aria-hidden', String(!open));
      document.body.classList.toggle('menu-open', open);
    }
    burger.addEventListener('click', function () {
      setMenu(burger.getAttribute('aria-expanded') !== 'true');
    });
    menu.addEventListener('click', function (e) {
      if (e.target.closest('a')) setMenu(false);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && menu.classList.contains('is-open')) {
        setMenu(false);
        burger.focus();
      }
    });

    document.addEventListener('click', function (e) {
      var target = e.target.closest('[data-soon]');
      if (!target) return;
      e.preventDefault();
      var title = target.getAttribute('data-soon');
      toast(title ? title + ' — появится на следующем этапе' : 'Раздел появится на следующем этапе');
    });

    $$('.cab-nav a[data-view]').forEach(function (link) {
      link.addEventListener('click', function (e) {
        var view = link.getAttribute('data-view');
        var anchor = link.getAttribute('data-anchor') || '';
        var hash = '#' + (anchor || view);
        if (window.location.hash === hash) {
          e.preventDefault();
          showView(view, anchor, false);
        }
      });
    });

    var termTabs = $('#termTabs');
    if (termTabs) {
      termTabs.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-term]');
        if (!btn) return;
        state.term = btn.getAttribute('data-term');
        renderGrades();
      });
    }

    var reqList = $('#reqList');
    if (reqList) {
      reqList.addEventListener('click', function (e) {
        var dl = e.target.closest('[data-download]');
        if (dl) { downloadRequest(dl.getAttribute('data-download')); return; }
        var cancel = e.target.closest('[data-cancel]');
        if (cancel) cancelRequest(cancel.getAttribute('data-cancel'));
      });
    }

    var reqCatalog = $('#reqCatalog');
    if (reqCatalog) {
      reqCatalog.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-type]');
        if (btn) openRequestDialog(btn.getAttribute('data-type'));
      });
    }

    var newRequestBtn = $('#newRequestBtn');
    if (newRequestBtn) newRequestBtn.addEventListener('click', function () { openRequestDialog(); });
    $('#requestForm').addEventListener('submit', submitRequest);
    $('#closeRequestDialog').addEventListener('click', function () { closeDialog('#requestDialog'); });
    $('#cancelRequestDialog').addEventListener('click', function () { closeDialog('#requestDialog'); });
    $('#requestDialog').addEventListener('click', function (e) {
      if (e.target === e.currentTarget) closeDialog('#requestDialog');
    });

    var addPortfolioBtn = $('#addPortfolioBtn');
    if (addPortfolioBtn) addPortfolioBtn.addEventListener('click', openPortfolioDialog);
    $('#portfolioForm').addEventListener('submit', submitPortfolio);
    $('#closePortfolioDialog').addEventListener('click', function () { closeDialog('#portfolioDialog'); });
    $('#cancelPortfolioDialog').addEventListener('click', function () { closeDialog('#portfolioDialog'); });
    $('#portfolioDialog').addEventListener('click', function (e) {
      if (e.target === e.currentTarget) closeDialog('#portfolioDialog');
    });

    var mailList = $('#mailList');
    if (mailList) {
      mailList.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-mail]');
        if (btn) openMail(btn.getAttribute('data-mail'));
      });
    }

    var mailRead = $('#mailRead');
    if (mailRead) {
      mailRead.addEventListener('click', function (e) {
        var attach = e.target.closest('[data-attach]');
        if (attach) toast('Вложение «' + attach.getAttribute('data-attach') + '» — демо, файл не приложен');
      });
    }

    var head = $('#siteHead');
    var onScroll = function () { head.classList.toggle('is-stuck', window.scrollY > 24); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  function initReveal() {
    var els = $$('[data-reveal]');
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!('IntersectionObserver' in window) || reduce) {
      els.forEach(function (el) { el.classList.add('is-in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        io.unobserve(entry.target);
      });
    }, { threshold: 0.12 });
    els.forEach(function (el) { io.observe(el); });
  }

  function initDate() {
    var now = new Date();
    var label = new Intl.DateTimeFormat('ru-RU', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    }).format(now);
    $('#heroDate').textContent = label.charAt(0).toUpperCase() + label.slice(1);
    $('#year').textContent = now.getFullYear();
  }

  /* ---------- Старт ---------- */
  canStore = storageAvailable();
  load();
  fillSelects();
  initDate();
  bindEvents();
  renderAll();
  initReveal();
  initRouter();

  window.bgituCabinet = {
    buildICS: buildICS,
    getState: function () { return JSON.parse(JSON.stringify(state)); },
    goTo: function (view) { window.location.hash = '#' + view; }
  };
})();
