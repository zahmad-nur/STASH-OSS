// Shows the chosen file name and enables the form's submit button.
document.querySelectorAll("form[data-filepick]").forEach(function (form) {
  var input = form.querySelector("input[type=file]");
  var name = form.querySelector(".file-name");
  var submit = form.querySelector("button[type=submit]");
  input.addEventListener("change", function () {
    var f = input.files[0];
    name.textContent = f ? f.name + " · " + Math.max(1, Math.round(f.size / 1024)) + " KB" : name.dataset.default;
    name.classList.toggle("chosen", !!f);
    submit.disabled = !f;
  });
});
