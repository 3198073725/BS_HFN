import MarkdownIt from 'markdown-it'

// 总结正文只接受 Markdown，不执行内容中的原始 HTML；保留解析器的危险协议过滤。
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: false })
const renderLink = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, index, options, environment, renderer) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return renderLink
    ? renderLink(tokens, index, options, environment, renderer)
    : renderer.renderToken(tokens, index, options)
}
// 宽表格只在自己的容器内滚动，不把整个学习页面撑宽。
markdown.renderer.rules.table_open = () => '<div class="markdown-table" tabindex="0" role="region" aria-label="总结表格"><table>\n'
markdown.renderer.rules.table_close = () => '</table></div>\n'

export function renderMarkdown(content) {
  return markdown.render(String(content || ''))
}
