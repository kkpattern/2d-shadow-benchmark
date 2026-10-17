import { defineConfig } from 'vite';
import { copyFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

// Keep the original art/model pipeline at the project root. Only the runtime
// bake (not Blender's project or analytical intermediates) belongs in dist.
export default defineConfig({
  publicDir: false,
  plugins: [{
    name: 'copy-baked-scene',
    async closeBundle() {
      const files = ['sample.png', 'docs/SHADOW_RESEARCH.md',
        'generated/albedo.png', 'generated/shadow-intervals.f32',
        'generated/shadow-normals.f32', 'generated/bake-metadata.json'];
      for (const file of files) {
        const destination = path.join('dist', file);
        await mkdir(path.dirname(destination), { recursive: true });
        await copyFile(file, destination);
      }
    }
  }]
});
