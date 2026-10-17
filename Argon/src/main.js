import * as THREE from 'three';
import {
  CANVAS_WIDTH,
  CANVAS_HEIGHT,
  SCALE,
  CX0,
  CY0,
  FLOOR_DY,
  BG_HEX,
  SCENE_ITEMS,
  getSpritePivot,
  getTileDepthOffsetPx,
  computeLightDirView,
} from './sceneData.js';
import {
  SPRITE_VERTEX_SHADER,
  ALBEDO_FRAGMENT_SHADER,
  GBUFFER_FRAGMENT_SHADER,
  FULLSCREEN_VERTEX_SHADER,
  SHADOW_FRAGMENT_SHADER,
  COMPOSITE_FRAGMENT_SHADER,
} from './shaders.js';

// Parse URL query parameters for deterministic testing and screenshot automation
const params = new URLSearchParams(window.location.search);

const state = {
  // Same camera-relative orbit start as Sol 225° and Astra -135°.
  azimuth: params.has('azimuth') ? parseFloat(params.get('azimuth')) : 0.0,
  elevation: params.has('elevation') ? parseFloat(params.get('elevation')) : 38.0,
  shadowIntensity: params.has('intensity') ? parseFloat(params.get('intensity')) : 0.80,
  lightSoftness: params.has('softness') ? parseFloat(params.get('softness')) : 1.15,
  normalShading: params.has('normalShading') ? parseFloat(params.get('normalShading')) : 0.06,
  depthBias: params.has('depthBias') ? parseFloat(params.get('depthBias')) : 1.35,
  normalBias: params.has('normalBias') ? parseFloat(params.get('normalBias')) : 1.85,
  maxDistance: 230.0,
  renderMode: params.has('mode') ? parseInt(params.get('mode'), 10) : 0,
  showLogo: params.has('logo') ? params.get('logo') !== '0' : false,
  autoOrbit: params.get('orbit') === '1',
  hideUI: params.get('ui') === '0',
};

if (state.hideUI) {
  document.body.classList.add('headless-capture');
}

// Initialize WebGL2 Renderer
const canvas = document.getElementById('webgl-canvas');
const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: false,
  alpha: false,
  powerPreference: 'high-performance',
  preserveDrawingBuffer: true,
});
renderer.setSize(CANVAS_WIDTH, CANVAS_HEIGHT, false);
renderer.setPixelRatio(1);
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
renderer.autoClear = false;

// Orthographic camera matching sample.png (918x515)
const orthoCamera = new THREE.OrthographicCamera(
  0,
  CANVAS_WIDTH,
  CANVAS_HEIGHT,
  0,
  -1000,
  1000
);
orthoCamera.position.set(0, 0, 10);

// Render Targets for Multi-Pass Pipeline
const rtAlbedo = new THREE.WebGLRenderTarget(CANVAS_WIDTH, CANVAS_HEIGHT, {
  minFilter: THREE.NearestFilter,
  magFilter: THREE.NearestFilter,
  format: THREE.RGBAFormat,
  type: THREE.UnsignedByteType,
  depthBuffer: false,
});

const rtGeo = new THREE.WebGLRenderTarget(CANVAS_WIDTH, CANVAS_HEIGHT, {
  minFilter: THREE.NearestFilter,
  magFilter: THREE.NearestFilter,
  format: THREE.RGBAFormat,
  type: THREE.FloatType,
  depthBuffer: true,
});

const rtNormal = new THREE.WebGLRenderTarget(CANVAS_WIDTH, CANVAS_HEIGHT, {
  minFilter: THREE.NearestFilter,
  magFilter: THREE.NearestFilter,
  format: THREE.RGBAFormat,
  type: THREE.FloatType,
  depthBuffer: true,
});

const rtShadow = new THREE.WebGLRenderTarget(CANVAS_WIDTH, CANVAS_HEIGHT, {
  minFilter: THREE.NearestFilter,
  magFilter: THREE.NearestFilter,
  format: THREE.RGBAFormat,
  type: THREE.HalfFloatType,
  depthBuffer: false,
});

// Scenes for Pass 1A (Albedo), Pass 1B (G-Buffer), Pass 2 (Shadow Raymarching), Pass 3 (Composite)
const albedoScene = new THREE.Scene();
const geoScene = new THREE.Scene();
const shadowScene = new THREE.Scene();
const compositeScene = new THREE.Scene();
const postCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

const sharedGbufferMode = { value: 0 };

// Load an HTML Image
function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = (err) => reject(new Error(`Failed to load ${url}: ${err}`));
    img.src = url;
  });
}

