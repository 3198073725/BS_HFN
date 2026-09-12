<script setup>
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import { useAuthStore } from '../stores/auth'


const formRef = ref(null)
const submitting = ref(false)
const resetDialog = ref(false)
const resetting = ref(false)
const form = reactive({ account: '', password: '' })
const resetForm = reactive({ username: '', verification: '', new_password: '', confirm_password: '' })
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

async function resetPassword() {
  if (!resetForm.username.trim() || !resetForm.verification.trim()) {
    ElMessage.warning('请填写用户名和身份验证信息')
    return
  }
  if (resetForm.new_password.length < 8 || resetForm.new_password.length > 72) {
    ElMessage.warning('新密码长度需为 8 到 72 位')
    return
  }
  if (resetForm.new_password !== resetForm.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  resetting.value = true
  try {
    await api.post('/auth/reset-password', {
      username: resetForm.username.trim(),
      verification: resetForm.verification.trim(),
      new_password: resetForm.new_password,
    })
    form.account = resetForm.username.trim()
    form.password = ''
    resetDialog.value = false
    Object.assign(resetForm, { username: '', verification: '', new_password: '', confirm_password: '' })
    ElMessage.success('密码已重置，请使用新密码登录')
  } catch (error) {
    ElMessage.error(error.message || '密码重置失败')
  } finally {
    resetting.value = false
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
            <el-button link @click="resetDialog = true">忘记密码</el-button>
            <RouterLink to="/">返回平台首页</RouterLink>
          </div>
        </div>
      </section>
    </section>

    <el-dialog v-model="resetDialog" title="找回密码" width="min(520px, 94vw)" :close-on-click-modal="!resetting">
      <p class="dialog-tip">学生或教师可使用注册邮箱、学号、工号或手机号核验身份。管理员账号请由另一位管理员在系统后台重置。</p>
      <el-form label-position="top" @submit.prevent="resetPassword">
        <el-form-item label="用户名" required>
          <el-input v-model.trim="resetForm.username" maxlength="50" autocomplete="username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="身份验证信息" required>
          <el-input v-model.trim="resetForm.verification" maxlength="100" placeholder="注册邮箱、学号、工号或手机号" />
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="resetForm.new_password" type="password" show-password maxlength="72" autocomplete="new-password" placeholder="8–72 位新密码" />
        </el-form-item>
        <el-form-item label="确认新密码" required>
          <el-input v-model="resetForm.confirm_password" type="password" show-password maxlength="72" autocomplete="new-password" placeholder="再次输入新密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="resetting" @click="resetDialog = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="resetPassword">确认重置</el-button>
      </template>
    </el-dialog>
  </main>
</template>
