// app/static/office.js — the office set (three.js, no downloaded assets): room, window light, desk, chair, shelf, plant, props.
import * as THREE from "three";

export function canvasTex(w, h, draw, repeat = [1, 1]) {
  const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...repeat); return t;
}
const noise = (g, w, h, a, n = 4000) => { for (let i = 0; i < n; i++) { g.fillStyle = `rgba(0,0,0,${Math.random() * a})`; g.fillRect(Math.random() * w, Math.random() * h, 1 + Math.random() * 3, 1); } };
const wood = (base, dark, rep) => canvasTex(512, 512, (g, w, h) => {
  g.fillStyle = base; g.fillRect(0, 0, w, h);
  for (let y = 0; y < h; y += 2) { g.strokeStyle = `rgba(${dark},${0.05 + Math.random() * 0.12})`; g.beginPath(); g.moveTo(0, y);
    for (let x = 0; x <= w; x += 32) g.lineTo(x, y + Math.sin(x / 60 + y / 9) * 3); g.stroke(); }
  noise(g, w, h, 0.06);
}, rep);
const planks = () => canvasTex(1024, 1024, (g, w, h) => {
  for (let i = 0; i < 8; i++) { const l = 52 + Math.random() * 10; g.fillStyle = `hsl(28, 35%, ${l}%)`; g.fillRect(0, i * 128, w, 128);
    g.fillStyle = "rgba(40,25,10,.35)"; g.fillRect(0, i * 128, w, 3); g.fillRect((i * 337) % w, i * 128, 3, 128); }
  noise(g, w, h, 0.08, 9000);
}, [3, 3]);

export const std = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.6, ...o });
export function mesh(geo, mat, x = 0, y = 0, z = 0, parent) {
  const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.castShadow = m.receiveShadow = true; if (parent) parent.add(m); return m;
}
const B = (w, h, d) => new THREE.BoxGeometry(w, h, d);

