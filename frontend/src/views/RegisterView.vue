<script setup>
import { ElMessage } from 'element-plus'
import { reactive } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'


const form = reactive({
  username: '',
  password: '',
  real_name: '',
  student_no: '',
  email: '',
  phone: '',
})
const auth = useAuthStore()
const router = useRouter()

async function submit() {
  try {
    await auth.register(form)
    ElMessage.success('注册成功')
    await router.replace('/')
  } catch (error) {
    ElMessage.error(error.message || '注册失败')
  }
}
</script>

<template>
  <main class="centered-page">
    <el-card class="login-card" shadow="never">
      <p class="eyebrow">STUDENT SIGN UP</p>
      <h1>学生注册</h1>
      <el-form :model="form" label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="真实姓名" required>
          <el-input v-model="form.real_name" autocomplete="name" />
        </el-form-item>
        <el-form-item label="学号">
          <el-input v-model="form.student_no" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" autocomplete="email" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" autocomplete="tel" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="form.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-button type="primary" native-type="submit" class="full-width">注册并登录</el-button>
      </el-form>
      <div class="auth-links">
        <RouterLink to="/login">已有账号，去登录</RouterLink>
        <RouterLink to="/">返回首页</RouterLink>
      </div>
    </el-card>
  </main>
</template>
