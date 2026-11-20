import assert from 'node:assert/strict'
import { renderMarkdown } from '../src/utils/markdown.js'

const source = [
  '## 视频总结', '', '### 知识点', '', '- **变量**与类型', '- 循环', '',
  '1. 理解', '2. 练习', '', '> 复习重点', '',
  '| 名称 | 说明 |', '| --- | --- |', '| int | 整数 |', '',
  '```c', 'int main(void) { return 0; }', '```', '',
  '[参考资料](https://example.com/)', '',
  '<script>alert(1)</script>', '<img src=x onerror=alert(1)>', '',
  '[危险链接](javascript:alert(1))', '[编码链接](jav&#x61;script:alert(1))',
].join('\n')
const html = renderMarkdown(source)
for (const tag of ['<h2>', '<h3>', '<ul>', '<ol>', '<strong>', '<blockquote>', '<table>', '<pre><code class="language-c">']) {
  assert.ok(html.includes(tag), `缺少 Markdown 格式：${tag}`)
}
assert.ok(html.includes('rel="noopener noreferrer"'))
assert.ok(!html.includes('<script>') && !html.includes('<img src=x'))
assert.ok(!html.includes('href="javascript:'))
assert.ok(html.includes('&lt;script&gt;'))
assert.equal(renderMarkdown(null), '')
assert.ok(renderMarkdown('普通文本').includes('<p>普通文本</p>'))
console.log('通过：标题、列表、加粗、引用、表格、代码块和安全链接均正确渲染；原始 HTML 与危险链接不执行。')
