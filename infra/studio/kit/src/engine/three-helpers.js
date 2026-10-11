// three.js helpers: studio environment, glyph → mesh, capsule halves.
import * as THREE from 'three';
import * as Type from './type.js';

/** px-per-world-unit for a perspective camera looking at z=0 from distance d, on a 1080-high design frame. */
export const pxPerUnit = (fovDeg, d) => 1080 / (2 * d * Math.tan((fovDeg * Math.PI) / 360));

/**
 * Procedural studio HDRI: a dark room with a few large softboxes. Returns a PMREM env texture.
 * boxes: [{ pos:[x,y,z], size:[w,h], color, intensity }]
 */
export function studioEnv(renderer, { boxes = null, ambient = 0x1a1614, floor = 0x2a2420 } = {}) {
  const scene = new THREE.Scene();
  const room = new THREE.Mesh(new THREE.BoxGeometry(40, 30, 40), new THREE.MeshBasicMaterial({ color: ambient, side: THREE.BackSide }));
  scene.add(room);
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.MeshBasicMaterial({ color: floor }));
  fl.rotation.x = -Math.PI / 2; fl.position.y = -14.9; scene.add(fl);
  const list = boxes || [
    { pos: [0, 12, 4], size: [18, 10], color: 0xffffff, intensity: 9 },      // top key
    { pos: [-16, 2, 6], size: [8, 14], color: 0xfff1dc, intensity: 6 },      // left strip
    { pos: [16, -2, -4], size: [6, 16], color: 0xffd9c4, intensity: 4 },     // right rim
    { pos: [0, -4, 18], size: [20, 6], color: 0xffffff, intensity: 2.5 },    // front fill
  ];
  for (const b of list) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(b.size[0], b.size[1]), new THREE.MeshBasicMaterial({ color: new THREE.Color(b.color).multiplyScalar(b.intensity), side: THREE.DoubleSide }));
    m.position.set(...b.pos); m.lookAt(0, 0, 0); scene.add(m);
  }
  const pm = new THREE.PMREMGenerator(renderer);
  const tex = pm.fromScene(scene, 0.035).texture;
  pm.dispose();
  return tex;
}

/** Half of a capsule (hemisphere cap + half barrel) standing on y=0, pointing +y. */
export function halfCapsule(radius, halfLen, seg = 48) {
  const pts = [];
  const hc = Math.max(0, halfLen - radius);
  pts.push(new THREE.Vector2(radius, 0));
  pts.push(new THREE.Vector2(radius, hc));
  const n = 18;
  for (let i = 1; i <= n; i++) { const a = (i / n) * Math.PI / 2; pts.push(new THREE.Vector2(Math.cos(a) * radius, hc + Math.sin(a) * radius)); }
  const g = new THREE.LatheGeometry(pts, seg);
  g.computeVertexNormals();
  return g;
}

/**
 * Glyph outlines → THREE.Shape[] (y up, units = px of the layout, origin at the line's left baseline).
 * Handles holes by containment so it works for any TrueType outline direction.
 */
export function lineShapes(L, { steps = 6 } = {}) {
  const outs = Type.outlines(L, 0, 0, 'left', 'alphabetic', steps);
  const shapes = [];
  for (const o of outs) {
    const polys = o.contours.map((c) => {
      const v = [];
      for (let i = 0; i < c.pts.length - 2; i += 2) v.push(new THREE.Vector2(c.pts[i], -c.pts[i + 1]));
      let area = 0;
      for (let i = 0; i < v.length; i++) { const a = v[i], b = v[(i + 1) % v.length]; area += a.x * b.y - b.x * a.y; }
      return { v, area: area / 2 };
    }).filter((p) => p.v.length >= 3 && Math.abs(p.area) > 1e-3);
    if (!polys.length) continue;
    // outer contours share the sign of the largest contour
    const sign = Math.sign(polys.reduce((a, b) => (Math.abs(b.area) > Math.abs(a.area) ? b : a)).area);
    const outers = polys.filter((p) => Math.sign(p.area) === sign).map((p) => ({ p, holes: [] }));
    const inside = (pt, poly) => {
      let c = false;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const a = poly[i], b = poly[j];
        if ((a.y > pt.y) !== (b.y > pt.y) && pt.x < ((b.x - a.x) * (pt.y - a.y)) / (b.y - a.y) + a.x) c = !c;
      }
      return c;
    };
    for (const h of polys.filter((p) => Math.sign(p.area) !== sign)) {
      const host = outers.filter((o2) => inside(h.v[0], o2.p.v)).sort((a, b) => Math.abs(a.p.area) - Math.abs(b.p.area))[0];
      if (host) host.holes.push(h);
    }
    for (const { p, holes } of outers) {
      const s = new THREE.Shape(p.v);
      for (const h of holes) s.holes.push(new THREE.Path(h.v));
      s.userData = { glyph: o.g };
      shapes.push(s);
    }
  }
  return shapes;
}

/** Extruded text geometry, centred on its bounding box in x/y. Returns {geometry, width, height}. */
export function textGeometry(L, { depth = 40, bevel = 4, bevelSegments = 3, curveSegments = 6, center = true } = {}) {
  const shapes = lineShapes(L);
  const g = new THREE.ExtrudeGeometry(shapes, { depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel, bevelSegments, curveSegments, steps: 1 });
  g.computeBoundingBox();
  const bb = g.boundingBox;
  if (center) g.translate(-(bb.min.x + bb.max.x) / 2, -(bb.min.y + bb.max.y) / 2, -depth / 2);
  return { geometry: g, width: bb.max.x - bb.min.x, height: bb.max.y - bb.min.y };
}

/** One geometry per glyph (each centred on its own box) for per-letter 3D animation. */
export function glyphGeometries(L, opts = {}) {
  const { depth = 40, bevel = 4, bevelSegments = 3 } = opts;
  const shapes = lineShapes(L);
  const byGlyph = new Map();
  for (const s of shapes) { const g = s.userData.glyph; if (!byGlyph.has(g)) byGlyph.set(g, []); byGlyph.get(g).push(s); }
  const res = [];
  for (const [g, list] of byGlyph) {
    const geo = new THREE.ExtrudeGeometry(list, { depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel, bevelSegments, curveSegments: 6, steps: 1 });
    geo.computeBoundingBox();
    const bb = geo.boundingBox;
    const cx = (bb.min.x + bb.max.x) / 2, cy = (bb.min.y + bb.max.y) / 2;
    geo.translate(-cx, -cy, -depth / 2);
    res.push({ g, geometry: geo, cx, cy, w: bb.max.x - bb.min.x, h: bb.max.y - bb.min.y });
  }
  return res;
}
