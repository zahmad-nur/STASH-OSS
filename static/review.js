// Review screen: hide employment fields on "No", show whether there are unsaved changes,
// and warn before leaving the page with changes that weren't saved.
(function () {
  var form = document.getElementById("review-form");
  if (!form) return;
  var rows = document.getElementById("work-rows");
  document.querySelectorAll("input[name=work_auth]").forEach(function (r) {
    r.addEventListener("change", function () { if (rows) rows.hidden = r.value !== "yes" || !r.checked; });
  });
  var state = document.getElementById("save-state");
  var dirty = form.dataset.draft === "1", submitting = false;
  function mark() {
    if (!dirty) { dirty = true; }
    state.textContent = "Unsaved changes. Save to keep them.";
    state.classList.add("unsaved");
  }
  form.addEventListener("input", mark);
  form.addEventListener("change", mark);
  form.addEventListener("submit", function () { submitting = true; });
  window.addEventListener("beforeunload", function (e) {
    if (dirty && !submitting) { e.preventDefault(); e.returnValue = ""; }
  });
})();
