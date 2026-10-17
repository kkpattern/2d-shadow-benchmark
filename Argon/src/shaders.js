// GLSL Shaders for 2.5D Isometric Unified G-Buffer & Volumetric Screen-Space Shadow Raymarching

export const SPRITE_VERTEX_SHADER = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const ALBEDO_FRAGMENT_SHADER = /* glsl */ `
  uniform sampler2D uAlbedoMap;
  varying vec2 vUv;

  void main() {
    vec4 texColor = texture2D(uAlbedoMap, vUv);
    if (texColor.a < 0.01) discard;
    gl_FragColor = texColor;
  }
`;

export const GBUFFER_FRAGMENT_SHADER = /* glsl */ `
  uniform sampler2D uAlbedoMap;
  uniform sampler2D uDepthMap;
  uniform sampler2D uThicknessMap;
  uniform sampler2D uNormalMap;
  uniform float uTileDepthOffset;
  uniform float uSortIndex;
  uniform float uIsBuilding;
  uniform int uGbufferMode; // 0 = Geo (zSceneFrontPx, thicknessPx, zLocalPx, 1.0), 1 = Normal (normalView, isBuilding)

  varying vec2 vUv;

  void main() {
    vec4 albedo = texture2D(uAlbedoMap, vUv);
    if (albedo.a < 0.25) discard;

    vec4 dTex = texture2D(uDepthMap, vUv);
    vec4 tTex = texture2D(uThicknessMap, vUv);
    vec4 nTex = texture2D(uNormalMap, vUv);

    // Decode 16-bit big-endian (R = high byte, G = low byte) local depth in sample.png pixel units
    float val16D = floor(dTex.r * 255.0 + 0.5) * 256.0 + floor(dTex.g * 255.0 + 0.5);
    float zLocalPx = (val16D / 65535.0) * 256.0 - 128.0;
    float zSceneFrontPx = zLocalPx + uTileDepthOffset;

    // Decode 16-bit component-local thickness in sample.png pixel units
    float val16T = floor(tTex.r * 255.0 + 0.5) * 256.0 + floor(tTex.g * 255.0 + 0.5);
    float thicknessPx = (val16T / 65535.0) * 128.0;

    // Decode camera view-space unit normal
    vec3 normalView = normalize(nTex.rgb * 2.0 - 1.0);

    // Hardware per-pixel depth sorting with tie-breaker for overlapping ground tiles & stacked floors
    float zSort = zSceneFrontPx + uSortIndex * 0.12;
    gl_FragDepth = clamp(0.5 - zSort / 1000.0, 0.001, 0.999);

    if (uGbufferMode == 0) {
      gl_FragColor = vec4(zSceneFrontPx, thicknessPx, zLocalPx, 1.0);
    } else {
      gl_FragColor = vec4(normalView, uIsBuilding);
    }
  }
`;

export const FULLSCREEN_VERTEX_SHADER = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

