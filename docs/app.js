const clusters = [
  {id: "stcrg", branch: "metrics-stcrg", encrypted: true},
  {id: "gb10", branch: "metrics-gb10", encrypted: false},
];
const owner = location.hostname.endsWith("github.io") ? location.hostname.split(".")[0] : "markli1hoshipu";
const repo = location.hostname.endsWith("github.io") ? location.pathname.split("/").filter(Boolean)[0] : "gpu-queue-probe";
const copy = {
  zh: {
    subtitle:"持续记录真实的 GPU 排队等待时间", primaryLabel:"核心指标", historyTitle:"等待时间历史",
    historyDescription:"每个点代表一次真正获得 GPU 的探针作业。", footer:"每分钟采样 · 每 5 分钟发布 · 时间均为 UTC",
    cluster:"集群", connecting:"连接中", online:"在线", protectedTitle:"数据已加密",
    protectedText:"输入访问密码后在本机浏览器中解密。", password:"访问密码", unlock:"解锁", wrongPassword:"密码错误或数据暂不可用",
    pendingJobs:"GPU 等待队列", pendingGpu:"排队 GPU 需求", runningJobs:"运行中作业", jobs:"个作业",
    oneGpu:"1 GPU 等待", twoGpu:"2 GPU 等待", median:"中位数", p95:"P95", samples:"样本", collecting:"正在收集完成样本", updated:"更新于", seconds:"秒", minutes:"分钟", hours:"小时"
  },
  en: {
    subtitle:"Continuous, real-world GPU queue wait measurements", primaryLabel:"Primary signal", historyTitle:"Wait-time history",
    historyDescription:"Each point is a probe that actually received its GPU allocation.", footer:"Sampled every minute · Published every 5 minutes · UTC",
    cluster:"Cluster", connecting:"Connecting", online:"Online", protectedTitle:"Encrypted data",
    protectedText:"Enter the access password to decrypt locally in this browser.", password:"Access password", unlock:"Unlock", wrongPassword:"Incorrect password or data unavailable",
    pendingJobs:"GPU queue", pendingGpu:"Queued GPU demand", runningJobs:"Running jobs", jobs:"jobs",
    oneGpu:"1 GPU wait", twoGpu:"2 GPU wait", median:"Median", p95:"P95", samples:"samples", collecting:"Collecting completed samples", updated:"Updated", seconds:"sec", minutes:"min", hours:"hr"
  }
};
let language = localStorage.getItem("gpuq-language") || (navigator.language.startsWith("zh") ? "zh" : "en");
const cards = new Map();

function t(key) { return copy[language][key]; }
function applyLanguage() {
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach(node => { node.textContent = t(node.dataset.i18n); });
  document.querySelectorAll("[data-lang]").forEach(button => button.classList.toggle("active", button.dataset.lang === language));
  cards.forEach(({data, card}) => { if (data) fillCard(card, data); });
}
document.querySelectorAll("[data-lang]").forEach(button => button.addEventListener("click", () => {
  language = button.dataset.lang; localStorage.setItem("gpuq-language", language); applyLanguage();
}));

