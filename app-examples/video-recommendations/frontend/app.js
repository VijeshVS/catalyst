const PLAN_LABELS = { free: "Free", premium: "Premium", family: "Family" };
const REGION_LABELS = {
  IN: "India",
  US: "United States",
  GB: "United Kingdom",
  JP: "Japan",
  DE: "Germany",
  BR: "Brazil",
  FR: "France",
  AU: "Australia",
  PK: "Pakistan",
  IS: "Iceland",
  AE: "UAE",
};
const COUNTRY_CODES = new Set(["IN", "US", "GB", "JP", "DE", "BR", ""]);
const PLANS = new Set(["free", "premium", "family"]);

const REASON_TEXT = {
  ENABLE_ALL_USERS: "Served true to everyone; no targeting or rollout was consulted.",
  KILL_SWITCH_ACTIVE: "Killed for everyone, so the flag serves false.",
  RULE_AND_ROLLOUT: "A targeting rule matched, and this viewer's bucket is inside the rollout.",
  RULE_OUTSIDE_ROLLOUT: "A targeting rule matched, but this viewer's bucket fell outside the rollout.",
  PERCENTAGE_ROLLOUT: "No targeting rules; this viewer's bucket is inside the percentage rollout.",
  PERCENTAGE_OUTSIDE_ROLLOUT: "This viewer's bucket is outside the percentage rollout.",
  DEFAULT_VALUE: "No targeting rule matched, so the flag is false for this viewer.",
  FLAG_NOT_FOUND: "This flag is not present in the environment snapshot.",
  NO_SNAPSHOT: "No snapshot loaded, so the SDK failed closed.",
};

const state = {
  userId: "viewer-1",
  country: "IN",
  genre: "Sci-Fi",
  plan: "premium",
  data: null,
  controller: null,
  requestId: 0,
  detail: null,
  lastFocus: null,
};

const els = {
  form: document.querySelector("#viewer-form"),
  country: document.querySelector("#country"),
  genre: document.querySelector("#genre"),
  userId: document.querySelector("#user-id"),
  shuffle: document.querySelector("#shuffle"),
  envPill: document.querySelector("#env-pill"),
  statusDot: document.querySelector("#status-dot"),
  healthText: document.querySelector("#health-text"),
  notice: document.querySelector("#notice"),
  noticeText: document.querySelector("#notice-text"),
  modeEyebrow: document.querySelector("#mode-eyebrow"),
  modeBadge: document.querySelector("#mode-badge"),
  modeLabel: document.querySelector("#mode-label"),
  railTitle: document.querySelector("#rail-title"),
  railSubtitle: document.querySelector("#rail-subtitle"),
  snapshotMeta: document.querySelector("#snapshot-meta"),
  snapshotMeta2: document.querySelector("#snapshot-meta-2"),
  rail: document.querySelector("#rail"),
  premiumSection: document.querySelector("#premium-section"),
  premiumRail: document.querySelector("#premium-rail"),
  flagGrid: document.querySelector("#flag-grid"),
  flagCounter: document.querySelector("#flag-counter"),
  dialog: document.querySelector("#detail-dialog"),
  detailClose: document.querySelector("#detail-close"),
  detailArt: document.querySelector("#detail-art"),
  detailGenre: document.querySelector("#detail-genre"),
  detailYear: document.querySelector("#detail-year"),
  detailPosterTitle: document.querySelector("#detail-poster-title"),
  detailPlay: document.querySelector("#detail-play"),
  previewLabel: document.querySelector("#preview-label"),
  detailKicker: document.querySelector("#detail-kicker"),
  detailTitle: document.querySelector("#detail-title"),
  detailTagline: document.querySelector("#detail-tagline"),
  detailMetaYear: document.querySelector("#detail-meta-year"),
  detailMetaRuntime: document.querySelector("#detail-meta-runtime"),
  detailMetaRating: document.querySelector("#detail-meta-rating"),
  detailMetaMarkets: document.querySelector("#detail-meta-markets"),
  detailSignals: document.querySelector("#detail-signals"),
  autoplayNote: document.querySelector("#autoplay-note"),
};

/* ------------------------------------------------------------- utilities */

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function params() {
  return new URLSearchParams({
    user_id: state.userId,
    country: state.country,
    genre: state.genre,
    plan: state.plan,
  });
}

