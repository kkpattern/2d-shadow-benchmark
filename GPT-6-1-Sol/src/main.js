import * as THREE from 'three';
import './style.css';
import { vertexShader, shadowShader, compositeShader } from './shaders.js';

const $ = (selector) => document.querySelector(selector);
// This camera's 225° azimuth matches Argon's 0° orbit start.
const defaults = { azimuth: 225, elevation: 42, softness: 2, strength: 60 };
const state = { ...defaults, enabled: true, animate: false, view: 0, compare: false };
const descriptions = [
  'Light is traced through the town’s depth and thickness, one screen-space ray at a time.',
  'Linear camera depth from the Blender reconstruction. Brighter surfaces are closer to the camera.',
  'Distance between the front and back of the first solid interval. Warm colors indicate thicker geometry.',
  'Visible surface normals in camera space: red points right, green points down, blue points toward you.',
  'The raymarched visibility buffer. Dark regions are occluded from the current sun direction.'
];

let renderer, shadowTarget, shadowMaterial, compositeMaterial, camera, scene, quad;
let dirty = true, initialized = false, lastTime = 0, lastShadowTime = 0;
const WIDTH = 918, HEIGHT = 515;

function updateControls() {
  for (const key of Object.keys(defaults)) {
    const input = $(`#${key}`);
    input.value = state[key];
    input.style.setProperty('--fill', `${(state[key] - Number(input.min)) / (Number(input.max) - Number(input.min)) * 100}%`);
    $(`#${key}-value`).textContent = key === 'strength' ? `${Math.round(state[key])}%` : key === 'softness' ? `${state[key].toFixed(1)}°` : `${Math.round(state[key])}°`;
  }
  $('#animate').setAttribute('aria-checked', state.animate);
  $('#shadows').setAttribute('aria-pressed', state.enabled);
  $('#shadow-button-label').textContent = state.enabled ? 'Shadows enabled' : 'Shadows disabled';
  $('#scene-status').textContent = state.animate ? 'SUNLIGHT IN MOTION' : 'LIVE SUNLIGHT';
  const angle = (state.azimuth - 180) * Math.PI / 360;
  $('#sun-glyph').setAttribute('transform', `translate(${130 + 108 * Math.sin(angle)}, ${86 - 72 * Math.cos(angle)})`);
}

for (const key of Object.keys(defaults)) {
  $(`#${key}`).addEventListener('input', (event) => {
    state[key] = Number(event.target.value);
    if (key === 'azimuth') state.animate = false;
    updateControls(); dirty = true;
  });
}
$('#animate').addEventListener('click', () => { state.animate = !state.animate; updateControls(); });
$('#shadows').addEventListener('click', () => { state.enabled = !state.enabled; dirty = true; updateControls(); });
$('#reset').addEventListener('click', () => { Object.assign(state, defaults, { enabled: true, animate: false }); dirty = true; updateControls(); });
document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => {
  state.view = Number(button.dataset.view);
  document.querySelectorAll('[data-view]').forEach((b) => b.classList.toggle('active', b === button));
  $('#view-description').textContent = descriptions[state.view];
  $('#view-caption').textContent = ['LIVE RECONSTRUCTION', 'LINEAR DEPTH', 'SOLID THICKNESS', 'SURFACE NORMALS', 'SHADOW VISIBILITY'][state.view];
  dirty = true;
}));
function updateComparison() {
  const amount = Number($('#comparison').value);
  $('#reference-image').style.display = state.compare ? 'block' : 'none';
  $('#reference-image').style.clipPath = `inset(0 ${100 - amount}% 0 0)`;
  $('#compare-line').style.display = state.compare ? 'block' : 'none';
  $('#compare-line').style.left = `${amount}%`;
  $('#compare').setAttribute('aria-pressed', state.compare);
  $('#comparison').hidden = !state.compare;
}
$('#compare').addEventListener('click', () => { state.compare = !state.compare; updateComparison(); });
$('#comparison').addEventListener('input', updateComparison);
$('#export').addEventListener('click', () => {
  if (!initialized) return;
  renderFrame(true);
  renderer.domElement.toBlob((blob) => {
    if (!blob) return;
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.download = `isometric-light-${Math.round(state.azimuth)}-${Math.round(state.elevation)}.png`;
    link.href = url;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }, 'image/png');
});
window.addEventListener('keydown', (event) => {
  if (/INPUT|TEXTAREA|BUTTON|SELECT/.test(event.target.tagName) || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.code === 'Space') { event.preventDefault(); $('#animate').click(); }
  if (event.key.toLowerCase() === 's') $('#shadows').click();
});