// Pass 2: Volumetric Screen-Space Shadow Raymarching with Vogel Disk Penumbra & Half-Space Self-Occlusion Rejection
export const SHADOW_FRAGMENT_SHADER = /* glsl */ `
  precision highp float;

  uniform sampler2D uGeoTex;
  uniform sampler2D uNormalTex;
  uniform vec2 uResolution;
  uniform vec3 uLightDirView;
  uniform float uLightSoftness;
  uniform float uDepthBias;
  uniform float uNormalBias;
  uniform float uMaxDistance;

  varying vec2 vUv;

  // Interleaved Gradient Noise (Jimenez 2014)
  float ign(vec2 pixelCoord) {
    vec3 magic = vec3(0.06711056, 0.00583715, 52.9829189);
    return fract(magic.z * fract(dot(pixelCoord, magic.xy)));
  }

  // Golden-angle Vogel disk sample for soft shadow cone
  vec2 vogelDiskSample(int sampleIndex, int samplesCount, float phi) {
    float r = sqrt((float(sampleIndex) + 0.5) / float(samplesCount));
    float theta = float(sampleIndex) * 2.399963229728653 + phi;
    return vec2(cos(theta), sin(theta)) * r;
  }

  void main() {
    vec4 geo0 = texture2D(uGeoTex, vUv);
    if (geo0.a < 0.5) {
      gl_FragColor = vec4(1.0, 0.0, 0.0, 0.0);
      return;
    }

    vec4 norm0Sample = texture2D(uNormalTex, vUv);
    vec3 normal0 = normalize(norm0Sample.rgb);
    float z0 = geo0.r;
    vec2 pixelXY = vUv * uResolution;

    // Build orthonormal tangent basis perpendicular to uLightDirView for soft shadow cone sampling
    vec3 L = normalize(uLightDirView);
    vec3 upGuide = abs(L.z) < 0.9 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 T1 = normalize(cross(upGuide, L));
    vec3 T2 = cross(L, T1);

    float noise = ign(gl_FragCoord.xy);
    float rotAngle = noise * 6.28318530718;
    float coneTan = uLightSoftness * 0.015;

    // Displace ray start slightly along the receiver's 3D normal
    vec3 startPos = vec3(pixelXY, z0) + normal0 * (uNormalBias * 0.85);

    const int NUM_RAYS = 8;
    const int MAX_STEPS = 112;
    float occlusionSum = 0.0;
    float hitDistSum = 0.0;
    float hitCount = 0.0;

    for (int r = 0; r < NUM_RAYS; r++) {
      vec2 disk = vogelDiskSample(r, NUM_RAYS, rotAngle);
      vec3 rayDir = normalize(L + (T1 * disk.x + T2 * disk.y) * coneTan);

      float t = 1.6 + noise * 1.1;
      float rayHit = 0.0;
      float rayHitDist = 0.0;

      for (int s = 0; s < MAX_STEPS; s++) {
        if (t > uMaxDistance) break;

        vec3 rayPos = startPos + rayDir * t;
        vec2 sampleUV = rayPos.xy / uResolution;

        // Stop if ray exits screen viewport
        if (sampleUV.x < 0.001 || sampleUV.x > 0.999 || sampleUV.y < 0.001 || sampleUV.y > 0.999) {
          break;
        }

        vec4 sGeo = texture2D(uGeoTex, sampleUV);
        if (sGeo.a > 0.5) {
          float zFrontSample = sGeo.r;
          float thicknessSample = sGeo.g;
          float penetration = zFrontSample - rayPos.z;

          // Volumetric interval check: ray is behind front surface and within finite component thickness
          if (penetration > uDepthBias && penetration < thicknessSample) {
            // Half-space self-occlusion check: the occluder's front surface must protrude
            // outward past the receiver's tangent plane (dot(P_sample - P_0, normal0) > threshold)
            vec3 diffFront = vec3(rayPos.xy - pixelXY, zFrontSample - z0);
            float outwardDist = dot(diffFront, normal0);

            if (outwardDist > uNormalBias) {
              // Smooth contact fade on ultra-thin grazing overlaps
              float edgeWeight = smoothstep(uDepthBias, uDepthBias + 1.2, penetration) *
                                 smoothstep(thicknessSample, thicknessSample - 1.2, penetration);
              rayHit = max(rayHit, clamp(edgeWeight, 0.35, 1.0));
              if (rayHit > 0.5) {
                rayHitDist = t;
                break;
              }
            }
          }
        }

        // Adaptive step size: fine 1.1px steps near contact, gradually increasing with distance
        t += 1.15 + 0.008 * t;
      }

      occlusionSum += rayHit;
      if (rayHit > 0.0) {
        hitDistSum += rayHitDist;
        hitCount += 1.0;
      }
    }

    float visibility = 1.0 - (occlusionSum / float(NUM_RAYS));
    float avgBlockerDist = hitCount > 0.0 ? (hitDistSum / hitCount) : 0.0;
    gl_FragColor = vec4(visibility, avgBlockerDist / uMaxDistance, 0.0, 1.0);
  }
`;

