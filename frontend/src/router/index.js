import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'


const DefaultLayout = () => import('../layouts/DefaultLayout.vue')
const CourseDetailView = () => import('../views/CourseDetailView.vue')
const CourseListView = () => import('../views/CourseListView.vue')
const HomeView = () => import('../views/HomeView.vue')
const LoginView = () => import('../views/LoginView.vue')
const NotFoundView = () => import('../views/NotFoundView.vue')
const RegisterView = () => import('../views/RegisterView.vue')
const TeacherCoursesView = () => import('../views/TeacherCoursesView.vue')


const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/register', name: 'register', component: RegisterView },
    {
      path: '/',
      component: DefaultLayout,
      children: [
        { path: '', name: 'home', component: HomeView },
        { path: 'courses', name: 'courses', component: CourseListView },
        { path: 'courses/:id', name: 'course-detail', component: CourseDetailView },
        {
          path: 'teacher/courses',
          name: 'teacher-courses',
          component: TeacherCoursesView,
          meta: { requiresAuth: true, roles: ['TEACHER'] },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundView },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (auth.isAuthenticated && !auth.user) {
    try {
      await auth.restoreUser()
    } catch {
      if (to.meta.requiresAuth) return { name: 'login', query: { redirect: to.fullPath } }
    }
  }
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.roles && !to.meta.roles.includes(auth.user?.role)) {
    return { name: 'home' }
  }
  if ((to.name === 'login' || to.name === 'register') && auth.isAuthenticated) {
    return { name: 'home' }
  }
  return true
})

export default router
