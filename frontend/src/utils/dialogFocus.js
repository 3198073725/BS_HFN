import { nextTick, onBeforeUnmount, watch } from 'vue'

export function focusElement(element) {
  if (!element?.isConnected || !element.getClientRects().length || element.matches(':disabled') || element.closest('[inert]')) return false
  element.focus()
  return document.activeElement === element
}

// Capture before rendering/focus trapping. Each nested dialog owns its opener.
export function useDialogFocus(visible) {
  let opener = null
  let alive = true
  watch(visible, (open) => {
    if (open) opener = document.activeElement
  }, { flush: 'sync' })
  onBeforeUnmount(() => { alive = false; opener = null })
  return async (event) => {
    event?.preventDefault()
    await nextTick()
    if (!alive || visible.value) return
    if (opener !== document.body && focusElement(opener)) return
    // The original row may disappear after saving/filtering/pagination.
    const heading = document.querySelector('.app-main .page-heading h1')
    if (heading) {
      heading.setAttribute('tabindex', '-1')
      focusElement(heading)
    }
  }
}
