precision highp float;

uniform sampler2D uColor;
uniform sampler2D uFront;
uniform sampler2D uBack;
uniform sampler2D uNormal;
uniform sampler2D uInterval0;
uniform sampler2D uInterval1;
uniform sampler2D uInterval2;
uniform sampler2D uInterval3;
uniform sampler2D uInterval4;
uniform sampler2D uInterval5;
uniform sampler2D uInterval6;
uniform sampler2D uInterval7;
uniform vec2 uResolution;
uniform vec3 uRight;
uniform vec3 uUp;
uniform vec3 uForward;
uniform vec3 uOrigin;
uniform vec3 uLight;
uniform vec3 uBackground;
uniform float uDepthMin;
uniform float uDepthRange;
uniform float uPixelsPerUnit;
uniform float uMaxHeight;
uniform float uSoftness;
uniform float uStrength;
uniform bool uShadows;
uniform int uView;
varying vec2 vUv;

float decodeDepth(vec2 packed) {
  return dot(packed, vec2(65280.0, 255.0)) / 65535.0 * uDepthRange + uDepthMin;
}

// An interval is solid only between its two measured boundary depths.
// Empty texels use front >= back, including the all-zero texture border.
// -1: no hit is possible in this or a later interval; 0: continue; 1: hit.
float intervalHit(vec4 packed, float rayMin, float rayMax) {
  float front = decodeDepth(packed.rg);
  float back = decodeDepth(packed.ba);
  float epsilon = min(0.006, (back - front) * 0.2);
  if (back <= front || rayMax <= front + epsilon) return -1.0;
  return float(rayMin < back - epsilon);
}

float occupied(vec2 uv, float rayMin, float rayMax) {
  float hit = intervalHit(texture2D(uInterval0, uv), rayMin, rayMax);
  if (hit != 0.0) return max(hit, 0.0);
  hit = intervalHit(texture2D(uInterval1, uv), rayMin, rayMax);
  if (hit != 0.0) return max(hit, 0.0);
  hit = intervalHit(texture2D(uInterval2, uv), rayMin, rayMax);
  if (hit != 0.0) return max(hit, 0.0);
  hit = intervalHit(texture2D(uInterval3, uv), rayMin, rayMax);
  if (hit != 0.0) return max(hit, 0.0);
  hit = intervalHit(texture2D(uInterval4, uv), rayMin, rayMax);
  if (hit != 0.0) return max(hit, 0.0);
  hit = intervalHit(texture2D(uInterval5, uv), rayMin, rayMax);
  if (hit != 0.0) return max(hit, 0.0);
  hit = intervalHit(texture2D(uInterval6, uv), rayMin, rayMax);
  if (hit != 0.0) return max(hit, 0.0);
  return max(intervalHit(texture2D(uInterval7, uv), rayMin, rayMax), 0.0);
}

// Orthographic projection makes the projected world-space ray linear in UV
// and camera depth. The depth segment at every step avoids tunneling through
// thin walls. Ordered solid intervals allow early exits before deeper layers.
float traceShadow(vec2 originUv, float originDepth, vec3 normal, vec3 light) {
  vec3 offset = normal * 0.012 + light * 0.018;
  vec2 uv = originUv + vec2(dot(offset, uRight), dot(offset, uUp)) * uPixelsPerUnit / uResolution;
  float depth = originDepth + dot(offset, uForward);
  vec2 planePosition = (originUv - 0.5) * uResolution / uPixelsPerUnit;
  float startWorldZ = uOrigin.z + uRight.z * planePosition.x + uUp.z * planePosition.y + uForward.z * originDepth + offset.z;
  float traceDistance = max(0.0, (uMaxHeight - startWorldZ) / max(light.z, 0.001));
  if (traceDistance <= 0.0) return 0.0;
  vec2 projected = vec2(dot(light, uRight), dot(light, uUp)) * uPixelsPerUnit;
  float depthStep = dot(light, uForward);
  float stepWorld = max(0.7 / max(length(projected), 1.0), traceDistance / 192.0);
  vec2 uvStep = projected * stepWorld / uResolution;
  float dd = depthStep * stepWorld;
  float halfDepthStep = abs(dd) * 0.48;
  for (int i = 0; i < 192; i++) {
    if ((float(i) + 1.0) * stepWorld > traceDistance) break;
    uv += uvStep;
    depth += dd;
    if (uv.x <= 0.0 || uv.x >= 1.0 || uv.y <= 0.0 || uv.y >= 1.0) break;
    if (depth < uDepthMin || depth > uDepthMin + uDepthRange) break;
    if (occupied(uv, depth - halfDepthStep, depth + halfDepthStep) > 0.5) return 1.0;
  }
  return 0.0;
}

float shadowAmount(vec2 uv, float depth, vec3 normal) {
  if (!uShadows) return 0.0;
  if (uSoftness < 0.01) return traceShadow(uv, depth, normal, uLight);
  vec3 tangent = normalize(cross(uLight, vec3(0.0, 0.0, 1.0)));
  vec3 bitangent = cross(uLight, tangent);
  // Three deterministic cone samples. A fixed per-pixel rotation prevents
  // repeated band contours while keeping paused/capture frames identical.
  float angle = fract(sin(dot(floor(uv * uResolution), vec2(12.9898, 78.233))) * 43758.5453) * 6.2831853;
  float cone = uSoftness * 0.035;
  float shadow = 0.0;
  for (int i = 0; i < 3; i++) {
    float a = angle + float(i) * 2.0943951;
    vec3 sampleLight = normalize(uLight + cone * (cos(a) * tangent + sin(a) * bitangent));
    shadow += traceShadow(uv, depth, normal, sampleLight);
  }
  return shadow / 3.0;
}

void main() {
  vec4 sprite = texture2D(uColor, vUv);
  vec4 front = texture2D(uFront, vUv);
  vec3 outputColor = uBackground;
  if (sprite.a > 0.001) {
    float depth = decodeDepth(front.rg);
    vec3 normal = normalize(texture2D(uNormal, vUv).rgb * 2.0 - 1.0);
    float shadow = 0.0;
    if (front.a > 0.5 && (uView == 0 || uView == 5)) shadow = shadowAmount(vUv, depth, normal);
    vec3 surface = sprite.rgb;
    if (uView == 0) {
      // The supplied art is pre-shaded; preserve its color and add only a
      // dynamic direct-light visibility term instead of relighting it twice.
      surface *= 1.0 - shadow * uStrength;
    } else if (uView == 2) {
      float d = clamp((depth - uDepthMin) / uDepthRange, 0.0, 1.0);
      surface = mix(vec3(0.04, 0.09, 0.19), vec3(0.65, 0.89, 1.0), 1.0 - d);
    } else if (uView == 3) {
      float thickness = max(0.0, decodeDepth(texture2D(uBack, vUv).rg) - depth);
      float t = clamp(thickness / 3.0, 0.0, 1.0);
      surface = mix(vec3(0.04, 0.13, 0.22), vec3(0.08, 0.68, 0.64), min(t * 2.0, 1.0));
      surface = mix(surface, vec3(1.0, 0.64, 0.19), max(t * 2.0 - 1.0, 0.0));
    } else if (uView == 4) {
      surface = normal * 0.5 + 0.5;
    } else if (uView == 5) {
      surface = vec3(1.0 - shadow);
    }
    if (uView >= 2 && front.a < 0.5) surface = uBackground;
    outputColor = mix(uBackground, surface, sprite.a);
  }
  gl_FragColor = vec4(outputColor, 1.0);
  #include <colorspace_fragment>
}
