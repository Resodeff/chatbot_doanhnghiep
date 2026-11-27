/* ============================================================
   Linh Kiện PC — JS giao diện
   1. Nút chuyển Dark / Light (lưu localStorage "lkpc-theme").
      Lưu ý: <html> đã được gán data-theme từ trước khi CSS load
      bằng đoạn script nhỏ trong <head> của home.html (chống chớp
      màn hình). File này chỉ gắn sự kiện cho nút bấm.
   2. Chat tư vấn — logic giữ nguyên bản home.html cũ, chỉ chuyển
      URL API + CSRF token sang biến toàn cục window.CHAT_CONFIG
      (do file static không chạy qua template engine của Django).
   ============================================================ */
(function () {
  "use strict";

  /* ---------- 1. Dark / Light ---------- */
  var STORAGE_KEY = "lkpc-theme";
  var root = document.documentElement;
  var toggle = document.getElementById("theme-toggle");

  function currentTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) { /* kệ */ }
    if (toggle) {
      toggle.setAttribute("aria-label",
        theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối");
      toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    }
  }
  if (toggle) {
    toggle.addEventListener("click", function () {
      applyTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  }

  /* ---------- 2. Chat tư vấn ---------- */
  var box = document.getElementById("chat-box");
  var msgs = document.getElementById("chat-msgs");
  var input = document.getElementById("chat-input");
  var chatHistory = [];   // lịch sử hội thoại gửi kèm để chatbot nhớ ngữ cảnh
  var chatBtn = document.getElementById("chat-btn");
  var chatForm = document.getElementById("chat-form");

  if (chatBtn && box) {
    chatBtn.addEventListener("click", function () {
      box.classList.toggle("open");
      if (box.classList.contains("open") && input) input.focus();
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && box) box.classList.remove("open");
  });

  // Hàm chuyển đổi Markdown ảnh và chữ in đậm sang HTML an toàn
  function formatReply(text) {
    var html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Biến ![Tên](URL) thành thẻ <img> (bấm vào mở tab mới xem ảnh gốc)
    html = html.replace(
      /!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener"><img src="$2" alt="$1" loading="lazy"></a>'
    );

    // Biến **chữ in đậm** thành <strong>
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    return html;
  }

  function add(text, who) {
    var d = document.createElement("div");
    d.className = "msg " + who;
    if (who === "bot") {
      d.innerHTML = formatReply(text);
    } else {
      d.textContent = text;
    }
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
    return d;
  }

  if (chatForm && input && msgs) {
    chatForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      var text = input.value.trim();
      if (!text) return;
      add(text, "me");
      input.value = "";
      var wait = add("Đang trả lời...", "bot");
      try {
        var cfg = window.CHAT_CONFIG || {};
        var res = await fetch(cfg.apiUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrfToken || "" },
          body: JSON.stringify({ message: text, history: chatHistory.slice(-12) }),
        });
        var data = await res.json();
        wait.innerHTML = formatReply(data.reply);

        // Tự động cuộn xuống đáy sau khi ảnh load xong để không bị che chữ bên dưới
        wait.querySelectorAll("img").forEach(function (img) {
          img.onload = function () { msgs.scrollTop = msgs.scrollHeight; };
        });
        msgs.scrollTop = msgs.scrollHeight;

        chatHistory.push({ role: "user", content: text }, { role: "assistant", content: data.reply });
      } catch (err) {
        wait.textContent = "Lỗi kết nối, bạn thử lại nhé.";
      }
    });
  }
})();