async function fetchBinary(url, expectedLength) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url} (${response.status})`);
  const buffer = await response.arrayBuffer();
  const data = new Float32Array(buffer);
  if (expectedLength && data.length !== expectedLength) throw new Error(`Invalid buffer length for ${url}: ${data.length}`);
  return data;
}

async function initialize() {
  const metaResponse = await fetch('/generated/bake-metadata.json');
  if (!metaResponse.ok) throw new Error('The Blender buffers are missing. Run the reconstruction script described in README.md.');
  const metadata = await metaResponse.json();
  if (metadata.width !== WIDTH || metadata.height !== HEIGHT || metadata.layers !== 4) {
    throw new Error('The bake dimensions do not match the fixed reference camera (918 × 515 × 4).');
  }
  const [intervals, normals, color] = await Promise.all([
    fetchBinary('/generated/shadow-intervals.f32', WIDTH * HEIGHT * 4 * 4),
    fetchBinary('/generated/shadow-normals.f32', WIDTH * HEIGHT * 4),
    new THREE.TextureLoader().loadAsync('/generated/albedo.png')
  ]);
  color.colorSpace = THREE.NoColorSpace;
  color.minFilter = color.magFilter = THREE.LinearFilter;
  color.generateMipmaps = false;
  const intervalTexture = new THREE.DataArrayTexture(intervals, WIDTH, HEIGHT, 4);
  intervalTexture.format = THREE.RGBAFormat; intervalTexture.type = THREE.FloatType;
  intervalTexture.minFilter = intervalTexture.magFilter = THREE.NearestFilter;
  intervalTexture.generateMipmaps = false; intervalTexture.needsUpdate = true;
  const normalTexture = new THREE.DataTexture(normals, WIDTH, HEIGHT, THREE.RGBAFormat, THREE.FloatType);
  normalTexture.minFilter = normalTexture.magFilter = THREE.NearestFilter;
  normalTexture.needsUpdate = true;

  renderer = new THREE.WebGLRenderer({ canvas: $('#scene'), antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(1);
  renderer.setSize(WIDTH, HEIGHT, false);
  renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.debug.checkShaderErrors = true;
  camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  scene = new THREE.Scene();
  const common = { uIntervals: { value: intervalTexture }, uNormals: { value: normalTexture } };
  shadowTarget = new THREE.WebGLRenderTarget(WIDTH, HEIGHT, { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false, stencilBuffer: false, type: THREE.UnsignedByteType });
  const depthRange = metadata.depth_range ?? metadata.depthRange ?? [-300, 350];
  const occupiedDepthRange = metadata.occupiedDepthRange ?? [-600, 600];
  shadowMaterial = new THREE.ShaderMaterial({ vertexShader, fragmentShader: shadowShader, uniforms: {
    ...common, uSize: { value: new THREE.Vector2(WIDTH, HEIGHT) }, uDepthRange: { value: new THREE.Vector2(...occupiedDepthRange) }, uSun: { value: new THREE.Vector3() }, uSoftness: { value: 0 }, uEnabled: { value: 1 }
  }, depthTest: false, depthWrite: false });
  compositeMaterial = new THREE.ShaderMaterial({ vertexShader, fragmentShader: compositeShader, uniforms: {
    ...common, uColor: { value: color }, uShadow: { value: shadowTarget.texture }, uStrength: { value: state.strength / 100 }, uEnabled: { value: 1 }, uView: { value: 0 }, uDepthRange: { value: new THREE.Vector2(...depthRange) }
  }, depthTest: false, depthWrite: false });
  quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), compositeMaterial);
  quad.frustumCulled = false;
  scene.add(quad);
  initialized = true;
  $('#loading').style.display = 'none';
  updateControls();
  // A small, intentional API supports reproducible screenshot and interaction QA.
  window.shadowStudy = {
    ready: true, state, metadata,
    set(values) { Object.assign(state, values); updateControls(); dirty = true; renderFrame(true); },
    render() { dirty = true; renderFrame(true); },
    capture() { renderFrame(true); return renderer.domElement.toDataURL('image/png'); },
    getInfo() { return { calls: renderer.info.render.calls, textures: renderer.info.memory.textures, width: WIDTH, height: HEIGHT, three: THREE.REVISION }; }
  };
  renderFrame(true);
}

function renderFrame(force = false) {
  if (!initialized || (!dirty && !force)) return;
  const azimuth = THREE.MathUtils.degToRad(state.azimuth);
  const elevation = THREE.MathUtils.degToRad(state.elevation);
  const worldSun = new THREE.Vector3(Math.cos(azimuth) * Math.cos(elevation), Math.sin(azimuth) * Math.cos(elevation), Math.sin(elevation));
  shadowMaterial.uniforms.uSun.value.set(
    (worldSun.x - worldSun.y) * Math.SQRT1_2,
    (worldSun.x + worldSun.y) * Math.SQRT1_2 * 0.5 - worldSun.z * Math.sqrt(3) * 0.5,
    (worldSun.x + worldSun.y) * Math.sqrt(3 / 8) + worldSun.z * 0.5
  ).normalize();
  shadowMaterial.uniforms.uSoftness.value = THREE.MathUtils.degToRad(state.softness);
  shadowMaterial.uniforms.uEnabled.value = state.enabled ? 1 : 0;
  quad.material = shadowMaterial;
  renderer.setRenderTarget(shadowTarget);
  renderer.render(scene, camera);
  quad.material = compositeMaterial;
  compositeMaterial.uniforms.uStrength.value = state.strength / 100;
  compositeMaterial.uniforms.uEnabled.value = state.enabled ? 1 : 0;
  compositeMaterial.uniforms.uView.value = state.view;
  renderer.setRenderTarget(null);
  renderer.render(scene, camera);
  dirty = false;
}

function tick(time) {
  requestAnimationFrame(tick);
  if (document.hidden) { lastTime = time; return; }
  const delta = Math.min((time - (lastTime || time)) / 1000, 0.1);
  lastTime = time;
  if (initialized && state.animate) {
    state.azimuth = (state.azimuth + delta * 8) % 360;
    if (time - lastShadowTime > 1000 / 20) {
      updateControls(); dirty = true; lastShadowTime = time;
    }
  }
  renderFrame();
}
updateControls();
requestAnimationFrame(tick);
initialize().catch((error) => {
  console.error(error);
  $('#loading').style.display = 'none';
  $('#scene-error').hidden = false;
  $('#scene-error').textContent = `This light study could not start. ${error.message}`;
  $('#scene-status').textContent = 'RENDERER UNAVAILABLE';
});
