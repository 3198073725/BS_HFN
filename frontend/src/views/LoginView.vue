<script setup>
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'


const formRef = ref(null)
const submitting = ref(false)
const form = reactive({ account: '', password: '' })
const rules = {
  account: [
    { required: true, message: '请输入用户名、邮箱、学号或工号', trigger: 'blur' },
    { max: 100, message: '账号不能超过 100 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入登录密码', trigger: 'blur' },
    { max: 72, message: '密码不能超过 72 位', trigger: 'blur' },
  ],
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
  <main class="account-page">
    <section class="account-shell" aria-labelledby="login-title">
      <aside class="account-aside">
        <RouterLink class="account-brand" to="/" aria-label="返回课后辅导教学平台首页">
          <span class="account-brand-mark">课</span>
          <span><strong>课后辅导教学平台</strong><small>教学与学习管理</small></span>
        </RouterLink>
        <div class="account-aside-content">
          <p>统一身份认证</p>
          <h2>登录一个账号，<br />使用对应的教学服务</h2>
          <ul>
            <li><strong>学生</strong><span>课程学习、作业、测验与班级信息</span></li>
            <li><strong>教师</strong><span>课程、班级和教学活动管理</span></li>
            <li><strong>管理员</strong><span>账号、分类与系统公告管理</span></li>
          </ul>
        </div>
        <p class="account-aside-footer">请妥善保管账号与登录密码</p>
      </aside>

      <section class="account-panel">
        <RouterLink class="account-brand account-mobile-brand" to="/">
          <span class="account-brand-mark">课</span>
          <span><strong>课后辅导教学平台</strong><small>教学与学习管理</small></span>
        </RouterLink>
        <div class="account-form-wrap">
          <p class="account-section-label">账号登录</p>
          <h1 id="login-title">欢迎回来</h1>
          <p class="account-intro">请输入平台账号和密码，系统将按身份进入相应功能页面。</p>

          <el-form ref="formRef" class="account-form" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
            <el-form-item label="账号" prop="account">
              <el-input
                v-model.trim="form.account"
                size="large"
                autocomplete="username"
                autofocus
                clearable
                maxlength="100"
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
                maxlength="72"
                placeholder="请输入登录密码"
              />
            </el-form-item>
            <el-button type="primary" native-type="submit" size="large" class="full-width account-submit" :loading="submitting">
              {{ submitting ? '正在登录' : '登录' }}
            </el-button>
          </el-form>

          <div class="account-links">
            <p>还没有学生账号？<RouterLink to="/register">学生注册</RouterLink></p>
            <RouterLink to="/">返回平台首页</RouterLink>
          </div>
        </div>
      </section>
    </section>
  </main>
</template>
