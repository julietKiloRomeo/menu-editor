import type { Config } from 'jest'

const config: Config = {
  testEnvironment: 'jsdom',
  setupFiles: ['<rootDir>/jest.polyfills.ts'],
  setupFilesAfterEnv: ['<rootDir>/setupTests.ts'],
  transform: {
    '^.+\\.(ts|tsx|js|mjs|jsx)$': '<rootDir>/jest.transformer.cjs',
  },
  transformIgnorePatterns: [
    // Force-transform ESM-only packages that ship .mjs/ESM sources.
    'node_modules/(?!(marked|html2pdf\\.js)/)',
  ],
  moduleNameMapper: {
    '\\.(css|less|scss|sass)$': '<rootDir>/styleMock.js',
    '^html2pdf.js$': '<rootDir>/mocks/html2pdf.js',
  },
}

export default config

