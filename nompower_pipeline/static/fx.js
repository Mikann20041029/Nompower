(() => {
  // ランダム3色（白に近すぎるのは避ける）
  const randHex = () => {
    const n = Math.floor(Math.random() * 0xFFFFFF);
    return "#" + n.toString(16).padStart(6, "0");
  };

  const luminance = (hex) => {
    const r = parseInt(hex.slice(1,3),16)/255;
    const g = parseInt(hex.slice(3,5),16)/255;
    const b = parseInt(hex.slice(5,7),16)/255;
    // relative luminance (simple)
    return 0.2126*r + 0.7152*g + 0.0722*b;
  };

  const pickNeon = () => {
    let c = randHex();
    let tries = 0;
    while (luminance(c) > 0.82 && tries < 30) { // 白寄り回避
      c = randHex();
      tries++;
    }
    return c;
  };

  const c1 = pickNeon();
  const c2 = pickNeon();
  const c3 = pickNeon();

  const root = document.documentElement;
  root.style.setProperty("--neon1", c1);
  root.style.setProperty("--neon2", c2);
  root.style.setProperty("--neon3", c3);
// Random dark background base (8 variants)
// Goal: add variety without making white text hard to read.
(function setRandomBgBase(){
  const bgPalette = [
    "#070A12", // original deep navy
    "#0E0610", // dark plum
    "#14060A", // dark wine
    "#12070A", // dark maroon
    "#160A06", // dark brown-red
    "#1A0D05", // dark burnt orange
    "#0F0A06", // dark cocoa
    "#0A0A0A"  // near-black neutral
  ];
  const pick = bgPalette[Math.floor(Math.random() * bgPalette.length)];
  document.documentElement.style.setProperty("--bg", pick);
})();

  // 粒子（CSSアニメ）
  const host = document.getElementById("particles");
  if (!host) return;

  const W = () => window.innerWidth;
  const H = () => window.innerHeight;

  const count = Math.min(120, Math.max(70, Math.floor(W()/16)));
  const colors = [c1, c2, c3];

  for (let i=0;i<count;i++){
    const p = document.createElement("div");
    p.className = "p";
    const size = 3 + Math.random()*6;
    p.style.width = `${size}px`;
    p.style.height = `${size}px`;
    p.style.left = `${Math.random()*100}vw`;
    p.style.top = `${(20 + Math.random()*90)}vh`;
    p.style.background = colors[Math.floor(Math.random()*colors.length)];
    p.style.boxShadow = `0 0 18px ${colors[Math.floor(Math.random()*colors.length)]}66`;
    const dur = 8 + Math.random()*14;
    p.style.animationDuration = `${dur}s`;
    p.style.animationDelay = `${-Math.random()*dur}s`;
    p.style.opacity = (0.25 + Math.random()*0.5).toFixed(2);
    host.appendChild(p);
  }
})();
