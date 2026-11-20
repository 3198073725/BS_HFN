import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'


const backendTarget = process.env.VITE_BACKEND_TARGET || 'http://127.0.0.1:5000'
// E:\BS_HFN 可能是指向实际项目目录的 Junction。显式使用配置文件
// 所在的真实目录，避免 Vite 的工作目录与 Rollup 入口位于不同盘符。
const projectRoot = fileURLToPath(new URL('.', import.meta.url))
// Vite 的开发依赖优化器仍会读取 process.cwd()；同步到真实目录可避免
// Junction 入口和真实目录分别生成依赖键，造成 depsInfo 缓存不一致。
process.chdir(projectRoot)


export default defineConfig({
  root: projectRoot,
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const moduleId = id.replaceAll('\\', '/')
          if (moduleId.includes('/node_modules/hls.js/')) return 'hls'
          if (moduleId.includes('/node_modules/zrender/')) return 'chart-renderer'
          if (moduleId.includes('/node_modules/echarts/')) return 'echarts'
          if (
            moduleId.includes('/node_modules/vue/') ||
            moduleId.includes('/node_modules/@vue/') ||
            moduleId.includes('/node_modules/vue-router/') ||
            moduleId.includes('/node_modules/pinia/')
          ) {
            return 'vue'
          }
          if (moduleId.includes('/node_modules/axios/')) return 'http'
          return undefined
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/media': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
})