// Pass 3: Joint Bilateral (Depth & Normal Edge-Preserving) Filter + Final Shading & Debug Modes
export const COMPOSITE_FRAGMENT_SHADER = /* glsl */ `
  precision highp float;

  uniform sampler2D uAlbedoTex;
  uniform sampler2D uGeoTex;
  uniform sampler2D uNormalTex;
  uniform sampler2D uShadowTex;
  uniform sampler2D uLogoTex;

  uniform vec2 uResolution;
  uniform vec3 uLightDirView;
  uniform float uShadowIntensity;
  uniform float uNormalShading;
  uniform int uRenderMode; // 0=Shadowed, 1=Unshadowed, 2=RawShadow, 3=Depth, 4=Thickness, 5=Normal
  uniform bool uShowLogo;

  varying vec2 vUv;

  void main() {
    vec4 albedo = texture2D(uAlbedoTex, vUv);
    vec4 geo = texture2D(uGeoTex, vUv);
    vec4 normSample = texture2D(uNormalTex, vUv);
    vec3 normal0 = normalize(normSample.rgb);
    float valid = geo.a;

    // Exact sample.png sky background color [63, 124, 182]
    vec3 skyBg = vec3(63.0 / 255.0, 124.0 / 255.0, 182.0 / 255.0);
    vec3 baseRgb = mix(skyBg, albedo.rgb, albedo.a);

    // Optional Kenney logo watermark in bottom-left (x: 15..315, y_down: 410..490)
    vec4 logoColor = vec4(0.0);
    if (uShowLogo) {
      vec2 px = vec2(vUv.x * uResolution.x, (1.0 - vUv.y) * uResolution.y);
      if (px.x >= 15.0 && px.x <= 315.0 && px.y >= 410.0 && px.y <= 490.0) {
        vec2 logoUv = vec2((px.x - 15.0) / 300.0, 1.0 - (px.y - 410.0) / 80.0);
        logoColor = texture2D(uLogoTex, logoUv);
      }
    }

    // Mode 1: Unshadowed Albedo (1:1 match with sample.png)
    if (uRenderMode == 1) {
      vec3 col = mix(baseRgb, logoColor.rgb, logoColor.a);
      gl_FragColor = vec4(col, 1.0);
      return;
    }

    // Mode 3: Unified Scene Front Depth Visualization
    if (uRenderMode == 3) {
      if (valid < 0.5) {
        gl_FragColor = vec4(0.05, 0.07, 0.10, 1.0);
        return;
      }
      float dNorm = clamp((geo.r + 185.0) / 380.0, 0.0, 1.0);
      vec3 dCol = vec3(dNorm, sin(dNorm * 3.14159265) * 0.82, 1.0 - dNorm);
      gl_FragColor = vec4(dCol, 1.0);
      return;
    }

    // Mode 4: Component-Local Thickness Visualization
    if (uRenderMode == 4) {
      if (valid < 0.5) {
        gl_FragColor = vec4(0.05, 0.07, 0.10, 1.0);
        return;
      }
      float tNorm = clamp(geo.g / 85.0, 0.0, 1.0);
      vec3 tCol = vec3(tNorm, sqrt(tNorm) * 0.78, tNorm * tNorm);
      gl_FragColor = vec4(tCol, 1.0);
      return;
    }

    // Mode 5: View-Space Normal Map Visualization
    if (uRenderMode == 5) {
      if (valid < 0.5) {
        gl_FragColor = vec4(0.05, 0.07, 0.10, 1.0);
        return;
      }
      gl_FragColor = vec4(normal0 * 0.5 + 0.5, 1.0);
      return;
    }

    // Joint Bilateral Filter on uShadowTex (5x5 kernel preserving 3D depth & normal edges)
    float filteredVis = 1.0;
    if (valid > 0.5) {
      float z0 = geo.r;
      vec2 texel = 1.0 / uResolution;
      float sumVis = 0.0;
      float sumWeight = 0.0;

      for (int dy = -2; dy <= 2; dy++) {
        for (int dx = -2; dx <= 2; dx++) {
          vec2 offset = vec2(float(dx), float(dy)) * texel;
          vec2 tapUV = vUv + offset;
          vec4 tapGeo = texture2D(uGeoTex, tapUV);
          if (tapGeo.a > 0.5) {
            vec3 tapNorm = normalize(texture2D(uNormalTex, tapUV).rgb);
            float tapVis = texture2D(uShadowTex, tapUV).r;

            float spatialW = exp(-float(dx * dx + dy * dy) / 4.5);
            float depthW = exp(-abs(tapGeo.r - z0) / 2.5);
            float normW = pow(max(0.0, dot(normal0, tapNorm)), 8.0);
            float w = spatialW * depthW * normW;

            sumVis += tapVis * w;
            sumWeight += w;
          }
        }
      }
      filteredVis = sumWeight > 1e-4 ? (sumVis / sumWeight) : texture2D(uShadowTex, vUv).r;
    }

    // Mode 2: Raw/Filtered Shadow Mask Visualization
    if (uRenderMode == 2) {
      if (valid < 0.5) {
        gl_FragColor = vec4(0.12, 0.15, 0.20, 1.0);
        return;
      }
      gl_FragColor = vec4(vec3(filteredVis), 1.0);
      return;
    }

    // Mode 0: Final Shadowed Scene with Cool Sky Ambient Tint & Dynamic Normal Shading
    vec3 finalColor = baseRgb;
    if (valid > 0.5) {
      vec3 L = normalize(uLightDirView);
      float NdotL = dot(normal0, L);

      // Self-facing shade for vertical walls oriented away from the dynamic light source
      float selfFacing = smoothstep(-0.22, 0.12, NdotL);
      float combinedVis = filteredVis * mix(0.66, 1.0, selfFacing);

      // Cool sky-tinted shadow multiplier + warm sunlight highlight
      vec3 shadowTint = vec3(0.42, 0.50, 0.64);
      vec3 sunLightTint = vec3(1.02, 1.01, 0.99);
      vec3 lightFactor = mix(mix(vec3(1.0), shadowTint, uShadowIntensity), sunLightTint, combinedVis);

      // Subtle dynamic normal-map directional modulation
      float lambertDelta = (max(0.0, NdotL) - 0.55) * uNormalShading;
      vec3 litRgb = clamp(albedo.rgb * lightFactor + lambertDelta * combinedVis, 0.0, 1.0);
      finalColor = mix(skyBg, litRgb, albedo.a);
    }

    finalColor = mix(finalColor, logoColor.rgb, logoColor.a);
    gl_FragColor = vec4(finalColor, 1.0);
  }
`;
