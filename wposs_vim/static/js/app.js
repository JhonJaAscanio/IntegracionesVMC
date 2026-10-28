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

/* Selección de archivos antes de guardar: lista con miniatura, quitar archivos
   uno a uno y acumular selecciones sucesivas en el mismo campo. */
(function () {
  "use strict";
  if (typeof DataTransfer === "undefined") return;

  function formatSize(bytes) {
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
    return Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  function fileKey(f) { return f.name + "|" + f.size + "|" + f.lastModified; }

  document.querySelectorAll("input[type=file][multiple]").forEach(function (input) {
    var kept = [];
    var urls = [];
    var summary = input.parentElement.querySelector("[data-file-summary]");
    var list = document.createElement("ul");
    list.className = "file-picks";
    list.hidden = true;
    input.insertAdjacentElement("afterend", list);

    function render() {
      urls.forEach(function (u) { URL.revokeObjectURL(u); });
      urls = [];
      list.textContent = "";
      list.hidden = kept.length === 0;
      kept.forEach(function (file, index) {
        var item = document.createElement("li");
        var thumb = document.createElement("span");
        thumb.className = "file-thumb";
        if (/^image\/(jpeg|png|gif|webp|bmp)$/.test(file.type)) {
          var img = document.createElement("img");
          var url = URL.createObjectURL(file);
          urls.push(url);
          img.src = url;
          img.alt = "";
          thumb.appendChild(img);
        } else {
          thumb.textContent = (file.name.split(".").pop() || "?").slice(0, 4).toUpperCase();
        }
        var info = document.createElement("span");
        info.className = "file-info";
        var name = document.createElement("span");
        name.className = "file-name";
        name.textContent = file.name;
        name.title = file.name;
        var size = document.createElement("span");
        size.className = "muted small";
        size.textContent = formatSize(file.size);
        info.appendChild(name);
        info.appendChild(size);
        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "btn btn-sm btn-ghost";
        remove.textContent = "Quitar";
        remove.setAttribute("aria-label", "Quitar " + file.name);
        remove.addEventListener("click", function () {
          kept.splice(index, 1);
          sync();
          input.focus();
        });
        item.appendChild(thumb);
        item.appendChild(info);
        item.appendChild(remove);
        list.appendChild(item);
      });
      if (summary) {
        var total = kept.reduce(function (acc, f) { return acc + f.size; }, 0);
        summary.textContent = kept.length ? kept.length + " archivo(s) · " + formatSize(total) : "";
      }
    }

    function sync() {
      var dt = new DataTransfer();
      kept.forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
      render();
    }

    input.addEventListener("change", function () {
      var seen = {};
      kept.forEach(function (f) { seen[fileKey(f)] = true; });
      Array.prototype.forEach.call(input.files || [], function (f) {
        if (!seen[fileKey(f)]) { kept.push(f); seen[fileKey(f)] = true; }
      });
      sync();
    });

    if (input.form) {
      input.form.addEventListener("reset", function () { kept = []; render(); });
    }
  });
})();

/* Formulario de visita: país según cliente, ciudades según país y objetivo según tipo de prueba. */
(function () {
  "use strict";

  function readMap(el, attr) {
    try { return JSON.parse(el.getAttribute(attr) || "{}"); } catch (e) { return {}; }
  }

  document.querySelectorAll("select[data-city-map]").forEach(function (pais) {
    var map = readMap(pais, "data-city-map");
    var ciudad = document.getElementById(pais.dataset.cityTarget);
    if (!ciudad) return;
    pais.addEventListener("change", function () {
      var current = ciudad.value;
      var cities = map[pais.value] || [];
      ciudad.textContent = "";
      var blank = document.createElement("option");
      blank.value = "";
      blank.textContent = pais.value ? "Seleccione…" : "Seleccione el país primero";
      ciudad.appendChild(blank);
      cities.forEach(function (c) {
        var o = document.createElement("option");
        o.value = c; o.textContent = c;
        if (c === current) o.selected = true;
        ciudad.appendChild(o);
      });
    });
  });

  document.querySelectorAll("select[data-country-map]").forEach(function (cliente) {
    var map = readMap(cliente, "data-country-map");
    var pais = document.getElementById(cliente.dataset.countryTarget);
    if (!pais) return;
    cliente.addEventListener("change", function () {
      var target = map[cliente.value];
      if (!target || pais.value === target) return;
      var exists = Array.prototype.some.call(pais.options, function (o) { return o.value === target; });
      if (exists) {
        pais.value = target;
        pais.dispatchEvent(new Event("change"));
      }
    });
  });

  document.querySelectorAll("select[data-objective-map]").forEach(function (tipo) {
    var map = readMap(tipo, "data-objective-map");
    var objetivo = document.getElementById(tipo.dataset.objectiveTarget);
    if (!objetivo) return;
    var templates = Object.keys(map).map(function (k) { return map[k]; });
    function apply() {
      var text = map[tipo.value];
      if (!text) return;
      var current = objetivo.value.trim();
      if (!current || templates.indexOf(current) >= 0) {
        objetivo.value = text;
        objetivo.dispatchEvent(new Event("input"));
      }
    }
    tipo.addEventListener("change", apply);
    if (!objetivo.value.trim()) apply();
  });
})();
