export const vertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

// Depth is linear and increases TOWARD the camera. Each layer is a disjoint,
// solid [back, front] interval, not a front surface with an arbitrary epsilon.
export const shadowShader = /* glsl */ `
  precision highp float;
  precision highp sampler2DArray;
  uniform sampler2DArray uIntervals;
  uniform sampler2D uNormals;
  uniform vec2 uSize;
  uniform vec2 uDepthRange;
  uniform vec3 uSun;
  uniform float uSoftness;
  uniform float uEnabled;
  varying vec2 vUv;

  float traceSun(vec3 receiver, vec3 direction, float receiverId, vec3 normal) {
    vec3 start = receiver + normal * 0.8;
    vec2 cell = floor(start.xy);
    vec2 increment = sign(direction.xy);
    vec2 deltaT = vec2(1.0) / max(abs(direction.xy), vec2(1e-8));
    vec2 boundary = cell + max(increment, vec2(0.0));
    vec2 nextT = abs(boundary - start.xy) * deltaT;
    if (abs(direction.x) < 1e-8) nextT.x = 1e20;
    if (abs(direction.y) < 1e-8) nextT.y = 1e20;
    float endT = 2400.0;
    if (direction.z > 1e-6) endT = max(0.0, (uDepthRange.y + 2.0 - start.z) / direction.z);
    if (direction.z < -1e-6) endT = max(0.0, (uDepthRange.x - 2.0 - start.z) / direction.z);
    float entryT = 0.0;
    // Exact grid traversal: visit every crossed texel and test only the ray
    // segment inside THAT texel. W+H is a strict bound on a screen crossing.
    for (int i = 0; i < 1440; ++i) {
      if (any(lessThan(cell, vec2(0.0))) || any(greaterThanEqual(cell, uSize))) break;
      float exitT = min(min(nextT.x, nextT.y), endT);
      vec2 uv = (cell + 0.5) / uSize;
      for (int layer = 0; layer < 4; ++layer) {
        vec4 interval = texture(uIntervals, vec3(uv, float(layer)));
        if (interval.w < 0.5) continue;
        // Only skip immediate self-contact, never the entire object.
        float clippedEntry = abs(interval.z - receiverId) < 0.25 ? max(entryT, 3.2) : entryT;
        if (clippedEntry >= exitT) continue;
        float a = start.z + direction.z * clippedEntry;
        float b = start.z + direction.z * exitT;
        float rayNear = max(a, b);
        float rayFar = min(a, b);
        float thickness = interval.x - interval.y;
        if (thickness < 0.00001) continue;
        float erosion = min(0.25, thickness * 0.1);
        if (rayNear >= interval.y + erosion && rayFar <= interval.x - erosion) return 1.0;
      }
      if (exitT >= endT) break;
      // At a grid corner advance BOTH axes; use pre-update boundary times.
      bool crossX = nextT.x <= nextT.y;
      bool crossY = nextT.y <= nextT.x;
      entryT = exitT;
      if (crossX) { cell.x += increment.x; nextT.x += deltaT.x; }
      if (crossY) { cell.y += increment.y; nextT.y += deltaT.y; }
    }
    // Screen-space rays that exit the bake or exhaust the budget are unoccluded.
    return 0.0;
  }

  void main() {
    vec2 bufferUv = vec2(vUv.x, 1.0 - vUv.y);
    vec4 front = texture(uIntervals, vec3(bufferUv, 0.0));
    if (front.w < 0.5 || uEnabled < 0.5) { gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0); return; }
    vec3 normal = normalize(texture(uNormals, bufferUv).xyz);
    vec3 receiver = vec3(bufferUv * uSize, front.x);
    float shadow;
    if (uSoftness < 0.001) {
      shadow = traceSun(receiver, uSun, front.z, normal);
    } else {
      // Stable area-source quadrature. No random/temporal noise or history buffer.
      vec3 tangent = normalize(cross(uSun, abs(uSun.z) < 0.9 ? vec3(0,0,1) : vec3(0,1,0)));
      vec3 bitangent = cross(uSun, tangent);
      float radius = tan(uSoftness);
      shadow = traceSun(receiver, normalize(uSun + tangent * radius * 0.65), front.z, normal);
      shadow += traceSun(receiver, normalize(uSun + (-tangent * 0.5 + bitangent * 0.866) * radius * 0.65), front.z, normal);
      shadow += traceSun(receiver, normalize(uSun + (-tangent * 0.5 - bitangent * 0.866) * radius * 0.65), front.z, normal);
      shadow /= 3.0;
    }
    gl_FragColor = vec4(shadow, shadow, shadow, 1.0);
  }
`;

export const compositeShader = /* glsl */ `
  precision highp float;
  precision highp sampler2DArray;
  uniform sampler2D uColor;
  uniform sampler2D uShadow;
  uniform sampler2D uNormals;
  uniform sampler2DArray uIntervals;
  uniform float uStrength;
  uniform float uEnabled;
  uniform int uView;
  uniform vec2 uDepthRange;
  varying vec2 vUv;
  void main() {
    vec2 bufferUv = vec2(vUv.x, 1.0 - vUv.y);
    vec4 front = texture(uIntervals, vec3(bufferUv, 0.0));
    vec3 color = texture(uColor, vUv).rgb;
    float shadow = texture(uShadow, vUv).r;
    // Proxy silhouettes are approximate. Never spill an occlusion onto the
    // uniform blue backdrop beyond the source artwork's actual silhouette.
    if (distance(color, vec3(63.0,124.0,182.0) / 255.0) < 0.004) shadow = 0.0;
    if (uView == 1) {
      float depth = clamp((front.x - uDepthRange.x) / (uDepthRange.y - uDepthRange.x), 0.0, 1.0);
      color = mix(vec3(0.065,0.12,0.17), vec3(depth), front.w);
    } else if (uView == 2) {
      float thickness = clamp((front.x - front.y) / 110.0, 0.0, 1.0);
      vec3 heat = mix(vec3(0.12,0.36,0.43), vec3(0.94,0.71,0.40), thickness);
      color = mix(vec3(0.065,0.12,0.17), heat, front.w);
    } else if (uView == 3) {
      vec4 normal = texture(uNormals, bufferUv);
      color = mix(vec3(0.065,0.12,0.17), normal.xyz * 0.5 + 0.5, normal.w);
    } else if (uView == 4) {
      color = mix(vec3(0.065,0.12,0.17), vec3(1.0 - shadow * 0.85), front.w);
    } else {
      // Sprite colors already contain stylized face shading. Preserve that art;
      // only multiply new, dynamic cast shadows. Work in the original sRGB art.
      color *= mix(vec3(1.0), vec3(0.62,0.72,0.83), shadow * uStrength * uEnabled);
      color *= 1.0 - shadow * uStrength * uEnabled * 0.52;
    }
    gl_FragColor = vec4(color, 1.0);
  }
`;
