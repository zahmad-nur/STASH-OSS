// Show / hide a masked value such as the SEVIS ID.
document.querySelectorAll(".reveal").forEach(function (box) {
  var text = box.querySelector("[data-full]"), btn = box.querySelector(".reveal-btn");
  btn.addEventListener("click", function () {
    var showing = text.textContent === text.dataset.full;
    text.textContent = showing ? text.dataset.masked : text.dataset.full;
    btn.textContent = showing ? "Show" : "Hide";
  });
});
