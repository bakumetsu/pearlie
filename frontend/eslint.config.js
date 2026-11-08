import eslint from '@eslint/js'
import tseslint from 'typescript-eslint'
import svelte from 'eslint-plugin-svelte'
import globals from 'globals'

export default [
  { ignores: ['dist', 'node_modules'] },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...svelte.configs['flat/recommended'],
  {
    files: ['**/*.svelte'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
      globals: globals.browser,
    },
  },
  {
    files: ['**/*.svelte.ts'],
    languageOptions: {
      parser: tseslint.parser,
      globals: globals.browser,
    },
  },
  {
    files: ['src/**/*.{ts,svelte}'],
    ignores: ['src/lib/api/client.ts', 'src/**/*.test.ts'],
    rules: {
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'Use the Api client in lib/api' },
      ],
    },
  },
  {
    files: ['**/*.ts'],
    languageOptions: {
      globals: globals.browser,
    },
  },
]
