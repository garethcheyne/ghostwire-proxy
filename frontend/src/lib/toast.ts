/**
 * Global toast notification system.
 * Call toast() from anywhere — no hooks or context needed.
 */

export interface ToastItem {
  id: number
  message: string
  type: 'success' | 'error' | 'info'
}

type SetToasts = React.Dispatch<React.SetStateAction<ToastItem[]>>

let _setToasts: SetToasts | null = null

/** Called once by Toaster component to register the state setter */
export function registerToastSetter(fn: SetToasts) {
  _setToasts = fn
}

export function toast(message: string, type: 'success' | 'error' | 'info' = 'success') {
  if (!_setToasts) return
  const id = Date.now() + Math.random()
  _setToasts(prev => [...prev, { id, message, type }])
  setTimeout(() => _setToasts?.(prev => prev.filter(t => t.id !== id)), 4000)
}

export function toastSuccess(message: string) { toast(message, 'success') }
export function toastError(message: string) { toast(message, 'error') }
export function toastInfo(message: string) { toast(message, 'info') }
