/**
 * ESLint 配置（从 package.json 的 eslintConfig 迁出，便于按目录加 overrides）。
 *
 * ⚠️ 规则集刻意保持与迁移前**完全一致**（plugin:vue/essential + eslint:recommended，
 * 仅关掉 vue/no-mutating-props）。扩规则必须一次性全开、跑一遍、把当时的违规数记进
 * `.eslint-baseline.json`，之后只允许「不新增」——见 `_verify_vue_lint.py`。
 *
 * 为什么不能直接上 plugin:vue/recommended：本仓库 61 个文件 / 近 3 万行，
 * recommended 会一次性报出上千条（主要是 attribute 顺序、多词组件名），
 * 那会把真正的信号淹没，也无法作为回归门。
 */
module.exports = {
  root: true,
  env: {
    node: true,
    // 前端代码会用到 window / document / setTimeout 等浏览器全局；
    // 加进来只会减少误报，不会引入新规则。
    browser: true
  },
  extends: ['plugin:vue/essential', 'eslint:recommended'],
  parserOptions: {
    parser: '@babel/eslint-parser'
  },
  rules: {
    'vue/no-mutating-props': 'off'
  },
  ignorePatterns: [
    'dist/',
    'public/',
    'node_modules/',
    '*.min.js'
  ]
}
