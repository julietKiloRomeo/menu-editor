// Custom Jest transformer:
//   1) Rewrite `import.meta.env` -> `process.env` (Vite build-time construct
//      not available in Node/Jest).
//   2) Hand off to @swc/jest for TSX/TS compilation.

const swc = require('@swc/jest')

const inner = swc.createTransformer({
  jsc: {
    parser: { syntax: 'typescript', tsx: true, decorators: false },
    transform: { react: { runtime: 'automatic' } },
    target: 'es2022',
  },
  module: { type: 'commonjs' },
})

module.exports = {
  process(sourceText, sourcePath, options) {
    const rewritten = sourceText.replace(/import\.meta\.env/g, 'process.env')
    return inner.process(rewritten, sourcePath, options)
  },
  getCacheKey(sourceText, sourcePath, options) {
    if (typeof inner.getCacheKey === 'function') {
      return inner.getCacheKey(sourceText, sourcePath, options) + '-vitemeta'
    }
    return sourceText.length + ':' + sourcePath + '-vitemeta'
  },
}
