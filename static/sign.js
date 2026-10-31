(function () {
  // ---- drawing pad (sign page and Settings) ----
  var pad = document.getElementById("sig-pad");
  var drawn = false;
  var onStroke = function () {};
  if (pad) {
    var ctx = pad.getContext("2d");
    var drawing = false;
    ctx.lineWidth = 2.5; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#1B1E22";
    var point = function (e) {
      var r = pad.getBoundingClientRect();
      return { x: (e.clientX - r.left) * (pad.width / r.width), y: (e.clientY - r.top) * (pad.height / r.height) };
    };
    pad.addEventListener("pointerdown", function (e) {
      drawing = true; drawn = true; pad.setPointerCapture(e.pointerId);
      var p = point(e); ctx.beginPath(); ctx.moveTo(p.x, p.y);
    });
    pad.addEventListener("pointermove", function (e) {
      if (!drawing) return;
      var p = point(e); ctx.lineTo(p.x, p.y); ctx.stroke();
    });
    ["pointerup", "pointercancel"].forEach(function (t) {
      pad.addEventListener(t, function () { if (drawing) { drawing = false; onStroke(); } });
    });
    var clear = document.getElementById("sig-clear");
    if (clear) clear.addEventListener("click", function () {
      ctx.clearRect(0, 0, pad.width, pad.height); drawn = false; onStroke();
    });
  }

  var form = document.getElementById("sign-form") || document.getElementById("draw-form");
  if (form) form.addEventListener("submit", function (e) {
    var src = form.querySelector("input[name=source]:checked") || form.querySelector("input[name=source]");
    if (pad && (!src || src.value === "draw")) {
      if (!drawn) { e.preventDefault(); alert("Draw your signature first."); return; }
      document.getElementById("sig-data").value = pad.toDataURL("image/png");
    }
  });

  // ---- placing signature and date on page 1 ----
  var placer = document.getElementById("placer");
  if (!placer) return;
  var sigBox = document.getElementById("sig-box"), dateBox = document.getElementById("date-box");
  var sigImg = document.getElementById("sig-img"), sigHint = document.getElementById("sig-hint");
  var size = document.getElementById("sig-size"), dateInput = document.getElementById("sign-date");
  var pageW = parseFloat(placer.dataset.pageW);
  var set = function (id, v) { document.getElementById(id).value = v.toFixed(4); };

  function showSig(src) {
    if (src) { sigImg.src = src; sigImg.hidden = false; sigHint.hidden = true; }
    else { sigImg.removeAttribute("src"); sigImg.hidden = true; sigHint.hidden = false; }
  }
  function currentSource() {
    var r = document.querySelector("input[name=source]:checked") || document.querySelector("input[name=source]");
    return r ? r.value : "draw";
  }
  function refreshSig() {
    if (currentSource() === "saved") showSig("/documents/signature.png");
    else showSig(drawn ? pad.toDataURL("image/png") : null);
  }
  onStroke = refreshSig;
  document.querySelectorAll("input[name=source]").forEach(function (r) {
    r.addEventListener("change", function () {
      document.getElementById("draw-area").hidden = currentSource() !== "draw";
      refreshSig();
    });
  });
  refreshSig();

  function scaleDate() {  // the date is drawn at 9pt on the page, shown to scale here
    dateBox.style.fontSize = (9 * placer.clientWidth / pageW) + "px";
  }
  function showDate() {
    var v = dateInput.value;
    dateBox.textContent = v ? v.slice(5, 7) + "/" + v.slice(8, 10) + "/" + v.slice(0, 4) : "MM/DD/YYYY";
  }
  dateInput.addEventListener("input", showDate);
  window.addEventListener("resize", scaleDate);
  showDate(); scaleDate();

  size.addEventListener("input", function () {
    sigBox.style.width = (size.value * 100) + "%"; set("sig_w", parseFloat(size.value));
  });

  function draggable(box, xId, yId) {
    var start = null;
    box.addEventListener("pointerdown", function (e) {
      e.preventDefault(); box.setPointerCapture(e.pointerId);
      var r = placer.getBoundingClientRect(), b = box.getBoundingClientRect();
      start = { dx: e.clientX - b.left, dy: e.clientY - b.top, r: r, w: b.width, h: b.height };
      box.classList.add("dragging");
    });
    box.addEventListener("pointermove", function (e) {
      if (!start) return;
      var r = start.r;
      var x = Math.min(Math.max(e.clientX - r.left - start.dx, 0), r.width - start.w) / r.width;
      var y = Math.min(Math.max(e.clientY - r.top - start.dy, 0), r.height - start.h) / r.height;
      box.style.left = (x * 100) + "%"; box.style.top = (y * 100) + "%";
      set(xId, x); set(yId, y);
    });
    ["pointerup", "pointercancel"].forEach(function (t) {
      box.addEventListener(t, function () { start = null; box.classList.remove("dragging"); });
    });
  }
  draggable(sigBox, "sig_x", "sig_y");
  draggable(dateBox, "date_x", "date_y");
})();
