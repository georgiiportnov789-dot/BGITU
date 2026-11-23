from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role


class ThemeUITests(TestCase):
    """Переключатель тем (paper/surik/latun/brass) — как на основном сайте bgitu."""

    @classmethod
    def setUpTestData(cls):
        cls.role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        cls.user = get_user_model().objects.create_user('tstudent', password='demo12345')
        cls.user.profile.role = cls.role
        cls.user.profile.save()

    def test_login_page_has_theme_popover(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-theme="paper"')
        self.assertContains(response, 'id="theme-pop"')
        for name in ('paper', 'surik', 'latun', 'brass'):
            self.assertContains(response, f'data-theme-set="{name}"')
        self.assertContains(response, 'js/theme.js')

    def test_custom_select_component_included(self):
        """Кастомный дропдаун: скрипт компонента подключён на кабинете и в auth-формах."""
        self.client.force_login(self.user)
        schedule = self.client.get(reverse('schedule:schedule'))
        self.assertContains(schedule, 'js/select.js')
        self.client.logout()
        register = self.client.get(reverse('accounts:register'))
        self.assertContains(register, 'js/select.js')
        self.assertContains(register, 'class="input"')

    def test_footer_wordmark_and_fixed_icons(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertContains(response, 'class="footer__word"')
        self.assertContains(response, 'data-text="БГИТУ"')
        # иконки-заливки наследуют цвет текста (не чёрные на тёмных темах)
        self.assertContains(response, 'class="cab-nav__icon cab-nav__icon--overview" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">')

    def test_pages_have_bg_canvas(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertContains(response, 'class="bg-canvas"')
        self.assertContains(response, 'js/bg.js')
        from django.test import Client
        anon = Client()
        auth = anon.get(reverse('accounts:login'))
        self.assertContains(auth, 'class="bg-canvas"')
        self.assertContains(auth, 'js/bg.js')

    def test_dashboard_has_theme_button(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="theme-btn"')
        self.assertContains(response, 'popovertarget="theme-pop"')
        self.assertContains(response, 'id="theme-pop"')


class StubPagesTests(TestCase):
    """Заглушки новых разделов: доступны залогиненным, скрыты от анонимов."""

    def setUp(self):
        self.role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        self.user = get_user_model().objects.create_user('stubstudent', password='demo12345')
        self.user.profile.role = self.role
        self.user.profile.save()

    def test_stub_pages_render_for_user(self):
        self.client.force_login(self.user)
        for name, title in [('stipendia', 'Стипендия'), ('profile', 'Профиль')]:
            response = self.client.get(reverse(f'portal:{name}'))
            self.assertEqual(response.status_code, 200, name)
            self.assertContains(response, title)

    def test_stub_pages_redirect_anonymous(self):
        for name in ('stipendia', 'profile'):
            response = self.client.get(reverse(f'portal:{name}'))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn('/login/', response.url, name)


class NavCompositionTests(TestCase):
    """Состав левого навбара: 7 разделов, «Студенты» только с правом."""

    def setUp(self):
        self.student_role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        self.dev_role = Role.objects.create(code='developer', name='Разработчик', is_developer=True,
                                            can_manage_users=True, can_manage_roles=True,
                                            can_approve_roles=True, can_manage_schedule=True)
        self.student = get_user_model().objects.create_user('navstudent', password='demo12345')
        self.student.profile.role = self.student_role
        self.student.profile.save()
        self.dev = get_user_model().objects.create_user('navdev', password='demo12345')
        self.dev.profile.role = self.dev_role
        self.dev.profile.save()

    def test_developer_sees_all_sections(self):
        self.client.force_login(self.dev)
        response = self.client.get(reverse('portal:dashboard'))
        content = response.content.decode()
        for label in ('Обзор', 'Расписание', 'Стипендия', 'Курсы', 'Оценки', 'Роли', 'Профиль', 'Студенты'):
            self.assertContains(response, f'class="cab-nav__lbl">{label}</span>')

    def test_nav_items_are_buttons_with_toggle(self):
        """Пункты — кнопки с data-href (нет показа адреса при наведении),
        раскрытие рельса — кнопкой-стрелкой, у иконок свои классы."""
        self.client.force_login(self.dev)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertContains(response, 'class="cab-nav__item"')
        self.assertContains(response, 'data-href="/schedule/"')
        self.assertContains(response, 'id="cabToggle"')
        for cls in ('overview', 'schedule', 'stipendia', 'courses', 'grades', 'roles', 'profile'):
            self.assertContains(response, f'cab-nav__icon--{cls}')

    def test_nav_is_flat_single_list(self):
        """Единый список без подзаголовка «управление» и разделителей;
        одна вкладка на раздел — без отдельных ссылок заявок/создания/импорта."""
        self.client.force_login(self.dev)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertNotContains(response, 'cab-nav__label')
        self.assertNotContains(response, 'cab-nav__sep')
        for removed in ('>Заявки на роли</a>', '>Создать роль</a>', '>Импорт расписания</a>', '>ЭОС</a>'):
            self.assertNotContains(response, removed)

    def test_top_nav_has_main_site_links(self):
        """Верхний навбар ведёт на внутренние страницы сайта, а не на GitHub."""
        self.client.force_login(self.dev)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertContains(response, 'class="nav"')
        for name, label in [
            ('university', 'Университет'),
            ('admission', 'Поступающим'),
            ('student', 'Студенту'),
            ('science', 'Наука'),
            ('news', 'Новости'),
            ('contacts', 'Контакты'),
        ]:
            self.assertContains(response, reverse(f'site:{name}'))
            self.assertContains(response, label)
        self.assertNotContains(response, 'github.io')

    def test_top_nav_has_no_role_and_no_fio(self):
        """В верхнем навбаре нет роли и ФИО — только поиск, тема, выход."""
        self.client.force_login(self.dev)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertNotContains(response, 'badge badge--soft')
        self.assertNotContains(response, 'class="head-user"')
        self.assertContains(response, 'data-search-open')
        # ФИО и роль видны в ящике (cab-nav__user)
        self.assertContains(response, 'cab-nav__user')

    def test_all_sections_are_wip(self):
        """Все разделы в режиме «в разработке»."""
        self.client.force_login(self.dev)
        for url in ('/cabinet/', '/cabinet/grades/', '/courses/', '/works/',
                    '/roles/', '/cabinet/stipendia/', '/cabinet/profile/', '/manage/students/'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertContains(response, 'Раздел в разработке')

    def test_student_does_not_see_students_link(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('portal:dashboard'))
        content = response.content.decode()
        self.assertNotIn('>Студенты</a>', content)
        for label in ('Обзор', 'Расписание', 'Стипендия', 'Курсы', 'Оценки', 'Роли', 'Профиль'):
            self.assertIn(f'class="cab-nav__lbl">{label}</span>', content)