// Create a pre-scaled 1:1 pixel CanvasTexture for Albedo
function createScaledAlbedoTexture(img, wSc, hSc) {
  const offCanvas = document.createElement('canvas');
  offCanvas.width = wSc;
  offCanvas.height = hSc;
  const ctx = offCanvas.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(img, 0, 0, wSc, hSc);

  const tex = new THREE.CanvasTexture(offCanvas);
  tex.minFilter = THREE.NearestFilter;
  tex.magFilter = THREE.NearestFilter;
  tex.colorSpace = THREE.NoColorSpace;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}

// Create a NearestFilter data texture for 16-bit RG Depth, Thickness, and Normal maps
function createNearestDataTexture(img) {
  const tex = new THREE.Texture(img);
  tex.minFilter = THREE.NearestFilter;
  tex.magFilter = THREE.NearestFilter;
  tex.colorSpace = THREE.NoColorSpace;
  tex.generateMipmaps = false;
  tex.flipY = true;
  tex.needsUpdate = true;
  return tex;
}

// Fullscreen Quad Pass 2 (Shadow Raymarching) & Pass 3 (Joint Bilateral Composite)
const resolutionVec = new THREE.Vector2(CANVAS_WIDTH, CANVAS_HEIGHT);
const lightDirVec = new THREE.Vector3(...computeLightDirView(state.azimuth, state.elevation));

const shadowMaterial = new THREE.ShaderMaterial({
  vertexShader: FULLSCREEN_VERTEX_SHADER,
  fragmentShader: SHADOW_FRAGMENT_SHADER,
  uniforms: {
    uGeoTex: { value: rtGeo.texture },
    uNormalTex: { value: rtNormal.texture },
    uResolution: { value: resolutionVec },
    uLightDirView: { value: lightDirVec },
    uLightSoftness: { value: state.lightSoftness },
    uDepthBias: { value: state.depthBias },
    uNormalBias: { value: state.normalBias },
    uMaxDistance: { value: state.maxDistance },
  },
  depthTest: false,
  depthWrite: false,
});
shadowScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), shadowMaterial));

const compositeMaterial = new THREE.ShaderMaterial({
  vertexShader: FULLSCREEN_VERTEX_SHADER,
  fragmentShader: COMPOSITE_FRAGMENT_SHADER,
  uniforms: {
    uAlbedoTex: { value: rtAlbedo.texture },
    uGeoTex: { value: rtGeo.texture },
    uNormalTex: { value: rtNormal.texture },
    uShadowTex: { value: rtShadow.texture },
    uLogoTex: { value: null },
    uResolution: { value: resolutionVec },
    uLightDirView: { value: lightDirVec },
    uShadowIntensity: { value: state.shadowIntensity },
    uNormalShading: { value: state.normalShading },
    uRenderMode: { value: state.renderMode },
    uShowLogo: { value: state.showLogo },
  },
  depthTest: false,
  depthWrite: false,
});
compositeScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), compositeMaterial));