function rawUrl(branch, filename) {
  return `https://raw.githubusercontent.com/${owner}/${repo}/${branch}/data/${filename}?t=${Date.now()}`;
}
function fromBase64(value) { return Uint8Array.from(atob(value), character => character.charCodeAt(0)); }
async function decryptEnvelope(envelope, password) {
  const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    {name:"PBKDF2", salt:fromBase64(envelope.salt), iterations:envelope.iterations, hash:"SHA-256"},
    material, {name:"AES-GCM", length:256}, false, ["decrypt"]
  );
  const clear = await crypto.subtle.decrypt({name:"AES-GCM", iv:fromBase64(envelope.nonce)}, key, fromBase64(envelope.ciphertext));
  return JSON.parse(new TextDecoder().decode(clear));
}
function percentile(values, fraction) {
  if (!values.length) return null;
  const sorted = [...values].sort((a,b) => a-b);
  return sorted[Math.ceil((sorted.length - 1) * fraction)];
}
function duration(value) {
  if (value == null) return "—";
  if (value < 60) return `${Math.round(value)} ${t("seconds")}`;
  if (value < 3600) return `${(value / 60).toFixed(value < 600 ? 1 : 0)} ${t("minutes")}`;
  return `${(value / 3600).toFixed(1)} ${t("hours")}`;
}
function chart(values) {
  if (!values.length) return `<div class="empty-chart">${t("collecting")}</div>`;
  const points = values.slice(-40);
  const width = 420, height = 96, pad = 8, maximum = Math.max(...points, 1);
  const coordinates = points.map((value,index) => {
    const x = points.length === 1 ? width / 2 : pad + index * (width - pad * 2) / (points.length - 1);
    const y = height - pad - (value / maximum) * (height - pad * 2);
    return [x,y,value];
  });
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img">
    <line class="gridline" x1="0" y1="${height-pad}" x2="${width}" y2="${height-pad}"></line>
    <polyline class="line" points="${coordinates.map(p => `${p[0]},${p[1]}`).join(" ")}"></polyline>
    ${coordinates.map(p => `<circle class="dot" cx="${p[0]}" cy="${p[1]}" r="3"><title>${duration(p[2])}</title></circle>`).join("")}
  </svg>`;
}
function historySeries(data, gpuCount) {
  const observations = (data.wait_history || []).filter(item => item.gpu_count === gpuCount && item.queue_wait_seconds != null);
  const values = observations.map(item => Number(item.queue_wait_seconds));
  const latest = values[values.length - 1];
  return `<section class="series">
    <div class="series-head"><div><span class="series-label">${gpuCount === 1 ? t("oneGpu") : t("twoGpu")}</span><strong class="series-latest">${duration(latest)}</strong></div>
    <div class="series-stats">${t("median")} ${duration(percentile(values,.5))}<br>${t("p95")} ${duration(percentile(values,.95))}<br>${values.length} ${t("samples")}</div></div>
    ${chart(values)}
  </section>`;
}
function fillCard(card, data) {
  card.querySelector(".history-grid").innerHTML = historySeries(data, 1) + historySeries(data, 2);
  for (const field of ["pending_jobs", "pending_gpu_demand", "running_jobs"]) card.querySelector(`[data-field=${field}]`).textContent = data.queue?.[field] ?? "—";
  card.querySelector(".status").textContent = t("online");
  card.querySelector(".status").classList.remove("error");
  card.querySelector(".updated").textContent = `${t("updated")} ${data.generated_at}`;
  card.querySelector(".data-panel").classList.remove("hidden");
}
async function fetchPublic(definition) {
  const response = await fetch(rawUrl(definition.branch, "latest.json"), {cache:"no-store"});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
async function unlock(definition, password) {
  const response = await fetch(rawUrl(definition.branch, "latest.enc.json"), {cache:"no-store"});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return decryptEnvelope(await response.json(), password);
}
async function refresh(definition) {
  const state = cards.get(definition.id);
  if (definition.encrypted && !state.password) return;
  try {
    const data = definition.encrypted ? await unlock(definition, state.password) : await fetchPublic(definition);
    state.data = data; fillCard(state.card, data);
  } catch (error) {
    state.card.querySelector(".status").textContent = definition.encrypted ? t("wrongPassword") : error.message;
    state.card.querySelector(".status").classList.add("error");
  }
}
function createCard(definition) {
  const fragment = document.querySelector("#cluster-card").content.cloneNode(true);
  const card = fragment.querySelector(".card");
  card.querySelector("h3").textContent = definition.id;
  const lockPanel = card.querySelector(".lock-panel");
  if (definition.encrypted) {
    lockPanel.classList.remove("hidden");
    card.querySelector(".unlock-form").addEventListener("submit", async event => {
      event.preventDefault();
      const password = event.currentTarget.querySelector("input").value;
      const state = cards.get(definition.id);
      try {
        const data = await unlock(definition, password);
        state.password = password; state.data = data;
        lockPanel.classList.add("hidden"); fillCard(card, data);
      } catch (_) { card.querySelector(".unlock-error").textContent = t("wrongPassword"); }
    });
  }
  document.querySelector("#clusters").append(card);
  cards.set(definition.id, {card, data:null, password:null});
  if (!definition.encrypted) refresh(definition);
}
clusters.forEach(createCard);
applyLanguage();
setInterval(() => clusters.forEach(refresh), 60_000);
