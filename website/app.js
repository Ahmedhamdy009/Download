const form = document.querySelector("#download-form");
const urlInput = document.querySelector("#url");
const qualityRow = document.querySelector("#quality-row");
const qualityInput = document.querySelector("#quality");
const submitButton = document.querySelector("#submit-button");
const pasteButton = document.querySelector("#paste-button");
const progressPanel = document.querySelector("#progress-panel");
const progressMessage = document.querySelector("#progress-message");
const progressPercent = document.querySelector("#progress-percent");
const progressFill = document.querySelector("#progress-fill");
const progressDetail = document.querySelector("#progress-detail");
const saveButton = document.querySelector("#save-button");
const errorMessage = document.querySelector("#error-message");
let selectedKind = "video";

function setKind(kind) {
  selectedKind = kind;
  document.querySelectorAll(".format-option").forEach((button) => {
    const selected = button.dataset.kind === kind;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  qualityRow.hidden = kind !== "video";
}

document.querySelectorAll(".format-option").forEach((button) => {
  button.addEventListener("click", () => setKind(button.dataset.kind));
});

pasteButton.addEventListener("click", async () => {
  try {
    urlInput.value = await navigator.clipboard.readText();
    urlInput.focus();
  } catch {
    urlInput.focus();
    urlInput.select();
  }
});

function setProgress(job) {
  const percent = Number(job.progress || 0);
  progressPanel.hidden = false;
  progressMessage.textContent = job.message || "جارٍ التحميل…";
  progressPercent.textContent = `${percent}%`;
  progressFill.style.width = `${percent}%`;
  progressDetail.textContent = job.state === "done" ? "الملف جاهز للحفظ على جهازك." : "سيب الصفحة مفتوحة لحد ما التحميل يكتمل.";
}

async function watchJob(id) {
  while (true) {
    const response = await fetch(`/api/status?id=${encodeURIComponent(id)}`, { cache: "no-store" });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "تعذّر متابعة التحميل.");
    setProgress(job);
    if (job.state === "done") {
      saveButton.href = `/api/file?id=${encodeURIComponent(id)}`;
      saveButton.hidden = false;
      break;
    }
    if (job.state === "error") throw new Error(job.message || "فشل التحميل.");
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorMessage.hidden = true;
  progressPanel.hidden = true;
  saveButton.hidden = true;
  submitButton.disabled = true;
  submitButton.querySelector("span:first-child").textContent = "جاري بدء التحميل…";

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: urlInput.value.trim(), kind: selectedKind, quality: qualityInput.value }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "تعذّر بدء التحميل.");
    await watchJob(result.id);
  } catch (error) {
    errorMessage.textContent = error.message || "حصلت مشكلة في الاتصال بالتطبيق.";
    errorMessage.hidden = false;
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector("span:first-child").textContent = "ابدأ التحميل";
  }
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js").catch(() => {}));
}
