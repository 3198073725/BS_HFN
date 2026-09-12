<script setup>
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'


const formRef = ref(null)
const submitting = ref(false)
const form = reactive({ username: '', password: '', real_name: '', student_no: '', email: '', phone: '' })
const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_\u4e00-\u9fff]{3,50}$/, message: '用户名需为 3–50 位中文、字母、数字或下划线', trigger: 'blur' },
  ],
  real_name: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' },
    { max: 50, message: '真实姓名不能超过 50 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请设置登录密码', trigger: 'blur' },
    { min: 8, max: 72, message: '密码长度需为 8–72 位', trigger: 'blur' },
  ],
  student_no: [{ max: 50, message: '学号不能超过 50 位', trigger: 'blur' }],
  email: [
    { type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' },
    { max: 100, message: '邮箱不能超过 100 位', trigger: 'blur' },
  ],
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
  <main class="account-page account-register-page">
    <section class="account-shell account-register-shell" aria-labelledby="register-title">
      <aside class="account-aside account-register-aside">
        <RouterLink class="account-brand" to="/" aria-label="返回课后辅导教学平台首页">
          <span class="account-brand-mark">课</span>
          <span><strong>课后辅导教学平台</strong><small>教学与学习管理</small></span>
        </RouterLink>
        <div class="account-aside-content">
          <p>学生账号注册</p>
          <h2>填写基本信息，<br />建立个人学习账号</h2>
          <div class="account-security-note">
            <strong>账号安全提示</strong>
            <span>密码长度至少 8 位，建议同时包含字母、数字和符号，不要与其他网站共用密码。</span>
          </div>
        </div>
        <p class="account-aside-footer">教师与管理员账号由系统管理员创建</p>
      </aside>

      <section class="account-panel account-register-panel">
        <RouterLink class="account-brand account-mobile-brand" to="/">
          <span class="account-brand-mark">课</span>
          <span><strong>课后辅导教学平台</strong><small>教学与学习管理</small></span>
        </RouterLink>
        <div class="account-form-wrap account-register-form-wrap">
          <p class="account-section-label">学生注册</p>
          <h1 id="register-title">创建学生账号</h1>
          <p class="account-intro">带星号的内容为必填项，其他信息可在需要时填写。</p>

          <el-form ref="formRef" class="account-form account-register-form" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
            <div class="account-form-grid">
              <el-form-item label="用户名" prop="username">
                <el-input v-model.trim="form.username" size="large" autocomplete="username" maxlength="50" placeholder="3–50 位中文、字母或数字" clearable />
              </el-form-item>
              <el-form-item label="真实姓名" prop="real_name">
                <el-input v-model.trim="form.real_name" size="large" autocomplete="name" maxlength="50" placeholder="请输入真实姓名" clearable />
              </el-form-item>
              <el-form-item label="学号（选填）" prop="student_no">
                <el-input v-model.trim="form.student_no" size="large" maxlength="50" placeholder="请输入学号" clearable />
              </el-form-item>
              <el-form-item label="邮箱（选填）" prop="email">
                <el-input v-model.trim="form.email" size="large" autocomplete="email" maxlength="100" placeholder="name@example.com" clearable />
              </el-form-item>
              <el-form-item label="手机号（选填）" prop="phone">
                <el-input v-model.trim="form.phone" size="large" autocomplete="tel" inputmode="tel" maxlength="11" placeholder="请输入 11 位手机号" clearable />
              </el-form-item>
              <el-form-item label="登录密码" prop="password">
                <el-input v-model="form.password" size="large" type="password" show-password autocomplete="new-password" maxlength="72" placeholder="请设置 8–72 位密码" />
              </el-form-item>
            </div>
            <el-button type="primary" native-type="submit" size="large" class="full-width account-submit" :loading="submitting">
              {{ submitting ? '正在创建账号' : '注册并登录' }}
            </el-button>
          </el-form>

          <div class="account-links account-register-links">
            <p>已有账号？<RouterLink to="/login">返回登录</RouterLink></p>
            <RouterLink to="/">返回平台首页</RouterLink>
          </div>
        </div>
      </section>
    </section>
  </main>
</template>
