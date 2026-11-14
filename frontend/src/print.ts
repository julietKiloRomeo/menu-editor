export function isIosDevice(): boolean {
  return /iPhone|iPad|iPod/i.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
}

/** iOS home-screen web apps can expose print() without presenting a dialog. */
export function isIosHomeScreen(): boolean {
  const standalone = (navigator as Navigator & { standalone?: boolean }).standalone === true ||
    (typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches)
  return isIosDevice() && standalone
}

/** A normal HTML page avoids iOS's control-less full-screen PDF viewer. */
export function safariPrintPage(pdfUrl: string): string {
  return new URL(pdfUrl.replace(/\.pdf$/, ''), window.location.href).href
}
