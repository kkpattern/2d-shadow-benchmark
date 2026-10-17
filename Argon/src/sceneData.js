// Scene layout and isometric projection constants for recreating sample.png (918x515)
export const CANVAS_WIDTH = 918;
export const CANVAS_HEIGHT = 515;
export const SCALE = 104.0 / 131.5;
export const CX0 = 200.0;
export const CY0 = 242.5;
export const FLOOR_DY = 27.68;
export const BG_RGB = [63, 124, 182];
export const BG_HEX = 0x3f7cb6;

// Exact list of ground tiles, props, and building story sprites in sample.png
// Format: [u, v, z_story, tileName, isOriginalAsset]
export const RAW_SCENE_ITEMS = [
  // Ground, road, plaza, tree, street lamp, fountain, and red-wall tiles
  [-1, 1, 0.0, 'scene_plaza', false],
  [ 0, 1, 0.0, 'scene_plaza', false],
  [ 0, 2, 0.0, 'scene_road_end_u', false],
  [ 0, 4, 0.0, 'scene_road_u', false],
  [ 1, 0, 0.0, 'scene_road_curve', false],
  [ 1, 1, 0.0, 'scene_road_lamps_v', false],
  [ 1, 2, 0.0, 'scene_road_roundabout', false],
  [ 1, 3, 0.0, 'scene_road_trees_v', false],
  [ 1, 4, 0.0, 'scene_road_cross', false],
  [ 2, 0, 0.0, 'scene_road_u', false],
  [ 2, 2, 0.0, 'scene_road_u', false],
  [ 3, 0, 0.0, 'scene_road_crosswalk_u', false],
  [ 3, 2, 0.0, 'scene_road_t_u_v', false],
  [ 3, 3, 0.0, 'scene_road_v', false],
  [ 3, 4, 0.0, 'scene_road_v', false],
  [ 3, 5, 0.0, 'scene_road_lamps_v', false],
  [ 4, 0, 0.0, 'scene_road_t_u_v', false],
  [ 4, 1, 0.0, 'scene_plaza', false],
  [ 4, 2, 0.0, 'scene_road_u', false],
  [ 4, 4, 0.0, 'scene_plaza_red_wall_44', false],
  [ 4, 5, 0.0, 'scene_plaza_fountain', false],
  [ 5, 1, 0.0, 'scene_plaza', false],
  [ 5, 2, 0.0, 'scene_road_u', false],
  [ 5, 3, 0.0, 'scene_plaza', false],
  [ 5, 4, 0.0, 'scene_plaza_red_wall_54', false],
  [ 6, 2, 0.0, 'scene_road_trees_u', false],
  [ 6, 4, 0.0, 'scene_plaza', false],
  [ 5.20, -0.42, 0.0, 'scene_road_detached', false],

  // Building 1: Yellow 4-story building at (0, 0)
  [ 0, 0, 0.0, 'buildingTiles_029', true],
  [ 0, 0, 1.0, 'buildingTiles_051', true],
  [ 0, 0, 2.0, 'buildingTiles_051', true],
  [ 0, 0, 3.0, 'buildingTiles_051', true],
  [ 0, 0, 4.0, 'buildingTiles_128_white', false],

  // Building 2: Red 2-story building at (-1, 2)
  [-1, 2, 0.0, 'buildingTiles_036', true],
  [-1, 2, 1.0, 'buildingTiles_049', true],
  [-1, 2, 2.0, 'buildingTiles_128_white', false],

  // Building 3: Brown 1-story building at (0, 3)
  [ 0, 3, 0.0, 'buildingTiles_014', true],
  [ 0, 3, 1.0, 'buildingTiles_102', true],

  // Building 4: Brown 4-story building at (2, 3)
  [ 2, 3, 0.0, 'buildingTiles_099', true],
  [ 2, 3, 1.0, 'buildingTiles_038', true],
  [ 2, 3, 2.0, 'buildingTiles_038', true],
  [ 2, 3, 3.0, 'buildingTiles_038', true],
  [ 2, 3, 4.0, 'buildingTiles_110', true],

  // Building 5: Grey 2-story building at (2, 4)
  [ 2, 4, 0.0, 'buildingTiles_124', true],
  [ 2, 4, 1.0, 'buildingTiles_031', true],
  [ 2, 4, 2.0, 'buildingTiles_127', true],

  // Building 6: Green shop 1-story building at (2, 1)
  [ 2, 1, 0.0, 'buildingTiles_108', true],
  [ 2, 1, 1.0, 'buildingTiles_088', true],

  // Building 7: Modern 3-story building at (3, 1)
  [ 3, 1, 0.0, 'buildingTiles_001', true],
  [ 3, 1, 1.0, 'buildingTiles_016', true],
  [ 3, 1, 2.0, 'buildingTiles_016', true],
  [ 3, 1, 3.0, 'buildingTiles_128_white', false],

  // Building 8: Red/Blue 2-story building at (4, 3)
  [ 4, 3, 0.0, 'buildingTiles_034', true],
  [ 4, 3, 1.15, 'buildingTiles_052', true],
  [ 4, 3, 2.15, 'buildingTiles_128', true],
];

