import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

export default defineConfig({
  plugins: [preact()],

  // Assets are served by FastAPI's /static mount
  base: '/static/dist/',

  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Fixed filenames, no content hashes to keeps git diffs clean
        entryFileNames: 'app.js',
        chunkFileNames: '[name].js',
        assetFileNames: 'app[extname]',
      },
    },
  },
})
