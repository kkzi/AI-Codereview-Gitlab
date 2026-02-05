"use strict";

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderMarkdown(target, text) {
  if (!target) return;
  if (!text) {
    target.textContent = "";
    return;
  }

  if (window.marked && window.DOMPurify) {
    const rawHtml = window.marked.parse(text, { breaks: true });
    target.innerHTML = window.DOMPurify.sanitize(rawHtml);
    return;
  }

  target.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");
}
