import { createRouter, createWebHistory } from 'vue-router'

const ChatView = () => import('@/modules/chat/views/ChatView.vue')

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: ChatView },
    { path: '/c/:id', name: 'conversation', component: ChatView, props: true },
  ],
})

export default router
