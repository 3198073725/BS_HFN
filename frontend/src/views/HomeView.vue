<script setup>
import { useAuthStore } from '../stores/auth'


const auth = useAuthStore()
</script>

<template>
  <div class="home-page">
    <section class="home-hero">
      <div class="hero-copy">
        <span class="status-pill"><i></i> 课后学习空间已开放</span>
        <p class="eyebrow">AFTER-CLASS LEARNING</p>
        <h1>让知识在课堂之外，<span>继续发生。</span></h1>
        <p class="hero-description">
          从课程章节到高清视频，把分散的课后学习内容整理成一条清晰路径。学生更专注，教师更省心。
        </p>
        <div class="hero-actions">
          <RouterLink class="action-link action-link-primary" to="/courses">
            浏览课程
            <span aria-hidden="true">→</span>
          </RouterLink>
          <RouterLink v-if="!auth.isAuthenticated" class="action-link action-link-ghost" to="/login">
            登录学习空间
          </RouterLink>
          <RouterLink
            v-else-if="auth.user?.role === 'TEACHER'"
            class="action-link action-link-ghost"
            to="/teacher/courses"
          >
            进入教学管理
          </RouterLink>
        </div>
        <div class="hero-proof">
          <div><strong>清晰</strong><span>课程与章节结构</span></div>
          <div><strong>流畅</strong><span>HLS 视频播放</span></div>
          <div><strong>可靠</strong><span>异步转码处理</span></div>
        </div>
      </div>

      <div class="hero-visual" aria-label="课程学习界面示意">
        <div class="visual-glow"></div>
        <div class="learning-window">
          <div class="window-top">
            <div class="window-dots"><i></i><i></i><i></i></div>
            <span>我的学习空间</span>
            <b>BS</b>
          </div>
          <div class="window-body">
            <div class="lesson-preview">
              <span class="preview-label">正在学习</span>
              <div class="play-button">▶</div>
              <div class="preview-caption">
                <small>第 03 章</small>
                <strong>核心知识点精讲</strong>
              </div>
            </div>
            <div class="lesson-list">
              <div class="lesson-list-title"><strong>课程目录</strong><span>3 / 8</span></div>
              <div class="lesson-row completed"><i>✓</i><p><strong>课程导学</strong><small>08:24</small></p></div>
              <div class="lesson-row active"><i>▶</i><p><strong>核心知识点精讲</strong><small>18:42</small></p></div>
              <div class="lesson-row"><i>03</i><p><strong>课后练习分析</strong><small>12:16</small></p></div>
            </div>
          </div>
        </div>
        <div class="floating-note">
          <span>✓</span>
          <p><strong>视频处理完成</strong><small>已生成 HLS 播放资源</small></p>
        </div>
      </div>
    </section>

    <section class="feature-section" aria-labelledby="feature-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">CORE EXPERIENCE</p>
          <h2 id="feature-title">围绕学习本身，保持简单</h2>
        </div>
        <p>第一阶段聚焦最重要的课程、章节和视频闭环，为后续学习功能建立稳定基础。</p>
      </div>
      <div class="feature-grid">
        <article>
          <span class="feature-index">01</span>
          <div class="feature-icon">课</div>
          <h3>课程结构清晰</h3>
          <p>按分类浏览已发布课程，通过章节快速找到当前需要复习的内容。</p>
          <RouterLink to="/courses">进入课程中心 →</RouterLink>
        </article>
        <article>
          <span class="feature-index">02</span>
          <div class="feature-icon feature-icon-teal">播</div>
          <h3>多端视频播放</h3>
          <p>使用 FFmpeg 转码并生成 HLS 资源，为桌面端与移动端提供稳定播放体验。</p>
          <span class="feature-meta">FFMPEG + HLS</span>
        </article>
        <article>
          <span class="feature-index">03</span>
          <div class="feature-icon feature-icon-gold">教</div>
          <h3>教学内容管理</h3>
          <p>教师可以创建课程与章节、上传视频，并实时了解视频后台处理状态。</p>
          <RouterLink v-if="auth.user?.role === 'TEACHER'" to="/teacher/courses">进入教学管理 →</RouterLink>
          <span v-else class="feature-meta">TEACHER WORKSPACE</span>
        </article>
      </div>
    </section>
  </div>
</template>
