// app/static/stage3d.js — the 3D office scan: renderer, desk computer, document camera, trays; follows the real server result.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { CSS3DObject, CSS3DRenderer } from "three/addons/renderers/CSS3DRenderer.js";
import { buildOffice, canvasTex, mesh, std } from "/static/office.js";

const B = (w, h, d) => new THREE.BoxGeometry(w, h, d);
const LED = { off: 0x22303f, busy: 0x4f9dff, ok: 0x35d07f, bad: 0xf0564c, ask: 0xf2b84b };
const VIEWS = { room: [[2.6, 2.2, 3.4], [0, 0.9, -0.2]], desk: [[0.25, 1.55, 1.6], [0.2, 0.98, -0.18]], screen: [[-0.25, 1.19, 0.66], [-0.25, 1.17, -0.33]] };
const SW = 1920, SH = 1125;  // the app page size shown on the PC: a big "resolution" so the whole app fits without scrolling (same aspect as the 0.82 x 0.48 m screen)

function tray(x, z, color, word) {
  const g = new THREE.Group(); g.position.set(x, 0.79, z);
  const m = std(color, { roughness: 0.4 });
  mesh(B(0.36, 0.012, 0.46), m, 0, 0, 0, g);
  for (const [w, d, px, pz] of [[0.36, 0.012, 0, 0.23], [0.36, 0.012, 0, -0.23], [0.012, 0.46, 0.18, 0], [0.012, 0.46, -0.18, 0]]) mesh(B(w, 0.05, d), m, px, 0.025, pz, g);
  const lab = mesh(new THREE.PlaneGeometry(0.3, 0.06), new THREE.MeshBasicMaterial({ map: canvasTex(256, 52, (c, w, h) => {
    c.fillStyle = "#fff"; c.fillRect(0, 0, w, h); c.fillStyle = "#222"; c.font = "700 34px IBM Plex Sans, sans-serif"; c.textAlign = "center"; c.fillText(word, w / 2, 38); }) }), 0, 0.03, 0.236, g);
  lab.rotation.x = -0.3; return g;
}