function syncUrl() {
  const query = params().toString();
  history.replaceState(null, "", `${location.pathname}?${query}`);
}

function hydrateFromUrl() {
  const query = new URLSearchParams(location.search);
  const country = (query.get("country") ?? "IN").toUpperCase();
  const genre = query.get("genre") ?? "Sci-Fi";
  const plan = (query.get("plan") ?? "premium").toLowerCase();
  const userId = (query.get("user_id") ?? "viewer-1").trim();

  if (COUNTRY_CODES.has(country)) state.country = country;
  if (PLANS.has(plan)) state.plan = plan;
  if (userId) state.userId = userId.slice(0, 80);
  if ([...els.genre.options].some((option) => option.value === genre)) {
    state.genre = genre;
  }

  els.country.value = state.country;
  els.genre.value = state.genre;
  els.userId.value = state.userId;
  const planInput = els.form.querySelector(`input[name="plan"][value="${state.plan}"]`);
  if (planInput) planInput.checked = true;
}

function formatRuntime(minutes) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours ? `${hours}h ${rest}m` : `${rest}m`;
}

function signalClass(text) {
  if (text.startsWith("Popular in")) return "signal location";
  if (text.startsWith("Matches your")) return "signal genre";
  if (text.startsWith("Early access")) return "signal premium";
  return "signal neutral";
}

function setStatus(kind, text) {
  els.statusDot.className = `status-dot ${kind}`;
  els.healthText.textContent = text;
}

/* ------------------------------------------------------------------ load */

