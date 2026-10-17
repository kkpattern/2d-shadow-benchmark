import * as THREE from 'three';
import fragmentShader from './shadow.frag.glsl?raw';
import './style.css';

const $ = (id) => document.getElementById(id);
const query = new URLSearchParams(location.search);
const captureMode = query.has('capture');
if (captureMode) document.body.classList.add('capture');

// This camera's -135° azimuth matches Argon's 0° orbit start.
const defaults = Object.freeze({ azimuth: -135, elevation: 40, softness: 0.35, strength: 0.65, shadows: true, animate: false, view: 'beauty', compare: false, comparison: 50 });
const state = { ...defaults };
const views = { beauty: 0, original: 1, depth: 2, thickness: 3, normals: 4, shadow: 5 };
const descriptions = {
  beauty: ['LIVE LIGHTING', 'Original sprites. Dynamic cast shadows.', 'Sprite colors retain their original shading; the moving sun adds geometry-aware cast shadows.'],
  original: ['ORIGINAL COLOR', 'Reassembled from the supplied sprite tiles.', 'The original sprite composition, without added shadows. Compare against the supplied reference image.'],
  depth: ['FRONT DEPTH', 'Linear camera depth · 16-bit precision', 'The first visible surface along each camera ray. Lighter tones are closer to the camera.'],
  thickness: ['SOLID THICKNESS', 'Front-to-back distance · world units', 'Distance between the first front surface and its exit surface. Teal is thin; warm colors are thicker.'],
  normals: ['WORLD NORMALS', 'Surface orientation · XYZ → RGB', 'World-space surface normals derived from reconstructed geometry. Z is the vertical axis.'],
  shadow: ['SHADOW VISIBILITY', 'White = lit · black = occluded', 'The raw screen-space raymarch result before it is applied to sprite color. Softness averages three light rays.'],
};
const presets = { morning: { azimuth: -70, elevation: 23 }, noon: { azimuth: -10, elevation: 78 }, evening: { azimuth: 115, elevation: 22 } };
let renderer, uniforms, scene, camera, manifest;
let ready = false;
let renderCount = 0;
let fpsFrames = 0;
let fpsStarted = performance.now();
let lastFrame = performance.now();
let dirty = true;

