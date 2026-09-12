<template>
  <main class="centered-page">
    <el-result icon="warning" title="404" sub-title="页面不存在">
      <template #extra>
        <RouterLink to="/"><el-button type="primary">返回首页</el-button></RouterLink>
      </template>
    </el-result>
  </main>
</template>