async function load() {
  const requestId = ++state.requestId;
  state.controller?.abort();
  const controller = new AbortController();
  state.controller = controller;

  document.body.classList.add("is-loading");
  els.rail.setAttribute("aria-busy", "true");
  syncUrl();

  try {
    const response = await fetch(`/api/recommendations?${params().toString()}`, {
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`The recommendations API answered ${response.status}.`);
    const data = await response.json();
    if (requestId !== state.requestId) return;
    state.data = data;
    render(data);
  } catch (error) {
    if (error.name === "AbortError") return;
    setStatus("warn", "App offline");
    showNotice(
      `Could not load recommendations: ${error.message} Is the FastAPI process running?`,
      true,
    );
  } finally {
    if (requestId === state.requestId) {
      document.body.classList.remove("is-loading");
      els.rail.setAttribute("aria-busy", "false");
    }
  }
}

function showNotice(message, degraded = false) {
  els.notice.hidden = false;
  els.notice.classList.toggle("degraded", degraded);
  els.noticeText.textContent = message;
}

/* ---------------------------------------------------------------- render */

function render(data) {
  const { audience, snapshot, mode } = data;
  const personalized = mode === "personalized";

  els.envPill.hidden = false;
  els.envPill.textContent = snapshot.env;
  setStatus(
    snapshot.degraded ? "warn" : "ok",
    snapshot.degraded
      ? "Catalyst unreachable"
      : `Catalyst connected · ${snapshot.flag_count} flags`,
  );

  const snapshotLabel = `${snapshot.env} · v${snapshot.version} · ${snapshot.refreshes} refresh${
    snapshot.refreshes === 1 ? "" : "es"
  } · ${snapshot.not_modified} × 304`;
  els.snapshotMeta.textContent = snapshotLabel;
  els.snapshotMeta2.textContent = snapshotLabel;

  els.modeEyebrow.textContent = personalized ? "Personalized rail" : "Fallback rail";
  els.railTitle.textContent = personalized ? "Recommended for you" : "Trending now";
  els.railSubtitle.textContent = personalized
    ? `${data.recommendations.length} titles · ${audience.country_label} · ${audience.genre_label} · ${PLAN_LABELS[audience.plan]} plan`
    : "Global popularity · the recommendation-engine master switch is off";
  els.modeBadge.dataset.mode = mode;
  els.modeLabel.textContent = personalized ? "Personalized engine" : "Trending fallback";

  if (data.notice) {
    showNotice(data.notice, snapshot.degraded);
  } else {
    els.notice.hidden = true;
  }

  renderRail(els.rail, data.recommendations);

  const shelf = data.premium_shelf;
  els.premiumSection.hidden = shelf.length === 0;
  if (shelf.length) renderRail(els.premiumRail, shelf);

  els.flagCounter.textContent = `${data.flags.length} flags`;
  els.flagGrid.replaceChildren(...data.flags.map((flag, index) => flagCard(flag, index)));
}

function renderRail(container, items) {
  const fragment = document.createDocumentFragment();
  items.forEach((item, index) => fragment.append(card(item, index)));
  container.replaceChildren(fragment);
}

function card(item, index) {
  const article = make("article", "card");
  article.style.animationDelay = `${Math.min(index * 32, 260)}ms`;

  const poster = make("button", "card-poster");
  poster.type = "button";
  poster.style.setProperty("--hue", item.hue);
  poster.setAttribute("aria-label", `View details for ${item.title}`);

  const top = make("span", "poster-top");
  top.append(make("span", "", item.genres[0]));
  top.append(make("span", "", item.year));

  const title = make("span", "poster-title", item.title);

  const play = make("span", "poster-play");
  play.innerHTML =
    '<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true"><path d="M8 5.5v13l11-6.5-11-6.5Z" fill="currentColor"/></svg>';

  poster.append(top, title, play);
  poster.addEventListener("click", () => openDetail(item.id, poster));

  const body = make("div", "card-body");

  const meta = make("div", "card-meta");
  meta.append(make("span", "", `${formatRuntime(item.runtime)} · ${item.rating}`));
  meta.append(make("span", "match", `${item.match}% match`));

  const signals = make("div", "signals");
  item.signals.forEach((text) => signals.append(make("span", signalClass(text), text)));

  body.append(meta, signals);
  article.append(poster, body);
  return article;
}

function flagCard(flag, index) {
  const article = make("article", "flag-card");
  article.classList.toggle("is-on", flag.value);
  article.classList.toggle("is-master", flag.kind === "master");
  article.classList.toggle("is-rollout", flag.kind === "rollout");
  article.style.animationDelay = `${Math.min(index * 40, 200)}ms`;

  const top = make("div", "flag-top");
  const heading = make("div", "");
  heading.append(make("div", "flag-label", flag.label));
  const kindLabel =
    flag.kind === "master"
      ? "master switch"
      : flag.kind === "rollout"
        ? "percentage rollout"
        : "targeting rule";
  heading.append(make("div", "flag-kind", kindLabel));

  const value = make("span", `flag-value${flag.value ? " on" : ""}`, flag.value ? "ON" : "OFF");
  top.append(heading, value);

  const foot = make("div", "flag-foot");
  const reasonRow = make("div", "reason-row");
  reasonRow.append(make("code", "reason-code", flag.reason));
  if (flag.rule_id) {
    reasonRow.append(make("span", "rule-hint", `rule ${flag.rule_id.slice(0, 8)}`));
  }
  foot.append(reasonRow);
  foot.append(
    make("p", "reason-text", REASON_TEXT[flag.reason] ?? "The SDK returned this decision."),
  );

  if (flag.percentage !== null && flag.percentage < 100 && flag.bucket !== null) {
    foot.append(rollout(flag));
  }

  article.append(top, make("p", "flag-desc", flag.description), foot);
  return article;
}

function rollout(flag) {
  const wrapper = make("div", "rollout");
  const track = make("div", "rollout-track");

  const fill = make("span", "rollout-fill");
  fill.style.width = `${flag.percentage}%`;
  track.append(fill);

  const inside = flag.bucket < flag.percentage;
  const marker = make("span", `rollout-marker${inside ? " inside" : ""}`);
  marker.style.left = `${flag.bucket}%`;
  track.append(marker);

  const legend = make("div", "rollout-legend");
  legend.append(make("span", "", `${flag.percentage}% rollout`));
  legend.append(
    make("span", "", `bucket ${flag.bucket} · ${inside ? "inside" : "outside"}`),
  );

  wrapper.append(track, legend);
  return wrapper;
}

/* ---------------------------------------------------------------- detail */

function openDetail(id, trigger) {
  const data = state.data;
  if (!data) return;
  const inShelf = data.premium_shelf.some((item) => item.id === id);
  const item = [...data.recommendations, ...data.premium_shelf].find((row) => row.id === id);
  if (!item) return;

  state.detail = item;
  state.lastFocus = trigger ?? document.activeElement;

  els.detailArt.style.setProperty("--hue", item.hue);
  els.detailGenre.textContent = item.genres.join(" · ");
  els.detailYear.textContent = item.year;
  els.detailPosterTitle.textContent = item.title;
  els.detailKicker.textContent = inShelf
    ? "Early access shelf"
    : data.mode === "trending"
      ? "Trending rail"
      : "In your personalized rail";
  els.detailTitle.textContent = item.title;
  els.detailTagline.textContent = item.tagline;
  els.detailMetaYear.textContent = item.year;
  els.detailMetaRuntime.textContent = formatRuntime(item.runtime);
  els.detailMetaRating.textContent = item.rating;
  els.detailMetaMarkets.textContent = item.regions
    .map((code) => REGION_LABELS[code] ?? code)
    .join(", ");
  els.detailSignals.replaceChildren(
    ...item.signals.map((text) => make("span", signalClass(text), text)),
  );

  const autoplay = data.autoplay;
  const autoplayFlag = data.flags.find((flag) => flag.key === "autoplay-previews");
  const rolloutPercentage = autoplayFlag?.percentage ?? 50;
  const inside = autoplay.bucket < rolloutPercentage;
  els.autoplayNote.replaceChildren();
  els.autoplayNote.append(
    make(
      "span",
      "",
      autoplay.value
        ? "Autoplay is ON for this viewer. "
        : "Autoplay is OFF for this viewer. ",
    ),
  );
  els.autoplayNote.append(
    make(
      "strong",
      "",
      `${autoplay.reason} · bucket ${autoplay.bucket} is ${inside ? "inside" : "outside"} the ${rolloutPercentage}% rollout.`,
    ),
  );
  els.autoplayNote.append(
    make(
      "span",
      "",
      " The preview below is simulated; the flag decides whether it starts on its own.",
    ),
  );

  els.dialog.classList.remove("playing");
  els.detailPlay.setAttribute("aria-label", "Play simulated preview");
  els.previewLabel.textContent = autoplay.value
    ? "Autoplay preview · simulated"
    : "Preview off · press play";

  els.dialog.showModal();
  if (autoplay.value) {
    requestAnimationFrame(() => {
      els.dialog.classList.add("playing");
      els.previewLabel.textContent = "Playing preview · simulated";
      els.detailPlay.setAttribute("aria-label", "Pause simulated preview");
    });
  }
}

function togglePreview() {
  const playing = els.dialog.classList.toggle("playing");
  els.previewLabel.textContent = playing
    ? "Playing preview · simulated"
    : "Preview paused · press play";
  els.detailPlay.setAttribute(
    "aria-label",
    playing ? "Pause simulated preview" : "Play simulated preview",
  );
}

function closeDetail() {
  els.dialog.classList.remove("playing");
  els.dialog.close();
}

/* ---------------------------------------------------------------- events */

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  load();
});