function syncUi() {
  for (const name of ['azimuth', 'elevation', 'softness', 'strength']) {
    const input = $(name);
    input.value = state[name];
    input.style.setProperty('--range-progress', `${(state[name] - Number(input.min)) / (Number(input.max) - Number(input.min)) * 100}%`);
    $(`${name}-value`).textContent = name === 'azimuth' || name === 'elevation' ? `${Math.round(state[name])}°` : `${Math.round(state[name] * 100)}%`;
  }
  $('shadows').checked = state.shadows;
  $('animate-button').setAttribute('aria-pressed', String(state.animate));
  $('animate-label').textContent = state.animate ? 'Pause sun' : 'Animate sun';
  $('animate-icon').textContent = state.animate ? 'Ⅱ' : '▶';
  $('sun-direction').style.transform = `translate(-50%, -50%) rotate(${state.azimuth}deg)`;
  document.querySelectorAll('[data-view]').forEach((button) => {
    const active = button.dataset.view === state.view;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  document.querySelectorAll('[data-preset]').forEach((button) => {
    const preset = presets[button.dataset.preset];
    button.classList.toggle('active', Math.abs(state.azimuth - preset.azimuth) < 1 && Math.abs(state.elevation - preset.elevation) < 1);
  });
  const description = descriptions[state.view];
  $('stage-label-text').textContent = description[0];
  $('stage-description').textContent = description[1];
  $('view-note').textContent = description[2];
  $('compare-button').setAttribute('aria-pressed', String(state.compare));
  for (const id of ['reference-overlay', 'comparison-divider', 'comparison-slider']) $(id).hidden = !state.compare;
  $('comparison-slider').value = state.comparison;
  $('reference-overlay').style.clipPath = `inset(0 ${100 - state.comparison}% 0 0)`;
  $('comparison-divider').style.left = `${state.comparison}%`;
}

function syncUniforms() {
  if (!uniforms) return;
  const azimuth = THREE.MathUtils.degToRad(state.azimuth);
  const elevation = THREE.MathUtils.degToRad(state.elevation);
  uniforms.uLight.value.set(Math.cos(azimuth) * Math.cos(elevation), Math.sin(azimuth) * Math.cos(elevation), Math.sin(elevation));
  uniforms.uSoftness.value = state.softness;
  uniforms.uStrength.value = state.strength;
  uniforms.uShadows.value = state.shadows;
  uniforms.uView.value = views[state.view];
}

function setState(next = {}) {
  for (const [key, value] of Object.entries(next)) {
    if (!(key in defaults)) continue;
    if (key === 'view') { if (value in views) state.view = value; }
    else if (['shadows', 'animate', 'compare'].includes(key)) state[key] = Boolean(value);
    else if (Number.isFinite(Number(value))) {
      const bounds = { azimuth: [-180, 180], elevation: [10, 85], softness: [0, 1], strength: [0, 1], comparison: [0, 100] }[key];
      state[key] = THREE.MathUtils.clamp(Number(value), ...bounds);
    }
  }
  syncUi();
  syncUniforms();
  dirty = true;
  if (ready) render();
  return { ...state };
}

function render() {
  if (!ready) return false;
  renderer.render(scene, camera);
  renderCount++;
  dirty = false;
  return true;
}

window.__shadowLab = {
  ready: false,
  setState,
  render,
  getState: () => ({ ...state, ready, renderCount, renderer: renderer?.info.render, manifest }),
};

for (const name of ['azimuth', 'elevation', 'softness', 'strength']) {
  $(name).addEventListener('input', (event) => setState({ [name]: Number(event.target.value), ...(name === 'azimuth' || name === 'elevation' ? { animate: false } : {}) }));
}
$('shadows').addEventListener('change', (event) => setState({ shadows: event.target.checked }));
$('animate-button').addEventListener('click', () => setState({ animate: !state.animate }));
$('reset-button').addEventListener('click', () => setState({ ...defaults, view: state.view, compare: state.compare }));
$('compare-button').addEventListener('click', () => setState({ compare: !state.compare }));
$('comparison-slider').addEventListener('input', (event) => setState({ comparison: Number(event.target.value) }));
document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => setState({ view: button.dataset.view })));
document.querySelectorAll('[data-preset]').forEach((button) => button.addEventListener('click', () => setState({ ...presets[button.dataset.preset], animate: false })));
document.addEventListener('keydown', (event) => {
  if (event.code !== 'Space' || ['INPUT', 'TEXTAREA', 'BUTTON', 'A', 'SELECT'].includes(document.activeElement.tagName)) return;
  event.preventDefault();
  setState({ animate: !state.animate });
});

async function loadTexture(name, color = false) {
  const texture = await new THREE.TextureLoader().loadAsync(`/generated/${name}.png`);
  texture.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  texture.minFilter = THREE.NearestFilter;
  texture.magFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
  return texture;
}

async function loadInterval(index) {
  const response = await fetch(`/generated/interval${index}.bin`);
  if (!response.ok) throw new Error(`Solid interval ${index} could not be loaded (HTTP ${response.status}).`);
  const source = new Uint8Array(await response.arrayBuffer());
  const rowSize = manifest.width * 4;
  if (source.length !== rowSize * manifest.height) throw new Error(`Solid interval ${index} has an invalid byte length.`);
  // Raw RGBA bytes preserve all 32 data bits, including the alpha channel.
  // Reverse top-down file rows explicitly; DataTexture UV zero is the bottom.
  const pixels = new Uint8Array(source.length);
  for (let y = 0; y < manifest.height; y++) {
    pixels.set(source.subarray(y * rowSize, (y + 1) * rowSize), (manifest.height - 1 - y) * rowSize);
  }
  const texture = new THREE.DataTexture(pixels, manifest.width, manifest.height, THREE.RGBAFormat, THREE.UnsignedByteType);
  texture.colorSpace = THREE.NoColorSpace;
  texture.minFilter = texture.magFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.flipY = false;
  texture.needsUpdate = true;
  return texture;
}

