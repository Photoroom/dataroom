const js       = require('@eslint/js');
const tsplugin = require('@typescript-eslint/eslint-plugin');
const tsparser = require('@typescript-eslint/parser');
const globals  = require('globals');

/** @type {import('eslint').Linter.FlatConfig[]} */
module.exports = [
  /* 1 ▸ project-specific ignores (mirrors your .prettierignore + extras) */
  {
    ignores: [
      'backend/**',
      '*.config.js',
      '*.config.ts',
      'frontend/src/api/client.ts',
      'frontend/src/api/client.schemas.ts',
    ],
  },

  /* 2 ▸ recommended rule sets + a handful of useful TS stricter checks */
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    languageOptions: {
      parser: tsparser,
      ecmaVersion: 2020,
      sourceType: 'module',
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { '@typescript-eslint': tsplugin },
    rules: {
      /* core + TS recommendations */
      ...js.configs.recommended.rules,
      ...tsplugin.configs.recommended.rules,

      /* pick any *logic* rules you still want */
      '@typescript-eslint/no-unused-vars': 'warn',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-empty-object-type': 'warn',
    },
  },
];