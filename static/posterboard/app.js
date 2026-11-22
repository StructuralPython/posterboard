// Posterboard: editor helpers and the preview card's behaviour.
(function () {
  "use strict";

  // "…more" shows only when the collapsed text is cut off, as on LinkedIn.
  function updateMore(root) {
    root.querySelectorAll("[data-preview]").forEach(function (preview) {
      var text = preview.querySelector("[data-li-text]");
      var more = preview.querySelector("[data-li-more]");
      if (!text || !more) return;
      var collapsed = preview.dataset.view === "collapsed";
      more.hidden = !(collapsed && text.scrollHeight > text.clientHeight + 1);
    });
  }

  function setPressed(group, attr, value) {
    group.querySelectorAll("[" + attr + "]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute(attr) === value));
    });
  }

  document.addEventListener("click", function (event) {
    var t = event.target.closest("button, [data-copy]");
    if (!t) return;
    var preview = t.closest("[data-preview]");

    if (t.hasAttribute("data-set-view")) {
      preview.dataset.view = t.getAttribute("data-set-view");
      setPressed(preview, "data-set-view", preview.dataset.view);
      updateMore(document);
    } else if (t.hasAttribute("data-set-width")) {
      preview.dataset.width = t.getAttribute("data-set-width");
      setPressed(preview, "data-set-width", preview.dataset.width);
      setTimeout(function () { updateMore(document); }, 220);
    } else if (t.hasAttribute("data-li-more")) {
      preview.dataset.view = "expanded";
      setPressed(preview, "data-set-view", "expanded");
      updateMore(document);
    } else if (t.hasAttribute("data-carousel-prev") || t.hasAttribute("data-carousel-next")) {
      var carousel = t.closest("[data-carousel]");
      var pages = carousel.querySelectorAll(".li-doc-pages img");
      var index = Array.prototype.findIndex.call(pages, function (p) { return !p.hidden; });
      var next = index + (t.hasAttribute("data-carousel-next") ? 1 : -1);
      if (next < 0 || next >= pages.length) return;
      pages[index].hidden = true;
      pages[next].hidden = false;
      carousel.querySelector("[data-carousel-index]").textContent = String(next + 1);
    } else if (t.hasAttribute("data-wrap")) {
      wrapSelection(t.getAttribute("data-wrap"));
    } else if (t.hasAttribute("data-copy")) {
      var source = document.querySelector(t.getAttribute("data-copy"));
      var done = function () { var old = t.textContent; t.textContent = "Copied"; setTimeout(function () { t.textContent = old; }, 1500); };
      if (navigator.clipboard) {
        navigator.clipboard.writeText(source.textContent).then(done, function () { selectText(source); });
      } else { selectText(source); }
    }
  });

  function selectText(el) {
    var range = document.createRange();
    range.selectNodeContents(el);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  // Bold / italic / code buttons and shortcuts wrap the selection in Markdown.
  function wrapSelection(mark) {
    var area = document.querySelector("textarea[name=body]");
    if (!area) return;
    var start = area.selectionStart, end = area.selectionEnd, value = area.value;
    var selected = value.slice(start, end) || "text";
    area.setRangeText(mark + selected + mark, start, end, "end");
    area.selectionStart = start + mark.length;
    area.selectionEnd = start + mark.length + selected.length;
    area.focus();
    area.dispatchEvent(new Event("input", { bubbles: true }));
  }

  document.addEventListener("keydown", function (event) {
    if (!(event.ctrlKey || event.metaKey) || event.target.name !== "body") return;
    if (event.key === "b") { event.preventDefault(); wrapSelection("**"); }
    if (event.key === "i") { event.preventDefault(); wrapSelection("*"); }
  });

  // Confirm before posting now or deleting.
  document.addEventListener("submit", function (event) {
    var button = event.submitter;
    if (button && button.dataset.confirm && !window.confirm(button.dataset.confirm)) {
      event.preventDefault();
    }
  });

  // Show a newly chosen file in the preview before it is saved.
  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!input.matches("[data-media-input]")) return;
    var slot = document.querySelector("[data-media-slot]");
    var file = input.files && input.files[0];
    if (!slot || !file) return;
    var url = URL.createObjectURL(file);
    var name = file.name.toLowerCase();
    slot.innerHTML = "";
    if (/\.(jpe?g|png|gif)$/.test(name)) {
      var img = document.createElement("img"); img.src = url; img.alt = ""; slot.appendChild(img);
    } else if (/\.mp4$/.test(name)) {
      var video = document.createElement("video"); video.src = url; video.controls = true; slot.appendChild(video);
    } else if (/\.pdf$/.test(name)) {
      var doc = document.createElement("div");
      doc.className = "li-doc-placeholder";
      doc.textContent = file.name + ": the carousel pages appear here once you save.";
      slot.appendChild(doc);
    }
  });

  document.addEventListener("DOMContentLoaded", function () { updateMore(document); });
  document.addEventListener("htmx:afterSwap", function () { updateMore(document); });
  window.addEventListener("resize", function () { updateMore(document); });
})();
