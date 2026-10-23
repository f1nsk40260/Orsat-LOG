// Fond « vue satellite » de la carte azimutale : reprojection pixel par pixel des tuiles Web Mercator
// (Sentinel-2 cloudless, servies et mises en cache par le carnet : api/sattile/z/y/x.jpg).
// Pour chaque pixel du disque : coordonnées géographiques (projection inverse), puis tuile et pixel
// Mercator correspondants au niveau de zoom adapté à l'échelle affichée.

const TILE = 256;
const cache = new Map();          // "z/y/x" -> Promise<ImageData | null>

function loadTile(z, y, x) {
  const key = `${z}/${y}/${x}`;
  if (!cache.has(key)) {
    cache.set(key, new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement('canvas');
        c.width = c.height = TILE;
        const g = c.getContext('2d');
        g.drawImage(img, 0, 0, TILE, TILE);
        resolve(g.getImageData(0, 0, TILE, TILE));
      };
      img.onerror = () => { cache.delete(key); resolve(null); };
      img.src = `api/sattile/${key}.jpg`;
    }));
  }
  return cache.get(key);
}

/** Niveau de tuiles pour une résolution au sol voulue (m/pixel) à la latitude donnée. */
export function tileZoom(metersPerPixel, lat) {
  const z = Math.log2((156543.03 * Math.cos((lat * Math.PI) / 180)) / metersPerPixel);
  return Math.max(2, Math.min(13, Math.ceil(z)));
}

/**
 * Image satellite du disque, en data URL (JPEG). proj : projection d3 (avec invert),
 * size : côté du carré en pixels, cx/cy/r : disque utile, z : niveau de tuiles.
 * Renvoie { url, missing } ; missing = nombre de tuiles introuvables.
 */
export async function renderSatellite(proj, size, cx, cy, r, z) {
  const n = 2 ** z, world = TILE * n;
  const W = size, H = size;
  const src = new Int32Array(W * H * 3).fill(-1);       // tuile x, tuile y, offset dans la tuile
  const needed = new Map();
  for (let py = 0; py < H; py++) {
    for (let px = 0; px < W; px++) {
      if ((px - cx) ** 2 + (py - cy) ** 2 > r * r) continue;
      const ll = proj.invert([px + 0.5, py + 0.5]);
      if (!ll || !isFinite(ll[0]) || !isFinite(ll[1])) continue;
      const lat = Math.max(-85.05, Math.min(85.05, ll[1]));
      const sin = Math.sin((lat * Math.PI) / 180);
      const gx = ((((ll[0] + 180) / 360) * world) % world + world) % world;
      const gy = (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * world;
      const tx = Math.floor(gx / TILE), ty = Math.min(n - 1, Math.floor(gy / TILE));
      const i = (py * W + px) * 3;
      src[i] = tx; src[i + 1] = ty;
      src[i + 2] = (Math.floor(gy) - ty * TILE) * TILE + (Math.floor(gx) - tx * TILE);
      needed.set(`${tx},${ty}`, [tx, ty]);
    }
  }
  const tiles = new Map();
  await Promise.all([...needed.values()].map(async ([tx, ty]) => tiles.set(`${tx},${ty}`, await loadTile(z, ty, tx))));
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  const out = g.createImageData(W, H);
  let missing = 0;
  for (const v of tiles.values()) if (!v) missing++;
  for (let p = 0; p < W * H; p++) {
    const tx = src[p * 3];
    if (tx < 0) continue;
    const t = tiles.get(`${tx},${src[p * 3 + 1]}`);
    if (!t) continue;
    const o = Math.max(0, Math.min(TILE * TILE - 1, src[p * 3 + 2])) * 4;
    out.data[p * 4] = t.data[o]; out.data[p * 4 + 1] = t.data[o + 1];
    out.data[p * 4 + 2] = t.data[o + 2]; out.data[p * 4 + 3] = 255;
  }
  g.putImageData(out, 0, 0);
  return { url: c.toDataURL('image/jpeg', 0.85), missing, total: tiles.size };
}
