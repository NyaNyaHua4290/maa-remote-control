/* MAA 远程控制 - 前端小脚本：复制、确认、状态轮询 */
(function () {
  "use strict";

  const STATUS_LABELS = {
    pending: "等待下发",
    delivered: "已下发",
    success: "成功",
    failed: "失败",
    timeout: "超时",
    canceled: "已取消",
  };

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    // 非 HTTPS 环境下的兜底方案
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand("copy");
    } finally {
      document.body.removeChild(textarea);
    }
    return Promise.resolve();
  }

  function bindCopy() {
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        const input = document.getElementById(button.getAttribute("data-copy"));
        if (!input) return;
        copyText(input.value).then(function () {
          const original = button.textContent;
          button.textContent = "已复制";
          setTimeout(function () {
            button.textContent = original;
          }, 1200);
        });
      });
    });

    document.querySelectorAll("[data-copy-text]").forEach(function (button) {
      button.addEventListener("click", function () {
        copyText(button.getAttribute("data-copy-text")).then(function () {
          const original = button.textContent;
          button.textContent = "已复制";
          setTimeout(function () {
            button.textContent = original;
          }, 1200);
        });
      });
    });
  }

  function bindConfirm() {
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.getAttribute("data-confirm"))) {
          event.preventDefault();
        }
      });
    });
  }

  function setOnline(online) {
    const dot = document.querySelector("[data-online-dot]");
    if (dot) {
      dot.classList.toggle("dot-online", online);
      dot.classList.toggle("dot-offline", !online);
    }
  }

  function refreshDashboard() {
    fetch("/api/devices", { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("bad status");
        return response.json();
      })
      .then(function (data) {
        let online = 0;
        data.devices.forEach(function (device) {
          if (device.online) online += 1;
          const card = document.querySelector('[data-device-id="' + device.id + '"]');
          if (!card) return;
          const dot = card.querySelector("[data-online-dot]");
          if (dot) {
            dot.classList.toggle("dot-online", device.online);
            dot.classList.toggle("dot-offline", !device.online);
          }
          const text = card.querySelector("[data-online-text]");
          if (text) {
            text.textContent = (device.online ? "在线" : "离线") + " · 最后活动 " + relative(device.last_seen_at);
          }
        });
        const counter = document.querySelector("[data-online-count]");
        if (counter) counter.textContent = online;
      })
      .catch(function () {});
  }

  function relative(iso) {
    if (!iso) return "从未";
    const seconds = Math.max(0, Math.round((Date.now() - new Date(iso + "Z").getTime()) / 1000));
    if (seconds < 5) return "刚刚";
    if (seconds < 60) return seconds + " 秒前";
    if (seconds < 3600) return Math.floor(seconds / 60) + " 分钟前";
    if (seconds < 86400) return Math.floor(seconds / 3600) + " 小时前";
    return Math.floor(seconds / 86400) + " 天前";
  }

  function refreshDevice() {
    const table = document.querySelector("[data-task-table]");
    if (!table) return;
    const deviceId = window.location.pathname.split("/").filter(Boolean).pop();
    if (!deviceId || isNaN(Number(deviceId))) return;

    fetch("/api/devices/" + deviceId, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("bad status");
        return response.json();
      })
      .then(function (data) {
        setOnline(data.device.online);

        const pending = document.querySelector("[data-pending-count]");
        if (pending) pending.textContent = data.pending;

        const rows = table.querySelectorAll("tr[data-task-id]");
        if (rows.length !== data.tasks.length) {
          window.location.reload();
          return;
        }

        data.tasks.forEach(function (task) {
          const row = table.querySelector('[data-task-id="' + task.id + '"]');
          if (!row) return;
          const cell = row.querySelector(".cell-status");
          if (cell && cell.getAttribute("data-status") !== task.status) {
            cell.setAttribute("data-status", task.status);
            const badge = cell.querySelector(".badge");
            if (badge) {
              badge.textContent = STATUS_LABELS[task.status] || task.status;
              badge.className = "badge badge-" + task.status;
            }
            if (task.has_screenshot) {
              const shotCell = row.querySelector(".cell-shot");
              if (shotCell && !shotCell.querySelector("a")) {
                shotCell.innerHTML =
                  '<a href="/devices/' + deviceId + "/screenshot/" + task.id +
                  '" target="_blank" rel="noopener">查看</a>';
              }
            }
          }
        });
      })
      .catch(function () {});
  }

  function startPolling() {
    const onDashboard = !!document.querySelector("[data-device-grid]");
    const onDevice = !!document.querySelector("[data-task-table]");

    if (onDashboard) refreshDashboard();
    if (onDevice) refreshDevice();
    if (!onDashboard && !onDevice) return;

    setInterval(function () {
      if (document.hidden) return;
      if (onDashboard) refreshDashboard();
      if (onDevice) refreshDevice();
    }, 5000);
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindCopy();
    bindConfirm();
    startPolling();
  });
})();
