import { TextEncoder, TextDecoder } from 'util'

// jsdom lacks these globals; react-router-dom v7 and other modules need
// them at import time (before any test file is evaluated).
if (typeof (globalThis as any).TextEncoder === 'undefined') {
  ;(globalThis as any).TextEncoder = TextEncoder
}
if (typeof (globalThis as any).TextDecoder === 'undefined') {
  ;(globalThis as any).TextDecoder = TextDecoder
}