export function buildOffice(scene) {
  // room
  const floor = mesh(new THREE.PlaneGeometry(9, 9), std(0xffffff, { map: planks(), roughness: 0.55 }), 0, 0, 0, scene); floor.rotation.x = -Math.PI / 2;
  const wallM = std(0xe9e4da, { roughness: 0.95 });
  mesh(B(9, 3.2, 0.1), wallM, 0, 1.6, -2.2, scene);
  mesh(B(0.1, 3.2, 9), wallM, -3.2, 1.6, 0, scene);
  mesh(B(9, 0.12, 0.04), std(0xf6f4ef), 0, 0.06, -2.13, scene);  // skirting
  // window with daylight
  const win = new THREE.Group(); win.position.set(0.9, 1.75, -2.14); scene.add(win);
  mesh(new THREE.PlaneGeometry(2.2, 1.4), new THREE.MeshBasicMaterial({ map: canvasTex(256, 256, (g, w, h) => {
    const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, "#9fc8f0"); gr.addColorStop(1, "#e4f1fb"); g.fillStyle = gr; g.fillRect(0, 0, w, h);
    g.fillStyle = "rgba(120,150,170,.55)"; for (let i = 0; i < 9; i++) g.fillRect(i * 30, h - 40 - (i * 53) % 70, 26, 120); }) }), 0, 0, 0.01, win);
  const frameM = std(0xfafafa, { roughness: 0.4 });
  for (const [w, h, x, y] of [[2.36, 0.08, 0, 0.74], [2.36, 0.08, 0, -0.74], [0.08, 1.56, 1.14, 0], [0.08, 1.56, -1.14, 0], [0.05, 1.4, 0, 0]])
    mesh(B(w, h, 0.08), frameM, x, y, 0.04, win);
  const sun = new THREE.DirectionalLight(0xfff3e0, 2.2); sun.position.set(2.5, 4.5, 3.5); sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048); sun.shadow.camera.left = -4; sun.shadow.camera.right = 4; sun.shadow.camera.top = 4; sun.shadow.camera.bottom = -4;
  sun.shadow.bias = -0.0004; sun.shadow.radius = 4; scene.add(sun);
  const fill = new THREE.PointLight(0xffe2b8, 6, 6, 1.6); fill.position.set(-1.2, 2.6, 0.8); scene.add(fill);
  // picture on the side wall
  mesh(B(0.04, 0.7, 1.0), std(0x2a2a2a), -3.13, 1.9, -0.6, scene);
  mesh(new THREE.PlaneGeometry(0.9, 0.6), std(0xffffff, { map: canvasTex(256, 170, (g, w, h) => {
    g.fillStyle = "#3e6d8f"; g.fillRect(0, 0, w, h); g.fillStyle = "#e8b04a"; g.beginPath(); g.arc(180, 60, 26, 0, 7); g.fill();
    g.fillStyle = "#2c4f3a"; g.beginPath(); g.moveTo(0, h); g.lineTo(90, 70); g.lineTo(170, h); g.fill(); }) }), -3.1, 1.9, -0.6, scene).rotation.y = Math.PI / 2;
  // desk
  const desk = new THREE.Group(); scene.add(desk);
  mesh(B(2.4, 0.06, 1.1), std(0xffffff, { map: wood("#b58858", "70,40,15", [1, 1]), roughness: 0.45 }), 0, 0.76, 0, desk);
  const metal = std(0x2b2f36, { metalness: 0.7, roughness: 0.35 });
  for (const [x, z] of [[-1.12, -0.48], [1.12, -0.48], [-1.12, 0.48], [1.12, 0.48]]) mesh(B(0.05, 0.73, 0.05), metal, x, 0.365, z, desk);
  mesh(B(0.5, 0.55, 0.95), std(0xdedbd5), -0.85, 0.42, 0, desk);  // drawer unit
  for (const y of [0.3, 0.55]) mesh(B(0.18, 0.02, 0.02), metal, -0.85, y, 0.48, desk);
  // chair
  const chair = new THREE.Group(); chair.position.set(0.1, 0, 1.15); chair.rotation.y = 0.25; scene.add(chair);
  const fabric = std(0x2d3e50, { roughness: 0.9 });
  mesh(B(0.55, 0.08, 0.5), fabric, 0, 0.5, 0, chair); mesh(B(0.55, 0.6, 0.07), fabric, 0, 0.85, 0.24, chair);
  mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.45), metal, 0, 0.24, 0, chair);
  mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.03, 5), metal, 0, 0.03, 0, chair);
  // shelf with binders
  const shelf = new THREE.Group(); shelf.position.set(-2.4, 0, -1.85); scene.add(shelf);
  const sm = std(0xd9cdb8);
  for (const y of [0.02, 0.6, 1.2, 1.8]) mesh(B(1.2, 0.04, 0.4), sm, 0, y, 0, shelf);
  for (const x of [-0.6, 0.6]) mesh(B(0.04, 1.84, 0.4), sm, x, 0.92, 0, shelf);
  const binder = [0x1f5f8b, 0xb8452f, 0x2f7d5c, 0xd6a531, 0x5a4a7a];
  for (const [r, y] of [[0, 0.04], [1, 0.62], [2, 1.22]]) for (let i = 0; i < 6 - r; i++)
    mesh(B(0.09, 0.42, 0.3), std(binder[(i + r) % 5], { roughness: 0.5 }), -0.45 + i * 0.11, y + 0.21, 0.02, shelf);
  // plant
  const plant = new THREE.Group(); plant.position.set(2.1, 0, -1.6); scene.add(plant);
  mesh(new THREE.CylinderGeometry(0.22, 0.17, 0.42, 24), std(0xf2efe8, { roughness: 0.3 }), 0, 0.21, 0, plant);
  const leaf = std(0x3f7d3a, { roughness: 0.7, side: THREE.DoubleSide });
  for (let i = 0; i < 14; i++) { const l = mesh(new THREE.SphereGeometry(0.16, 12, 8), leaf, 0, 0.75 + Math.random() * 0.5, 0, plant);
    l.scale.set(0.35, 1.6, 0.12); const a = i * 2.4; l.position.x = Math.cos(a) * 0.12; l.position.z = Math.sin(a) * 0.12; l.rotation.set(Math.sin(a) * 0.5, a, Math.cos(a) * 0.5); }
  return { desk };
}
