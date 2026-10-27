/* WPOSS Vending Integration Manager — interacciones mínimas */
(function () {
  "use strict";

  // Menú lateral en pantallas pequeñas.
  document.querySelectorAll("[data-toggle-menu]").forEach(function (btn) {
    btn.addEventListener("click", function () { document.body.classList.toggle("menu-open"); });
  });

  // Cerrar mensajes.
  document.querySelectorAll("[data-dismiss]").forEach(function (btn) {
    btn.addEventListener("click", function () { btn.closest(".toast").remove(); });
  });
  document.querySelectorAll(".toast-ok").forEach(function (t) {
    setTimeout(function () { if (t.isConnected) { t.style.transition = "opacity .3s"; t.style.opacity = "0"; setTimeout(function () { t.remove(); }, 300); } }, 6000);
  });

  // Filas clicables.
  document.querySelectorAll("tr[data-href]").forEach(function (row) {
    row.addEventListener("click", function (e) {
      if (e.target.closest("a, button, input, select, textarea, summary, form")) return;
      window.location.href = row.dataset.href;
    });
  });

  // Botón "Pendiente": registra "Pendiente de confirmar".
  document.querySelectorAll("[data-fill]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.dataset.fill);
      if (input) { input.value = "Pendiente de confirmar"; input.focus(); }
    });
  });

  // Confirmación de operaciones importantes.
  var dialog = document.getElementById("confirm-dialog");
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.confirmed === "1") return;
      e.preventDefault();
      if (!dialog || typeof dialog.showModal !== "function") {
        if (window.confirm(form.dataset.confirm)) { form.dataset.confirmed = "1"; form.submit(); }
        return;
      }
      dialog.querySelector("[data-confirm-text]").textContent = form.dataset.confirm;
      dialog.returnValue = "";
      dialog.showModal();
      dialog.addEventListener("close", function onClose() {
        dialog.removeEventListener("close", onClose);
        if (dialog.returnValue === "ok") { form.dataset.confirmed = "1"; form.submit(); }
      });
    });
  });

  // Evita envíos dobles y muestra estado de carga.
  document.querySelectorAll("form[method=post]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (e.defaultPrevented) return;
      var btn = e.submitter;
      if (form.dataset.sending === "1") { e.preventDefault(); return; }
      form.dataset.sending = "1";
      if (btn) {
        // El navegador ya incluyó el botón en los datos; se desactiva después.
        setTimeout(function () { btn.disabled = true; btn.dataset.label = btn.textContent; btn.textContent = "Guardando…"; }, 0);
      }
    });
  });
  window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[data-sending]").forEach(function (f) { delete f.dataset.sending; });
  });

  // Copiar al portapapeles.
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var el = document.querySelector(btn.dataset.copy);
      if (!el) return;
      var text = el.innerText;
      var done = function () {
        var original = btn.innerHTML;
        btn.textContent = "Copiado";
        setTimeout(function () { btn.innerHTML = original; }, 1600);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done);
      } else {
        var range = document.createRange(); range.selectNodeContents(el);
        var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
        document.execCommand("copy"); sel.removeAllRanges(); done();
      }
    });
  });

  // Imprimir informe.
  document.querySelectorAll("[data-print]").forEach(function (btn) {
    btn.addEventListener("click", function () { window.print(); });
  });

  // Formulario por pasos (nueva visita / edición).
  document.querySelectorAll("form[data-stepper]").forEach(function (form) {
    var steps = Array.prototype.slice.call(form.querySelectorAll("[data-step]"));
    var tabs = Array.prototype.slice.call(form.querySelectorAll("[data-step-to]"));
    var prev = form.querySelector("[data-step-prev]");
    var next = form.querySelector("[data-step-next]");
    if (!steps.length) return;
    form.classList.add("js-stepper");
    var current = 0;
    steps.forEach(function (step, i) {
      if (step.querySelector(".has-error")) { tabs[i] && tabs[i].classList.add("has-error"); }
    });
    var firstError = steps.findIndex(function (s) { return s.querySelector(".has-error"); });
    function show(i) {
      current = Math.max(0, Math.min(steps.length - 1, i));
      steps.forEach(function (s, j) { s.classList.toggle("current", j === current); });
      tabs.forEach(function (t, j) { t.classList.toggle("current", j === current); });
      prev.style.visibility = current === 0 ? "hidden" : "visible";
      next.style.display = current === steps.length - 1 ? "none" : "";
    }
    tabs.forEach(function (t) { t.addEventListener("click", function () { show(parseInt(t.dataset.stepTo, 10)); }); });
    prev.addEventListener("click", function () { show(current - 1); window.scrollTo({ top: 0, behavior: "smooth" }); });
    next.addEventListener("click", function () { show(current + 1); window.scrollTo({ top: 0, behavior: "smooth" }); });
    show(firstError >= 0 ? firstError : 0);
  });

  // Evidencias: filtra los registros según el tipo seleccionado.
  var evType = document.querySelector("[data-ev-type]");
  var evRecord = document.querySelector("[data-ev-record]");
  if (evType && evRecord) {
    var sync = function () {
      var first = null;
      Array.prototype.forEach.call(evRecord.options, function (o) {
        var match = o.dataset.type === evType.value;
        o.hidden = !match; o.disabled = !match;
        if (match && !first) first = o;
      });
      if (first) { evRecord.value = first.value; } else { evRecord.value = ""; }
    };
    evType.addEventListener("change", sync);
    sync();
  }

  // Incidencia nueva: al cambiar de sesión se recargan sus pruebas.
  document.querySelectorAll("[data-reload-on-change]").forEach(function (sel) {
    sel.addEventListener("change", function () {
      var url = new URL(window.location.href);
      url.searchParams.set(sel.dataset.reloadOnChange, sel.value);
      url.searchParams.delete("prueba");
      window.location.href = url.toString();
    });
  });

  // Comparación: entre 2 y 6 sesiones.
  var compareBtn = document.querySelector("[data-compare-submit]");
  if (compareBtn) {
    var boxes = document.querySelectorAll("[data-compare]");
    var update = function () {
      var n = Array.prototype.filter.call(boxes, function (b) { return b.checked; }).length;
      compareBtn.disabled = n < 2 || n > 6;
      compareBtn.textContent = n ? "Comparar (" + n + ")" : "Comparar";
    };
    boxes.forEach(function (b) { b.addEventListener("change", update); });
    update();
  }

  // Áreas de texto que crecen con el contenido.
  document.querySelectorAll("textarea.autosize").forEach(function (ta) {
    var fit = function () { ta.style.height = "auto"; ta.style.height = (ta.scrollHeight + 2) + "px"; };
    ta.addEventListener("input", fit); fit();
  });
})();
