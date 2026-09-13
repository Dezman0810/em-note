import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { guest: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterView.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      name: 'notes',
      component: () => import('../views/NotesView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/notes/:id',
      name: 'note',
      component: () => import('../views/NotesView.vue'),
      meta: { requiresAuth: true },
      beforeEnter: (to) => {
        const id = to.params.id as string
        if (
          !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
        ) {
          return { name: 'notes' }
        }
      },
    },
    {
      path: '/tags',
      name: 'tags',
      component: () => import('../views/TagsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/habits',
      name: 'habits',
      component: () => import('../views/HabitsView.vue'),
      meta: { requiresAuth: true, requiresHabits: true },
    },
    {
      path: '/budget',
      name: 'budget',
      component: () => import('../views/BudgetView.vue'),
      meta: { requiresAuth: true, requiresBudget: true },
    },
    {
      path: '/schemas',
      name: 'schemas',
      component: () => import('../views/SchemasView.vue'),
      meta: { requiresAuth: true, requiresSchemas: true },
    },
    {
      path: '/schemas/note/:noteId',
      name: 'schema-note',
      component: () => import('../views/SchemasView.vue'),
      meta: { requiresAuth: true, requiresSchemas: true },
      beforeEnter: (to) => {
        const id = String(to.params.noteId || '')
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
          return { name: 'schemas' }
        }
      },
    },
    {
      path: '/schemas/:noteId/:index',
      name: 'schema-edit',
      component: () => import('../views/SchemasView.vue'),
      meta: { requiresAuth: true, requiresSchemas: true },
      beforeEnter: (to) => {
        const id = String(to.params.noteId || '')
        const index = Number(to.params.index)
        if (
          !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) ||
          !Number.isInteger(index) ||
          index < 0
        ) {
          return { name: 'schemas' }
        }
      },
    },
    {
      path: '/mindmaps',
      name: 'mindmaps',
      component: () => import('../views/MapsView.vue'),
      meta: { requiresAuth: true, requiresSchemas: true },
    },
    {
      path: '/mindmaps/note/:noteId',
      name: 'mindmap-note',
      component: () => import('../views/MapsView.vue'),
      meta: { requiresAuth: true, requiresSchemas: true },
      beforeEnter: (to) => {
        const id = String(to.params.noteId || '')
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
          return { name: 'mindmaps' }
        }
      },
    },
    {
      path: '/mindmaps/:noteId/:index',
      name: 'mindmap-edit',
      component: () => import('../views/MapsView.vue'),
      meta: { requiresAuth: true, requiresSchemas: true },
      beforeEnter: (to) => {
        const id = String(to.params.noteId || '')
        const index = Number(to.params.index)
        if (
          !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) ||
          !Number.isInteger(index) ||
          index < 0
        ) {
          return { name: 'mindmaps' }
        }
      },
    },
    {
      path: '/h/:token',
      name: 'public-habits',
      component: () => import('../views/HabitsView.vue'),
      beforeEnter: (to) => {
        const t = String(to.params.token || '').trim()
        if (!t) return { path: '/' }
        return true
      },
    },
    {
      path: '/p/:token',
      name: 'public-note',
      component: () => import('../views/PublicNoteView.vue'),
      beforeEnter: (to) => {
        const t = String(to.params.token || '').trim()
        if (!t) return { path: '/' }
        return true
      },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) await auth.fetchMe()

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.guest && auth.isAuthenticated) {
    return { name: 'notes' }
  }
  if (to.meta.requiresHabits && !auth.user?.can_use_habits) {
    return { name: 'notes' }
  }
  if (to.meta.requiresBudget && !auth.user?.can_use_budget) {
    return { name: 'notes' }
  }
  if (to.meta.requiresSchemas && !auth.user?.can_use_schemas) {
    return { name: 'notes' }
  }
  return true
})

export default router