// Sort back-to-front by isometric depth (u - v), then story height (z_story)
export const SCENE_ITEMS = [...RAW_SCENE_ITEMS]
  .map((item, idx) => ({
    u: item[0],
    v: item[1],
    zStory: item[2],
    tileName: item[3],
    isAsset: item[4],
    originalIndex: idx,
  }))
  .sort((a, b) => {
    const depthA = a.u - a.v;
    const depthB = b.u - b.v;
    if (Math.abs(depthA - depthB) > 1e-4) return depthA - depthB;
    if (Math.abs(a.zStory - b.zStory) > 1e-4) return a.zStory - b.zStory;
    return a.originalIndex - b.originalIndex;
  });

/**
 * Compute sprite pivot in original unscaled pixel coordinates
 */
export function getSpritePivot(tileName, wOrig, hOrig) {
  if (tileName === 'scene_road_detached') {
    return { cxOrig: 74.0, cyOrig: 67.0 };
  }
  if (hOrig >= 125) {
    return { cxOrig: wOrig / 2.0, cyOrig: hOrig - 68.0 };
  }
  if (hOrig === 85) {
    return { cxOrig: wOrig / 2.0, cyOrig: hOrig - 25.5 };
  }
  return { cxOrig: wOrig / 2.0, cyOrig: hOrig - 26.2 };
}

/**
 * Compute global view-space depth offset (in sample.png pixel units) for a tile at (u, v, zStory)
 */
export function getTileDepthOffsetPx(u, v, zStory) {
  const SQRT3 = Math.sqrt(3.0);
  return (u - v) * (26.0 * SQRT3) + zStory * (FLOOR_DY / SQRT3);
}

/**
 * Compute camera view-space unit light direction L_view = (Lx, Ly, Lz)
 * from horizontal sun azimuth (degrees, where -55° is top-left sun, +55° is top-right sun)
 * and sun elevation above the horizontal ground plane (degrees, 10°..85°).
 */
export function computeLightDirView(azimuthDeg, elevationDeg) {
  const alpha = (azimuthDeg * Math.PI) / 180.0;
  const theta = (elevationDeg * Math.PI) / 180.0;
  const cosT = Math.cos(theta);
  const sinT = Math.sin(theta);
  const sinA = Math.sin(alpha);
  const cosA = Math.cos(alpha);
  const SQRT3_2 = Math.sqrt(3.0) * 0.5;

  // Orthonormal projection of L_world onto (R_cam, U_cam, F_cam)
  const lx = cosT * sinA;
  const ly = 0.5 * cosT * cosA + SQRT3_2 * sinT;
  const lz = -SQRT3_2 * cosT * cosA + 0.5 * sinT;
  const len = Math.hypot(lx, ly, lz) || 1.0;
  return [lx / len, ly / len, lz / len];
}
