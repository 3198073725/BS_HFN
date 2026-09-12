<script setup>
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'


const formRef = ref(null)
const submitting = ref(false)
const form = reactive({
  username: '',
  password: '',
  real_name: '',
  student_no: '',
  email: '',
  phone: '',
})
const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_\u4e00-\u9fff]{3,50}$/,
      message: '用户名需为 3–50 位中文、字母、数字或下划线',
      trigger: 'blur',
    },
  ],
  real_name: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' },
    { max: 50, message: '真实姓名不能超过 50 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请设置登录密码', trigger: 'blur' },
    { min: 8, max: 72, message: '密码长度需为 8–72 位', trigger: 'blur' },
  ],
  email: [{ type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' }],
  phone: [{ pattern: /^1[3-9]\d{9}$/, message: '请输入正确的 11 位手机号', trigger: 'blur' }],
}
const auth = useAuthStore()
const router = useRouter()

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || submitting.value) return

  submitting.value = true
  try {
    await auth.register(form)
    ElMessage.success('注册成功，已为你自动登录')
    await router.replace('/')
  } catch (error) {
    ElMessage.error(error.message || '注册失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-page auth-page-register">
    <section class="auth-shell register-shell" aria-labelledby="register-title">
      <aside class="auth-showcase register-showcase">
        <RouterLink class="auth-brand auth-brand-light" to="/" aria-label="返回课后辅导系统首页">
          <span class="brand-mark">辅</span>
          <span>
            <strong>课后辅导</strong>
            <small>BS_HFN LEARNING</small>
          </span>
        </RouterLink>
        <div class="showcase-content">
          <span class="showcase-badge">新同学，你好</span>
          <h2>建立你的学习档案，<br />从第一门课程开始。</h2>
          <p>注册学生账号后，即可使用统一身份访问课程与视频内容。</p>
          <div class="register-note">
            <span>✓</span>
            <p><strong>信息安全提示</strong><small>请使用未在其他网站使用过的独立密码。</small></p>
          </div>
        </div>
        <p class="showcase-footer">LEARN · REVIEW · GROW</p>
      </aside>

      <section class="auth-panel register-panel">
        <RouterLink class="auth-brand auth-mobile-brand" to="/">
          <span class="brand-mark">辅</span>
          <span><strong>课后辅导</strong><small>BS_HFN LEARNING</small></span>
        </RouterLink>
        <div class="auth-form-wrap register-form-wrap">
          <p class="eyebrow">CREATE ACCOUNT</p>
          <h1 id="register-title">创建学生账号</h1>
          <p class="auth-intro">填写基本信息，带星号的内容为必填项。</p>

          <el-form
            ref="formRef"
            class="auth-form register-form"
            :model="form"
            :rules="rules"
            label-position="top"
            @submit.prevent="submit"
          >
            <div class="form-grid">
              <el-form-item label="用户名" prop="username">
                <el-input
                  v-model.trim="form.username"
                  size="large"
                  autocomplete="username"
                  placeholder="3–50 位中文、字母或数字"
                  clearable
                />
              </el-form-item>
              <el-form-item label="真实姓名" prop="real_name">
                <el-input
                  v-model.trim="form.real_name"
                  size="large"
                  autocomplete="name"
                  placeholder="请输入真实姓名"
                  clearable
                />
              </el-form-item>
              <el-form-item label="学号（选填）" prop="student_no">
                <el-input v-model.trim="form.student_no" size="large" placeholder="请输入学号" clearable />
              </el-form-item>
              <el-form-item label="邮箱（选填）" prop="email">
                <el-input
                  v-model.trim="form.email"
                  size="large"
                  autocomplete="email"
                  placeholder="name@example.com"
                  clearable
                />
              </el-form-item>
              <el-form-item label="手机号（选填）" prop="phone">
                <el-input
                  v-model.trim="form.phone"
                  size="large"
                  autocomplete="tel"
                  inputmode="tel"
                  maxlength="11"
                  placeholder="请输入 11 位手机号"
                  clearable
                />
              </el-form-item>
              <el-form-item label="登录密码" prop="password">
                <el-input
                  v-model="form.password"
                  size="large"
                  type="password"
                  show-password
                  autocomplete="new-password"
                  placeholder="请设置 8–72 位密码"
                />
              </el-form-item>
            </div>
            <el-button
              type="primary"
              native-type="submit"
              size="large"
              class="full-width auth-submit"
              :loading="submitting"
            >
              {{ submitting ? '正在创建账号' : '注册并登录' }}
            </el-button>
          </el-form>

          <p class="auth-secondary register-secondary">
            已有账号？
            <RouterLink to="/login">返回登录</RouterLink>
            <span aria-hidden="true">·</span>
            <RouterLink to="/">先浏览首页</RouterLink>
          </p>
        </div>
      </section>
    </section>
  </main>
</template>
