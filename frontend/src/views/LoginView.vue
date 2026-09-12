<script setup>
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'


const formRef = ref(null)
const submitting = ref(false)
const form = reactive({ account: '', password: '' })
const rules = {
  account: [{ required: true, message: '请输入用户名、邮箱、学号或工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入登录密码', trigger: 'blur' }],
}
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || submitting.value) return

  submitting.value = true
  try {
    await auth.login(form)
    ElMessage.success('登录成功，欢迎回来')
    await router.replace(String(route.query.redirect || '/'))
  } catch (error) {
    ElMessage.error(error.message || '登录失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-shell" aria-labelledby="login-title">
      <aside class="auth-showcase">
        <RouterLink class="auth-brand auth-brand-light" to="/" aria-label="返回课后辅导系统首页">
          <span class="brand-mark">辅</span>
          <span>
            <strong>课后辅导</strong>
            <small>BS_HFN LEARNING</small>
          </span>
        </RouterLink>

        <div class="showcase-content">
          <span class="showcase-badge">学生成长空间</span>
          <h2>把课堂之外的时间，<br />变成持续进步。</h2>
          <p>课程、章节与视频学习集中在一个清晰的空间，让每一次复习都更有方向。</p>
          <div class="showcase-points" aria-label="平台特点">
            <div><span>01</span><p><strong>课程有序</strong><small>按分类与章节快速定位内容</small></p></div>
            <div><span>02</span><p><strong>视频流畅</strong><small>FFmpeg 与 HLS 支持多端播放</small></p></div>
            <div><span>03</span><p><strong>进度清晰</strong><small>为后续学习闭环打好基础</small></p></div>
          </div>
        </div>
        <p class="showcase-footer">WEB · FFMPEG · HLS</p>
      </aside>

      <section class="auth-panel">
        <RouterLink class="auth-brand auth-mobile-brand" to="/">
          <span class="brand-mark">辅</span>
          <span><strong>课后辅导</strong><small>BS_HFN LEARNING</small></span>
        </RouterLink>
        <div class="auth-form-wrap">
          <p class="eyebrow">WELCOME BACK</p>
          <h1 id="login-title">欢迎回来</h1>
          <p class="auth-intro">登录后继续你的课程学习或教学管理。</p>

          <el-form
            ref="formRef"
            class="auth-form"
            :model="form"
            :rules="rules"
            label-position="top"
            @submit.prevent="submit"
          >
            <el-form-item label="账号" prop="account">
              <el-input
                v-model.trim="form.account"
                size="large"
                autocomplete="username"
                autofocus
                clearable
                placeholder="用户名、邮箱、学号或工号"
              />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="form.password"
                size="large"
                type="password"
                show-password
                autocomplete="current-password"
                placeholder="请输入登录密码"
              />
            </el-form-item>
            <el-button
              type="primary"
              native-type="submit"
              size="large"
              class="full-width auth-submit"
              :loading="submitting"
            >
              {{ submitting ? '正在登录' : '登录' }}
            </el-button>
          </el-form>

          <div class="auth-divider"><span>首次使用？</span></div>
          <p class="auth-secondary">
            还没有学生账号？
            <RouterLink to="/register">立即注册</RouterLink>
          </p>
          <RouterLink class="back-home-link" to="/">← 返回首页浏览公开课程</RouterLink>
        </div>
      </section>
    </section>
  </main>
</template>
