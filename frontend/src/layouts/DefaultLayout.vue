<script setup>
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'


const route = useRoute()
const auth = useAuthStore()
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <RouterLink class="brand" to="/">课后辅导系统</RouterLink>
      <el-menu :default-active="route.path" mode="horizontal" router :ellipsis="false">
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/courses">课程</el-menu-item>
        <el-menu-item v-if="auth.user?.role === 'TEACHER'" index="/teacher/courses">教学管理</el-menu-item>
      </el-menu>
      <div class="session-actions">
        <span v-if="auth.user" class="muted">{{ auth.user.real_name }} · {{ auth.user.role }}</span>
        <el-button v-if="auth.isAuthenticated" text @click="auth.logout">退出</el-button>
        <RouterLink v-else to="/login"><el-button text>登录</el-button></RouterLink>
      </div>
    </el-header>
    <el-main class="app-main">
      <RouterView />
    </el-main>
  </el-container>
</template>
