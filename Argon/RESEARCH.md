# Screen-Space Raymarching Shadow Rendering for 2.5D Isometric Scenes

## 1. Overview & Problem Statement

Recreating a 2D isometric tile scene (such as `sample.png` from Kenney's *Isometric Buildings* pack) with realistic dynamic global shadows presents a fundamental geometric challenge: each asset in `assets/buildingTiles_XXX.png` is a pre-rendered 2D RGBA sprite lacking explicit 3D mesh connectivity at runtime.

Standard 2D drop shadows or simple heightfield raymarching fail to capture true 3D occlusion:
1. **Heightfield ("Infinite Pillar") Limitation**: If a pixel only stores a single height or front depth $z_{\text{front}}(u, v)$ and blocks any ray with $z_{\text{ray}} < z_{\text{front}}(u, v)$, overhanging structures—such as tree canopies above narrow trunks, street lamp arms, storefront awnings, and roof eaves—cast solid walls of shadow down to the ground. Rays cannot pass *underneath* the overhang.
2. **Multi-Sprite Compositing & Overlap**: In an isometric scene, sprites are stacked vertically (multi-story buildings + roofs) and overlap across grid cells. Each sprite's local depth map must be transformed into a unified scene-wide metric space with accurate per-pixel depth sorting.
3. **Self-Shadowing & Aliasing Artifacts**: Discrete texel sampling of depth maps introduces staircase self-occlusion ("shadow acne") on sloped roofs and vertical walls, as well as step-banding along shadow penumbras.

To solve these challenges, we combine **per-sprite 3D reconstruction in Blender 5.2** (generating calibrated **Front Depth**, **Component Thickness**, and **View/World Normal** maps) with a **WebGL2 / Three.js Multiple Render Target (MRT) G-Buffer pipeline** and a **Screen-Space Volumetric Interval Raymarching Shader**.

---

## 2. Mathematical Formulation of Isometric Projection & View Space

### 2.1 Calibrated Orthographic Isometric Camera Basis

Analysis of the sprites in `assets/buildingTiles_000.png` through `buildingTiles_128.png` reveals an exact **2:1 isometric diamond projection**:
- A ground tile (`132x127` or `133x127`) has a horizontal diamond span of $W_{\text{ground}} = 131\text{ px}$ ($\Delta x = 65.5\text{ px}$ per half-tile) and a vertical diamond span of $H_{\text{ground}} = 65.5\text{ px}$ ($\Delta y = 32.75\text{ px}$ per half-tile), yielding $\Delta y / \Delta x = 0.5 = \cos(60^\circ)$.
- A building body (`99x85` or `100x85`) occupies $75\%$ of the ground footprint ($W_{\text{bldg}} = 98\text{ px}$, leaving a $12.5\%$ sidewalk margin on all four sides).
- In `sample.png` ($918 \times 515$), the scene is rendered at a uniform scale factor $s = 104 / 131.5 \approx 0.79087$, where each grid step has horizontal half-width $\Delta x = 52\text{ px}$ and vertical half-height $\Delta y = 26\text{ px}$.

In Blender 5.2 (right-handed Z-up world coordinates $(X_w, Y_w, Z_w)$), this exact projection is produced by an **Orthographic Camera** with Euler XYZ rotation:
$$\theta_X = 60^\circ, \qquad \theta_Y = 0^\circ, \qquad \theta_Z = 45^\circ$$

The orthonormal camera basis vectors in world space—Screen Right ($\mathbf{R}_{\text{cam}}$), Screen Up ($\mathbf{U}_{\text{cam}}$), and View Front toward Camera ($\mathbf{F}_{\text{cam}} = -\mathbf{V}_{\text{look}}$)—are:
$$\mathbf{R}_{\text{cam}} = \begin{bmatrix} \cos 45^\circ \\ \sin 45^\circ \\ 0 \end{bmatrix} = \begin{bmatrix} \frac{\sqrt{2}}{2} \\ \frac{\sqrt{2}}{2} \\ 0 \end{bmatrix}, \quad
\mathbf{U}_{\text{cam}} = \begin{bmatrix} -\sin 45^\circ \cos 60^\circ \\ \cos 45^\circ \cos 60^\circ \\ \sin 60^\circ \end{bmatrix} = \begin{bmatrix} -\frac{\sqrt{2}}{4} \\ \frac{\sqrt{2}}{4} \\ \frac{\sqrt{3}}{2} \end{bmatrix}, \quad
\mathbf{F}_{\text{cam}} = \begin{bmatrix} \sin 45^\circ \sin 60^\circ \\ -\cos 45^\circ \sin 60^\circ \\ \cos 60^\circ \end{bmatrix} = \begin{bmatrix} \frac{\sqrt{6}}{4} \\ -\frac{\sqrt{6}}{4} \\ \frac{1}{2} \end{bmatrix}$$

### 2.2 Unified Screen-Pixel Metric View Space $(x_{\text{px}}, y_{\text{px}}, z_{\text{px}})$

Let $s_{\text{px}}$ denote the orthographic scale in screen pixels per world unit. Any 3D world point $\mathbf{P}_w = (X_w, Y_w, Z_w)^T$ maps to **Pixel-Scaled Camera View Space** $\mathbf{P}_{\text{px}} = (x_{\text{px}}, y_{\text{px}}, z_{\text{px}})^T$ via:
$$\mathbf{P}_{\text{px}} = s_{\text{px}} \begin{bmatrix} \mathbf{R}_{\text{cam}}^T \\ \mathbf{U}_{\text{cam}}^T \\ \mathbf{F}_{\text{cam}}^T \end{bmatrix} \mathbf{P}_w$$
Because $(\mathbf{R}_{\text{cam}}, \mathbf{U}_{\text{cam}}, \mathbf{F}_{\text{cam}})$ is an orthonormal basis and all three axes are scaled by the same scalar $s_{\text{px}}$:
1. $x_{\text{px}} \in [0, W]$ and $y_{\text{px}} \in [0, H]$ correspond directly to screen pixel coordinates (`gl_FragCoord.xy`).
2. $z_{\text{px}}$ measures linear depth toward the camera in **screen-pixel units** (larger $z_{\text{px}}$ = closer to the camera).
3. Any unit light direction vector $\mathbf{L}_w = (L_X, L_Y, L_Z)^T$ ($\|\mathbf{L}_w\| = 1$, pointing from the surface toward the light source) transforms into view space via:
   $$\mathbf{L}_v = \begin{bmatrix} L_{x,v} \\ L_{y,v} \\ L_{z,v} \end{bmatrix} = \begin{bmatrix} \mathbf{R}_{\text{cam}}^T \mathbf{L}_w \\ \mathbf{U}_{\text{cam}}^T \mathbf{L}_w \\ \mathbf{F}_{\text{cam}}^T \mathbf{L}_w \end{bmatrix}, \qquad \|\mathbf{L}_v\| = 1$$
   When marching a ray in pixel-scaled view space by step size $\Delta t$ (in pixels), the ray advances by $\Delta t \cdot (L_{x,v}, L_{y,v}, L_{z,v})$ with zero aspect-ratio distortion.

---

## 3. Volumetric Interval Raymarching with Depth and Thickness

### 3.1 Front Depth, Back Depth, and Component Thickness

At each pixel $(u, v)$, an orthographic viewing ray from the camera passes through the 3D scene geometry:
- **Front Depth $z_{\text{front}}(u, v)$**: The view-space depth $z_{\text{px}}$ of the closest visible front surface at $(u, v)$.
- **Component Thickness $T(u, v) \ge 0$**: The depth span along the viewing ray of the front-most hit 3D structure at $(u, v)$, defining its back surface at:
  $$z_{\text{back}}(u, v) = z_{\text{front}}(u, v) - T(u, v)$$

> **Critical Design Principle — Component-Local Thickness vs. Whole-Tile Depth Span**:
> Suppose a viewing ray at pixel $(u, v)$ hits the upper canopy of a tree, and behind the canopy (further along the viewing ray) lies the ground slab of the same tile. If thickness $T(u, v)$ were computed as $z_{\text{front, canopy}} - z_{\text{back, ground}}$, the empty air gap under the canopy would be filled in, turning the tree into a solid pillar.
> Instead, $T(u, v)$ must measure the entry-to-exit depth span of the **front-most hit 3D component** $[z_{\text{back, comp}}, z_{\text{front, comp}}]$. This preserves the open space beneath tree crowns, street lamp arms, and awnings.

### 3.2 Ray-Interval Intersection Condition

To evaluate whether a surface point $\mathbf{P}_0 = (x_0, y_0, z_{\text{front}}(x_0, y_0))$ is in shadow, we march a ray toward the light direction $\mathbf{L}_v$:
$$\mathbf{P}(t) = \mathbf{P}_{0,\text{biased}} + t \cdot \mathbf{L}_v, \qquad t \in [t_{\text{start}}, t_{\max}]$$
where $\mathbf{P}_{0,\text{biased}} = \mathbf{P}_0 + \epsilon_n \mathbf{N}_v$ applies a normal-offset bias $\epsilon_n$ along the view-space surface normal $\mathbf{N}_v$.

At each sample step $t_i$, we convert $(x(t_i), y(t_i))$ to screen UV coordinates $(u_i, v_i) = (x(t_i)/W, y(t_i)/H)$ and fetch $z_{\text{front}}(u_i, v_i)$, $T(u_i, v_i)$, and coverage $\alpha(u_i, v_i)$ from the unified scene G-Buffer.

Defining the penetration depth behind the front surface at $(u_i, v_i)$:
$$\Delta z(t_i) = z_{\text{front}}(u_i, v_i) - z_{\text{ray}}(t_i)$$
the ray intersects the solid volume at $(u_i, v_i)$ if and only if $\alpha(u_i, v_i) \ge 0.5$ and:
$$\epsilon_z < \Delta z(t_i) < T(u_i, v_i)$$
where $\epsilon_z = \epsilon_{\text{base}} + \epsilon_{\text{slope}}(1 - \max(\mathbf{N}_v \cdot \mathbf{L}_v, 0))$ is the slope-scaled depth bias:
- **Case 1 ($\Delta z(t_i) \le \epsilon_z$)**: The ray is in front of / above the surface at $(u_i, v_i)$ ($z_{\text{ray}} \ge z_{\text{front}} - \epsilon_z$). **Unoccluded.**
- **Case 2 ($\epsilon_z < \Delta z(t_i) < T(u_i, v_i)$)**: The ray penetrates inside the solid volume $[z_{\text{back}}, z_{\text{front}} - \epsilon_z]$. **Occluded.**
- **Case 3 ($\Delta z(t_i) \ge T(u_i, v_i)$)**: The ray passes completely behind / underneath the overhanging structure ($z_{\text{ray}} \le z_{\text{back}}$). **Unoccluded.**

---

## 4. Multi-Sprite Unified G-Buffer Composition in Three.js

### 4.1 Per-Tile Depth Offset ($\Delta z_{\text{tile}}$)

Each sprite asset $k$ is rendered in Blender 5.2 centered at its local origin $(0, 0, 0)$, producing:
- Local front depth $z_{\text{local}}^{\text{front}}(u_s, v_s) = s_{\text{px}} (\mathbf{P}_{\text{local}, w} \cdot \mathbf{F}_{\text{cam}})$,
- Local component thickness $T_{\text{local}}(u_s, v_s)$,
- View-space normal $\mathbf{N}_v(u_s, v_s)$.

When placed at isometric grid coordinates $(u_{\text{grid}}, v_{\text{grid}}, h_{\text{story}})$ in the Three.js scene, the tile's 3D world translation $\mathbf{T}_{\text{tile}, w}$ adds a scalar view-space depth offset $\Delta z_{\text{tile}}$ to every pixel of the sprite:
$$z_{\text{scene}}^{\text{front}}(u, v) = z_{\text{local}}^{\text{front}}(u_s, v_s) + \Delta z_{\text{tile}}, \qquad \Delta z_{\text{tile}} = s_{\text{px}} (\mathbf{T}_{\text{tile}, w} \cdot \mathbf{F}_{\text{cam}})$$
Specifically, in our screen-pixel coordinate system where stepping $+1$ in $u_{\text{grid}}$ moves $(+52, +26)$ px, stepping $+1$ in $v_{\text{grid}}$ moves $(+52, -26)$ px, and stepping $+1$ building story moves $(0, +27.68)$ px upward:
- In normalized world units where $1\text{ grid tile} = L_w$ units:
  - Stepping $+1$ in $u_{\text{grid}}$ corresponds to $+L_w$ along $\mathbf{X}_w$ (down-right): $\Delta x_{\text{px}} = +52$, $\Delta y_{\text{px}} = -26$ (in Y-up screen coordinates), and $\Delta z_{\text{px}} = +26\sqrt{3} \approx +45.033\text{ px}$.
  - Stepping $+1$ in $v_{\text{grid}}$ corresponds to $+L_w$ along $\mathbf{Y}_w$ (up-right): $\Delta x_{\text{px}} = +52$, $\Delta y_{\text{px}} = +26$, and $\Delta z_{\text{px}} = -26\sqrt{3} \approx -45.033\text{ px}$.
  - Stepping $+1$ in vertical height $\Delta H_{\text{px}}$ (where projected screen height is $\Delta y_{\text{px}} = Z_w s_{\text{px}} \sin 60^\circ$) contributes $\Delta z_{\text{px}} = Z_w s_{\text{px}} \cos 60^\circ = \Delta y_{\text{px}} / \sqrt{3} \approx 0.57735 \, \Delta y_{\text{px}}$.

### 4.2 Per-Pixel Depth Sorting via `gl_FragDepth`

Because isometric sprite bounding boxes overlap, painter's algorithm sorting of whole quads is insufficient where multi-part structures or props overlap. In the Three.js G-Buffer pass, each sprite fragment writes its exact unified front depth into `gl_FragDepth`:
```glsl
if (albedo.a < 0.5) discard;
float zSceneFront = zLocalFront + uTileDepthOffset;
gl_FragDepth = clamp(1.0 - (zSceneFront - uZMin) / (uZMax - uZMin), 0.0, 1.0);
```
With hardware `depthTest: true` and `depthWrite: true`, the GPU Z-buffer resolves exact per-pixel visibility across all overlapping sprites.

---

## 5. Soft Penumbras, Jittering & Shading Integration

1. **Interleaved Gradient Noise (IGN) & Multi-Ray Cone Sampling**:
   To produce natural contact-hardening soft shadows (sharp near contact points, softer with distance) without step banding, we cast $K$ rays per pixel distributed across a Vogel spiral disk of angular radius $r_{\text{light}}$ around $\mathbf{L}_v$, with each ray's starting step offset by Jorge Jimenez's Interleaved Gradient Noise:
   $$\text{IGN}(x, y) = \text{fract}\left(52.9829189 \cdot \text{fract}(0.06711056 x + 0.00583715 y)\right)$$
2. **Depth- & Normal-Aware Bilateral Filtering**:
   A separable 2-pass spatial bilateral filter (weighted by front-depth proximity and normal similarity) smooths any residual stochastic noise while preserving razor-sharp geometric edges along building silhouettes and roof rims.
3. **Preserving Pre-Baked Sprite Aesthetics**:
   Because Kenney's 2D sprites in `assets/` already contain baked ambient and directional wall shading, applying a heavy diffuse $\mathbf{N} \cdot \mathbf{L}$ multiplier would double-darken right-facing walls and alter the reference colors of `sample.png`. We therefore use the reconstructed normal map primarily for:
   - Exact 3D normal-offset ray origin biasing ($\mathbf{P}_0 + \epsilon_n \mathbf{N}_v$),
   - Edge-preserving bilateral shadow filtering,
   - Subtle directional light responsiveness when the dynamic global light moves, while the raymarched shadow visibility factor cleanly modulates cast shadows across roads, sidewalks, roofs, and facades.