els.country.addEventListener("change", () => {
  state.country = els.country.value;
  load();
});

els.genre.addEventListener("change", () => {
  state.genre = els.genre.value;
  load();
});

els.form.querySelectorAll('input[name="plan"]').forEach((input) => {
  input.addEventListener("change", () => {
    if (!input.checked) return;
    state.plan = input.value;
    load();
  });
});

let typingTimer;
els.userId.addEventListener("input", () => {
  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => {
    state.userId = els.userId.value.trim().slice(0, 80) || "viewer-1";
    load();
  }, 450);
});

els.shuffle.addEventListener("click", () => {
  state.userId = `viewer-${Math.random().toString(36).slice(2, 8)}`;
  els.userId.value = state.userId;
  load();
});

els.detailClose.addEventListener("click", closeDetail);
els.detailPlay.addEventListener("click", togglePreview);
els.dialog.addEventListener("click", (event) => {
  if (event.target === els.dialog) closeDetail();
});
els.dialog.addEventListener("close", () => {
  els.dialog.classList.remove("playing");
  state.lastFocus?.focus();
});

async function checkHealth() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    const health = await response.json();
    if (state.data?.snapshot.degraded) return;
    setStatus("ok", `Catalyst connected · ${health.sdk.flag_count} flags`);
  } catch {
    if (!state.data) setStatus("warn", "Waiting for the API");
  }
}

hydrateFromUrl();
load();
checkHealth();
