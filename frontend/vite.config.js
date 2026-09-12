import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'


export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const moduleId = id.replaceAll('\\', '/')
          if (moduleId.includes('/node_modules/hls.js/')) return 'hls'
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
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})
