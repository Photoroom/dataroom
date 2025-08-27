import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react'
import FastGlob from "fast-glob";


export default defineConfig(({ command }) => ({
  base: "/static/", // same as STATIC_URL
  root: './frontend/',
  build: {
    manifest: 'manifest.json', // generate a manifest.json in outDir
    rollupOptions: {
      input: {
        spa: './frontend/src/index.ts',
        styles: './frontend/styles/index.css',
      }
    },
    outDir:  '../backend/static_built/', // same as DJANGO_VITE_ASSETS_PATH
  },
  plugins: [
    react({
      fastRefresh: command === 'serve',  // dev only
    }),
    {
      name: 'watch-external', // https://stackoverflow.com/questions/63373804/rollup-watch-include-directory/63548394#63548394
      async buildStart(){
        const htmls = await FastGlob(['backend/templates/**/*.html']);
        for (let file of htmls) {
          this.addWatchFile(file);
        }

        const jinjas = await FastGlob(['backend/templates/**/*.jinja']);
        for (let file of jinjas) {
          this.addWatchFile(file);
        }
      }
    },
    {
      name: 'reloadHtml',
      handleHotUpdate({ file, server }) {
        if (file.endsWith('.html') || file.endsWith('.jinja')){
          server.ws.send({
            type: 'custom',
            event: 'template-hmr',
            path: '*',
          });
        }
      },
    }
  ],
}));
