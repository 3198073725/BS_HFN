<script setup>
import { ElMessage } from 'element-plus'
import { reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'


const form = reactive({ account: '', password: '' })
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

async function submit() {
  try {
    await auth.login(form)
    ElMessage.success('登录成功')
    await router.replace(String(route.query.redirect || '/'))
  } catch (error) {
    ElMessage.error(error.message || '登录失败')
  }
}
</script>

<template>
  <main class="centered-page">
    <el-card class="login-card" shadow="never">
      <p class="eyebrow">WELCOME BACK</p>
      <h1>登录</h1>
      <el-form :model="form" label-position="top" @submit.prevent="submit">
        <el-form-item label="账号">
          <el-input v-model="form.account" autocomplete="username" placeholder="用户名、邮箱、学号或工号" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-button type="primary" native-type="submit" class="full-width">登录</el-button>
      </el-form>
      <div class="auth-links">
        <RouterLink to="/register">学生注册</RouterLink>
        <RouterLink to="/">返回首页</RouterLink>
      </div>
    </el-card>
  </main>
</template>