export function createStage(el) {
  const r = new THREE.WebGLRenderer({ antialias: true });
  r.setPixelRatio(Math.min(devicePixelRatio, 2)); r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
  r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 0.95; el.appendChild(r.domElement);
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0xd8d3ca);
  scene.environment = new THREE.PMREMGenerator(r).fromScene(new RoomEnvironment(), 0.04).texture;
  const cam = new THREE.PerspectiveCamera(40, 1, 0.05, 40), ctl = new OrbitControls(cam, r.domElement);
  ctl.enableDamping = true; ctl.enableZoom = false;  // mouse wheel scrolls the page, not the camera (it trapped the page scroll)
  ctl.maxPolarAngle = Math.PI / 2.1; ctl.minDistance = 0.6; ctl.maxDistance = 6;
  cam.position.set(...VIEWS.room[0]); ctl.target.set(...VIEWS.room[1]);
  const { desk } = buildOffice(scene);

  // computer: its screen is the real Closeguard app page (iframe in a CSS3D layer), keyboard, mouse, mug
  const dark = std(0x16191e, { roughness: 0.4, metalness: 0.3 });
  const css = new CSS3DRenderer(), cssScene = new THREE.Scene(); el.appendChild(css.domElement);
  Object.assign(css.domElement.style, { position: "absolute", inset: "0", pointerEvents: "none" });
  const frame = document.createElement("iframe"); frame.src = "/app?embed=1"; frame.title = "Closeguard app on the PC";
  Object.assign(frame.style, { width: SW + "px", height: SH + "px", border: "0", background: "#f4f6f8", pointerEvents: "none", backfaceVisibility: "hidden" });
  const app = new CSS3DObject(frame); app.position.set(-0.25, 1.17, -0.31); app.scale.setScalar(0.82 / SW); cssScene.add(app);
  mesh(B(0.26, 0.012, 0.18), dark, -0.25, 0.795, -0.32, desk); mesh(B(0.05, 0.3, 0.04), dark, -0.25, 0.94, -0.36, desk);
  mesh(B(0.86, 0.52, 0.035), dark, -0.25, 1.17, -0.33, desk);
  mesh(new THREE.PlaneGeometry(0.82, 0.48), new THREE.MeshBasicMaterial({ color: 0x0b0f14 }), -0.25, 1.17, -0.311, desk).castShadow = false;
  mesh(B(0.46, 0.018, 0.15), std(0x2a2e35, { map: canvasTex(256, 84, (c, w, h) => { c.fillStyle = "#2a2e35"; c.fillRect(0, 0, w, h);
    c.fillStyle = "#555c66"; for (let y = 0; y < 5; y++) for (let x = 0; x < 15; x++) c.fillRect(4 + x * 16.6, 4 + y * 16, 13, 12); }) }), -0.25, 0.79, 0.12, desk);
  mesh(new THREE.CapsuleGeometry(0.025, 0.04, 4, 8), std(0x2a2e35), 0.12, 0.8, 0.14, desk).rotation.x = Math.PI / 2;
  const mug = mesh(new THREE.CylinderGeometry(0.04, 0.035, 0.1, 20), std(0xf1ede4, { roughness: 0.25 }), -0.85, 0.83, 0.25, desk);
  mesh(new THREE.TorusGeometry(0.025, 0.007, 8, 16), std(0xf1ede4), 0.045, 0, 0, mug);

  // document camera over a mat; trays: IN (to scan), OK, ON HOLD
  const matPos = new THREE.Vector3(0.62, 0.795, -0.02), metal = std(0x9aa3ad, { metalness: 0.8, roughness: 0.3 });
  mesh(B(0.42, 0.006, 0.52), std(0x1b1f25, { roughness: 0.9 }), matPos.x, 0.792, matPos.z, desk);
  mesh(new THREE.CylinderGeometry(0.07, 0.08, 0.025, 24), dark, 0.62, 0.805, -0.36, desk);
  mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.62), metal, 0.62, 1.1, -0.36, desk);
  mesh(new THREE.CylinderGeometry(0.01, 0.01, 0.34), metal, 0.62, 1.4, -0.2, desk).rotation.x = Math.PI / 2;
  const head = mesh(B(0.09, 0.04, 0.12), dark, 0.62, 1.39, -0.03, desk);
  const ledM = new THREE.MeshStandardMaterial({ color: LED.off, emissive: LED.off, emissiveIntensity: 2 });
  mesh(new THREE.TorusGeometry(0.03, 0.006, 8, 24), ledM, 0, -0.022, 0, head).rotation.x = Math.PI / 2;
  const beam = new THREE.SpotLight(0xdfe9ff, 0, 1.2, 0.5, 0.6); beam.position.set(0.62, 1.36, -0.03); beam.target.position.copy(matPos); desk.add(beam, beam.target);
  const bar = mesh(new THREE.PlaneGeometry(0.4, 0.008), new THREE.MeshBasicMaterial({ color: 0x7fd4ff, transparent: true, opacity: 0, toneMapped: false }), matPos.x, 0.81, 0, desk);
  bar.rotation.x = -Math.PI / 2; bar.castShadow = false;
  const inbox = tray(1.0, 0.3, 0xcfd6de, "IN"), okT = tray(-0.78, -0.12, 0x8fd1a8, "OK"), holdT = tray(1.0, -0.32, 0xf0a39d, "ON HOLD");
  desk.add(inbox, okT, holdT);
  for (let i = 0; i < 5; i++) mesh(B(0.3, 0.003, 0.4), std(0xf7f4ec), 0, 0.01 + i * 0.004, 0, inbox).rotation.y = (Math.random() - 0.5) * 0.12;

  // the document being scanned, with a stamp that appears on the verdict
  const docM = new THREE.MeshStandardMaterial({ color: 0xf7f4ec, roughness: 0.85 });
  const doc = mesh(new THREE.PlaneGeometry(0.3, 0.4), docM, 1.0, 0.84, 0.3, desk); doc.rotation.x = -Math.PI / 2; doc.visible = false;
  const stampM = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false });
  const stamp = mesh(new THREE.PlaneGeometry(0.24, 0.1), stampM, 0, 0.03, 0.002, doc); stamp.rotation.z = 0.25; stamp.castShadow = false;
  const loader = new THREE.TextureLoader();

  let tweens = [], scanning = false, t0 = performance.now();
  const tween = (obj, to, ms) => new Promise(done => tweens.push({ obj, from: obj.clone(), to: to.clone(), t: performance.now(), ms, done }));
  const fly = (view, ms = 1200) => Promise.all([tween(cam.position, new THREE.Vector3(...VIEWS[view][0]), ms), tween(ctl.target, new THREE.Vector3(...VIEWS[view][1]), ms)]);
  const at = (x, y, z) => new THREE.Vector3(x, y, z);
  function fit() { const w = el.clientWidth, h = el.clientHeight; r.setSize(w, h, false); css.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix(); }
  new ResizeObserver(fit).observe(el); fit();
  r.setAnimationLoop(() => {
    const now = performance.now();
    tweens = tweens.filter(tw => { const k = Math.min(1, (now - tw.t) / tw.ms), e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      tw.obj.lerpVectors(tw.from, tw.to, e); if (k >= 1) tw.done(); return k < 1; });
    if (scanning) { const s = (now - t0) / 1000; bar.material.opacity = 0.9; bar.position.z = matPos.z + Math.sin(s * 3) * 0.19;
      ledM.emissiveIntensity = 1.5 + Math.sin(s * 8); } else bar.material.opacity = 0;
    ctl.update(); r.render(scene, cam); css.render(cssScene, cam);
  });
  const led = c => { ledM.color.setHex(c); ledM.emissive.setHex(c); };
  const setDoc = map => { docM.map = map; docM.color.setHex(map ? 0xffffff : 0xf7f4ec); docM.needsUpdate = true;
    const im = map && map.image; if (im) { const a = (im.videoWidth || im.width) / (im.videoHeight || im.height); if (a) doc.scale.set(Math.min(1.4, a / 0.75), 1, 1); } };

  return {
    async pick(url, title) {  // a document comes off the IN tray and lands under the camera
      stampM.opacity = 0; led(LED.off); doc.visible = true; doc.position.set(1.0, 0.84, 0.3); doc.scale.set(1, 1, 1);
      if (url) loader.load(url, t => { t.colorSpace = THREE.SRGBColorSpace; setDoc(t); }); else setDoc(null);
      await Promise.all([fly("desk"), tween(doc.position, at(matPos.x, 0.80, matPos.z), 900)]);
    },
    liveCam(video) { const t = new THREE.VideoTexture(video); t.colorSpace = THREE.SRGBColorSpace;
      doc.visible = true; stampM.opacity = 0; doc.position.set(matPos.x, 0.80, matPos.z); setDoc(t);
      fly("desk"); },
    scanning(on = true) { scanning = on; beam.intensity = on ? 3 : 0; if (on) { t0 = performance.now(); led(LED.busy); } },
    async result(kind, word) {  // the app screen shows the verdict first, then back to the desk for the stamp and the tray
      this.scanning(false); led(LED[kind]);
      await new Promise(f => setTimeout(f, 2800)); await fly("desk", 1000);
      stampM.map = canvasTex(256, 100, (c, w, h) => { c.strokeStyle = c.fillStyle = kind === "ok" ? "#1f9d57" : kind === "ask" ? "#c98a12" : "#d33a2f";
        c.lineWidth = 8; c.strokeRect(6, 6, w - 12, h - 12); c.font = "800 40px IBM Plex Sans, sans-serif"; c.textAlign = "center"; c.fillText(word, w / 2, 64); }, [1, 1]);
      stampM.opacity = 0.9; stampM.needsUpdate = true;
      await new Promise(f => setTimeout(f, 1200));
      if (kind !== "ask") await tween(doc.position, kind === "ok" ? at(-0.78, 0.83, -0.12) : at(1.0, 0.83, -0.32), 900);
    },
    fail() { this.scanning(false); led(LED.bad); },
    view: fly,
  };
}