async function buildScene() {
  // Collect unique tile names to load each asset bundle once
  const uniqueTiles = new Map();
  for (const item of SCENE_ITEMS) {
    if (!uniqueTiles.has(item.tileName)) {
      uniqueTiles.set(item.tileName, item.isAsset);
    }
  }

  const tileAssets = new Map();
  const loadPromises = [];

  for (const [tileName, isAsset] of uniqueTiles.entries()) {
    const albedoUrl = isAsset
      ? `assets/${tileName}.png`
      : `generated/scene_tiles/${tileName}.png`;
    const depthUrl = `generated/depth/${tileName}.png`;
    const thickUrl = `generated/thickness/${tileName}.png`;
    const normalUrl = `generated/normal/${tileName}.png`;

    loadPromises.push(
      Promise.all([
        loadImage(albedoUrl),
        loadImage(depthUrl),
        loadImage(thickUrl),
        loadImage(normalUrl),
      ]).then(([albedoImg, depthImg, thickImg, normalImg]) => {
        const wOrig = albedoImg.width;
        const hOrig = albedoImg.height;
        const wSc = Math.round(wOrig * SCALE);
        const hSc = Math.round(hOrig * SCALE);

        tileAssets.set(tileName, {
          wOrig,
          hOrig,
          wSc,
          hSc,
          albedoTex: createScaledAlbedoTexture(albedoImg, wSc, hSc),
          depthTex: createNearestDataTexture(depthImg),
          thickTex: createNearestDataTexture(thickImg),
          normalTex: createNearestDataTexture(normalImg),
        });
      })
    );
  }

  // Also load Kenney logo watermark
  loadPromises.push(
    loadImage('generated/scene_tiles/kenney_logo.png?v=3').then((logoImg) => {
      compositeMaterial.uniforms.uLogoTex.value = createNearestDataTexture(logoImg);
    })
  );

  await Promise.all(loadPromises);

  // Create sprite meshes for Pass 1A (Albedo) and Pass 1B (G-Buffer)
  SCENE_ITEMS.forEach((item, sortIndex) => {
    const bundle = tileAssets.get(item.tileName);
    const { wOrig, hOrig, wSc, hSc, albedoTex, depthTex, thickTex, normalTex } = bundle;
    const { cxOrig, cyOrig } = getSpritePivot(item.tileName, wOrig, hOrig);

    const cxScreen = CX0 + (item.u + item.v) * 52.0;
    const cyScreen = CY0 + (item.u - item.v) * 26.0 - item.zStory * FLOOR_DY;

    const px0 = Math.round(cxScreen - cxOrig * SCALE);
    const py0 = Math.round(cyScreen - cyOrig * SCALE);

    // Center of sprite quad in OrthographicCamera(0, 918, 515, 0)
    const quadX = px0 + wSc * 0.5;
    const quadY = CANVAS_HEIGHT - (py0 + hSc * 0.5);

    const geom = new THREE.PlaneGeometry(wSc, hSc);

    // Pass 1A: Albedo mesh (painter's order with alpha blending)
    const albedoMat = new THREE.ShaderMaterial({
      vertexShader: SPRITE_VERTEX_SHADER,
      fragmentShader: ALBEDO_FRAGMENT_SHADER,
      uniforms: {
        uAlbedoMap: { value: albedoTex },
      },
      transparent: true,
      depthTest: false,
      depthWrite: false,
    });
    const albedoMesh = new THREE.Mesh(geom, albedoMat);
    albedoMesh.position.set(quadX, quadY, 0);
    albedoMesh.renderOrder = sortIndex;
    albedoScene.add(albedoMesh);

    // Pass 1B: G-Buffer mesh (per-pixel gl_FragDepth sorting)
    const tileDepthOffset = getTileDepthOffsetPx(item.u, item.v, item.zStory);
    const isBuilding = item.tileName.startsWith('buildingTiles_') ? 1.0 : 0.0;

    const geoMat = new THREE.ShaderMaterial({
      vertexShader: SPRITE_VERTEX_SHADER,
      fragmentShader: GBUFFER_FRAGMENT_SHADER,
      uniforms: {
        uAlbedoMap: { value: albedoTex },
        uDepthMap: { value: depthTex },
        uThicknessMap: { value: thickTex },
        uNormalMap: { value: normalTex },
        uTileDepthOffset: { value: tileDepthOffset },
        uSortIndex: { value: sortIndex },
        uIsBuilding: { value: isBuilding },
        uGbufferMode: sharedGbufferMode,
      },
      transparent: false,
      depthTest: true,
      depthWrite: true,
      depthFunc: THREE.LessEqualDepth,
    });
    const geoMesh = new THREE.Mesh(geom, geoMat);
    geoMesh.position.set(quadX, quadY, 0);
    geoMesh.renderOrder = sortIndex;
    geoScene.add(geoMesh);
  });

  const statusEl = document.getElementById('loading-status');
  if (statusEl) statusEl.style.display = 'none';

  renderFrame();
  window.__SCENE_READY__ = true;
}

function updateUniforms() {
  const [lx, ly, lz] = computeLightDirView(state.azimuth, state.elevation);
  lightDirVec.set(lx, ly, lz);

  shadowMaterial.uniforms.uLightSoftness.value = state.lightSoftness;
  shadowMaterial.uniforms.uDepthBias.value = state.depthBias;
  shadowMaterial.uniforms.uNormalBias.value = state.normalBias;

  compositeMaterial.uniforms.uShadowIntensity.value = state.shadowIntensity;
  compositeMaterial.uniforms.uNormalShading.value = state.normalShading;
  compositeMaterial.uniforms.uRenderMode.value = state.renderMode;
  compositeMaterial.uniforms.uShowLogo.value = state.showLogo;

  // Update sun compass widget in UI if visible
  const sunDot = document.getElementById('sun-dot');
  if (sunDot) {
    const rad = (state.azimuth * Math.PI) / 180.0;
    const rPx = (1.0 - state.elevation / 90.0) * 26.0;
    const dx = Math.sin(rad) * rPx;
    const dy = -Math.cos(rad) * rPx;
    sunDot.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
  }
}