async function initialize() {
  const response = await fetch('/generated/scene.json');
  if (!response.ok) throw new Error(`Scene manifest could not be loaded (HTTP ${response.status}). Run the asset generation step first.`);
  manifest = await response.json();
  const [color, front, back, normal, ...intervals] = await Promise.all([
    loadTexture('color', true), loadTexture('front'), loadTexture('back'), loadTexture('normal'),
    ...Array.from({ length: 8 }, (_, i) => loadInterval(i)),
  ]);
  renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false, powerPreference: 'high-performance', preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.setSize(manifest.width, manifest.height, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.domElement.setAttribute('aria-label', 'Isometric city with interactive screen-space shadows');
  renderer.domElement.setAttribute('role', 'img');
  $('canvas-container').appendChild(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 2);
  camera.position.z = 1;
  uniforms = {
    uColor: { value: color }, uFront: { value: front }, uBack: { value: back }, uNormal: { value: normal },
    uInterval0: { value: intervals[0] }, uInterval1: { value: intervals[1] }, uInterval2: { value: intervals[2] }, uInterval3: { value: intervals[3] },
    uInterval4: { value: intervals[4] }, uInterval5: { value: intervals[5] }, uInterval6: { value: intervals[6] }, uInterval7: { value: intervals[7] },
    uResolution: { value: new THREE.Vector2(manifest.width, manifest.height) },
    uRight: { value: new THREE.Vector3(...manifest.camera.right) },
    uUp: { value: new THREE.Vector3(...manifest.camera.up) },
    uForward: { value: new THREE.Vector3(...manifest.camera.forward) },
    uOrigin: { value: new THREE.Vector3(...manifest.camera.origin) },
    uLight: { value: new THREE.Vector3() }, uBackground: { value: new THREE.Color(manifest.background || '#3f7cb6') },
    uDepthMin: { value: manifest.depthMin }, uDepthRange: { value: manifest.depthRange },
    uPixelsPerUnit: { value: manifest.pixelsPerUnit }, uSoftness: { value: state.softness },
    uMaxHeight: { value: manifest.maxHeight },
    uStrength: { value: state.strength }, uShadows: { value: state.shadows }, uView: { value: views[state.view] },
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
    fragmentShader,
    depthTest: false,
    depthWrite: false,
  });
  scene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material));
  syncUniforms();
  await renderer.compileAsync(scene, camera);
  ready = true;
  window.__shadowLab.ready = true;
  $('loading').hidden = true;
  render();
}

function frame(time) {
  requestAnimationFrame(frame);
  const elapsed = Math.min((time - lastFrame) / 1000, 0.1);
  lastFrame = time;
  if (!ready || document.hidden) return;
  if (state.animate) {
    // This camera's right axis is reversed; decrease azimuth to match the other orbits.
    state.azimuth = ((state.azimuth - elapsed * 12 + 540) % 360) - 180;
    syncUi();
    syncUniforms();
  }
  // Render continuously in the interactive lab so the FPS counter measures
  // the actual shader workload. Captures render only when state changes.
  if (!captureMode || dirty || state.animate) {
    render();
    fpsFrames++;
  }
  if (time - fpsStarted >= 1000) {
    $('fps-value').textContent = captureMode ? '—' : String(Math.round(fpsFrames * 1000 / (time - fpsStarted)));
    fpsFrames = 0;
    fpsStarted = time;
  }
}

setState({
  ...(query.has('view') ? { view: query.get('view') } : {}),
  ...(query.has('azimuth') ? { azimuth: query.get('azimuth') } : {}),
  ...(query.has('elevation') ? { elevation: query.get('elevation') } : {}),
  ...(query.has('shadows') ? { shadows: query.get('shadows') !== '0' } : {}),
});
initialize().catch((error) => {
  console.error(error);
  window.__shadowLab.error = error.message;
  $('loading').classList.add('error');
  $('loading').replaceChildren();
  const title = document.createElement('strong');
  title.textContent = 'The scene could not be loaded';
  const message = document.createElement('span');
  message.textContent = error.message;
  $('loading').append(title, message);
});
requestAnimationFrame(frame);
