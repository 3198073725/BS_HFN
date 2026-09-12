import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ElButton,
  ElCard,
  ElContainer,
  ElDatePicker,
  ElDialog,
  ElDivider,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElHeader,
  ElInput,
  ElInputNumber,
  ElLoading,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElRadio,
  ElRadioButton,
  ElRadioGroup,
  ElResult,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTimeline,
  ElTimelineItem,
  provideGlobalConfig,
} from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'

import App from './App.vue'
import { SESSION_EXPIRED_EVENT } from './api/client'
import router from './router'
import { useAuthStore } from './stores/auth'
import './assets/main.css'
import './assets/learning.css'


const app = createApp(App)
provideGlobalConfig({ locale: zhCn }, app, true)
const components = [
  ElButton,
  ElCard,
  ElContainer,
  ElDatePicker,
  ElDialog,
  ElDivider,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElHeader,
  ElInput,
  ElInputNumber,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElRadio,
  ElRadioButton,
  ElRadioGroup,
  ElResult,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTimeline,
  ElTimelineItem,
]

components.forEach((component) => app.component(component.name, component))
app.use(ElLoading)
const pinia = createPinia()
app.use(pinia)
app.use(router)
function clearExpiredSession() {
  useAuthStore(pinia).clearSession()
  const current = router.currentRoute.value
  if (current.meta.requiresAuth && current.name !== 'login') {
    void router.replace({ name: 'login', query: { redirect: current.fullPath } })
  }
}

window.addEventListener(SESSION_EXPIRED_EVENT, clearExpiredSession)
window.addEventListener('storage', (event) => {
  if (
    (event.key === null || ['access_token', 'refresh_token'].includes(event.key))
    && !localStorage.getItem('access_token')
    && !localStorage.getItem('refresh_token')
  ) {
    clearExpiredSession()
  }
})
app.mount('#app')
