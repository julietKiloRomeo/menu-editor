import '@testing-library/jest-dom'

// Minimal mocks for browser APIs used in App
Object.defineProperty(global, 'URL', {
  value: {
    createObjectURL: jest.fn(() => 'blob:mock'),
    revokeObjectURL: jest.fn(),
  },
  writable: true,
})

// Mock html2pdf to avoid loading during tests
jest.mock('html2pdf.js', () => ({ __esModule: true, default: {} }))

// Mock play() to resolve
// @ts-ignore
HTMLMediaElement.prototype.play = jest.fn().mockResolvedValue(void 0)

// Canvas mocks
// @ts-ignore
HTMLCanvasElement.prototype.getContext = jest.fn(() => ({
  drawImage: jest.fn(),
}))

// @ts-ignore
HTMLCanvasElement.prototype.toBlob = jest.fn((cb: (blob: Blob | null) => void) => {
  const blob = new Blob(['test'], { type: 'image/jpeg' })
  cb(blob)
})

