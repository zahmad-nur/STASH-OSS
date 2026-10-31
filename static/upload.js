(function () {
  var form = document.getElementById("upload-form");
  if (!form) return;
  var input = document.getElementById("upload-input");
  var status = document.getElementById("upload-status");
  var button = document.getElementById("upload-btn");
  var original = status.textContent;

  function sizeLabel(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }
  function update() {
    var f = input.files && input.files[0];
    if (f) {
      status.textContent = f.name + " · " + sizeLabel(f.size);
      status.classList.add("chosen");
      button.disabled = false;
    } else {
      status.textContent = original;
      status.classList.remove("chosen");
      button.disabled = true;
    }
  }
  input.addEventListener("change", update);

  ["dragenter", "dragover"].forEach(function (t) {
    form.addEventListener(t, function (e) { e.preventDefault(); form.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (t) {
    form.addEventListener(t, function (e) { e.preventDefault(); if (t === "dragleave" && form.contains(e.relatedTarget)) return; form.classList.remove("over"); });
  });
  form.addEventListener("drop", function (e) {
    if (e.dataTransfer && e.dataTransfer.files.length) { input.files = e.dataTransfer.files; update(); }
  });
  form.addEventListener("submit", function () { button.disabled = true; button.textContent = "Uploading…"; });
})();