function renderFrame() {
  updateUniforms();

  // Pass 1A: Render Albedo Scene
  const skyColor = new THREE.Color().setRGB(63 / 255, 124 / 255, 182 / 255, THREE.LinearSRGBColorSpace);
  renderer.setRenderTarget(rtAlbedo);
  renderer.setClearColor(skyColor, 1.0);
  renderer.clear(true, true, false);
  renderer.render(albedoScene, orthoCamera);

  // Pass 1B (0): Render Unified Depth & Thickness G-Buffer
  sharedGbufferMode.value = 0;
  renderer.setRenderTarget(rtGeo);
  renderer.setClearColor(0x000000, 0.0);
  renderer.clear(true, true, false);
  renderer.render(geoScene, orthoCamera);

  // Pass 1B (1): Render Unified View-Space Normal G-Buffer
  sharedGbufferMode.value = 1;
  renderer.setRenderTarget(rtNormal);
  renderer.setClearColor(0x000000, 0.0);
  renderer.clear(true, true, false);
  renderer.render(geoScene, orthoCamera);

  // Pass 2: Screen-Space Volumetric Shadow Raymarching
  renderer.setRenderTarget(rtShadow);
  renderer.setClearColor(0xffffff, 1.0);
  renderer.clear(true, false, false);
  renderer.render(shadowScene, postCamera);

  // Pass 3: Joint Bilateral Filter + Final Composite to Screen
  renderer.setRenderTarget(null);
  renderer.setClearColor(skyColor, 1.0);
  renderer.clear(true, true, false);
  renderer.render(compositeScene, postCamera);
}

// Setup UI Controls
function setupUI() {
  const bindSlider = (id, valId, key, suffix = '') => {
    const input = document.getElementById(id);
    const valSpan = document.getElementById(valId);
    if (!input) return;
    input.value = state[key];
    if (valSpan) valSpan.textContent = `${Number(state[key]).toFixed(suffix === '°' ? 0 : 2)}${suffix}`;
    input.addEventListener('input', (e) => {
      state[key] = parseFloat(e.target.value);
      if (valSpan) valSpan.textContent = `${Number(state[key]).toFixed(suffix === '°' ? 0 : 2)}${suffix}`;
      renderFrame();
    });
  };

  bindSlider('ctrl-azimuth', 'val-azimuth', 'azimuth', '°');
  bindSlider('ctrl-elevation', 'val-elevation', 'elevation', '°');
  bindSlider('ctrl-intensity', 'val-intensity', 'shadowIntensity', '');
  bindSlider('ctrl-softness', 'val-softness', 'lightSoftness', '');
  bindSlider('ctrl-normal-shading', 'val-normal-shading', 'normalShading', '');

  const modeSelect = document.getElementById('ctrl-mode');
  if (modeSelect) {
    modeSelect.value = String(state.renderMode);
    modeSelect.addEventListener('change', (e) => {
      state.renderMode = parseInt(e.target.value, 10);
      renderFrame();
    });
  }

  const logoCheck = document.getElementById('ctrl-logo');
  if (logoCheck) {
    logoCheck.checked = state.showLogo;
    logoCheck.addEventListener('change', (e) => {
      state.showLogo = e.target.checked;
      renderFrame();
    });
  }

  const orbitCheck = document.getElementById('ctrl-orbit');
  if (orbitCheck) {
    orbitCheck.checked = state.autoOrbit;
    orbitCheck.addEventListener('change', (e) => {
      state.autoOrbit = e.target.checked;
    });
  }

  // Preset lighting buttons
  document.querySelectorAll('[data-preset]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const [az, el, soft] = btn.dataset.preset.split(',').map(Number);
      state.azimuth = az;
      state.elevation = el;
      state.lightSoftness = soft;
      state.autoOrbit = false;
      if (orbitCheck) orbitCheck.checked = false;

      const azIn = document.getElementById('ctrl-azimuth');
      const elIn = document.getElementById('ctrl-elevation');
      const sfIn = document.getElementById('ctrl-softness');
      if (azIn) azIn.value = az;
      if (elIn) elIn.value = el;
      if (sfIn) sfIn.value = soft;
      document.getElementById('val-azimuth').textContent = `${az}°`;
      document.getElementById('val-elevation').textContent = `${el}°`;
      document.getElementById('val-softness').textContent = soft.toFixed(2);
      renderFrame();
    });
  });
}

let lastTime = performance.now();
function animate(now) {
  requestAnimationFrame(animate);
  const dt = (now - lastTime) * 0.001;
  lastTime = now;

  if (state.autoOrbit && window.__SCENE_READY__) {
    state.azimuth = ((state.azimuth + dt * 22.0 + 180.0) % 360.0) - 180.0;
    const azIn = document.getElementById('ctrl-azimuth');
    const azVal = document.getElementById('val-azimuth');
    if (azIn) azIn.value = state.azimuth;
    if (azVal) azVal.textContent = `${Math.round(state.azimuth)}°`;
    renderFrame();
  }
}

setupUI();
buildScene().catch((err) => {
  console.error(err);
  const statusEl = document.getElementById('loading-status');
  if (statusEl) statusEl.textContent = 'ERROR: ' + (err && err.message ? err.message : String(err));
});
requestAnimationFrame(animate);
