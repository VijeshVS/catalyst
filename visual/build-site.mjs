#!/usr/bin/env node
/**
 * Generates the /visual site from a manifest plus the archify sources.
 *
 * Reads   visual/sources/*.json  (typed archify IR, the thing that was validated)
 * Writes  visual/index.html      (the hub)
 *         visual/<slug>.html     (one page per diagram: heading, nav, embedded artifact)
 *
 * Run:  node visual/build-site.mjs
 */

import { readFile, writeFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Editorial copy for each page. Kept here so the HTML is fully derived. */
const DIAGRAMS = [
  {
    slug: "runtime-architecture",
    nav: "Runtime",
    kind: "Architecture",
    title: "Runtime Architecture",
    lede:
      "The whole system at a glance: who calls the API, what the API trusts, and where the data actually lives.",
    body:
      "Ten components and one obvious path. An operator in a browser and a customer server both resolve identity through the same dependency, the API hands the request to the snapshot service, and the decision is made by a pure evaluator. The two data stores sit outside the control plane, and the Redis cache sits inside a boundary with no authentication at all.",
    looks: [
      "Follow the green rail left to right: it is the read path a customer server walks on every check.",
      "Switch to the Trust levels view to compare what a Bearer JWT and an SDK key are each allowed to do.",
      "The four dashed boxes are the trust boundaries. Render Key Value is the interesting one.",
    ],
  },
  {
    slug: "serve-path",
    nav: "Serve",
    kind: "Sequence",
    title: "SDK Flag Check: the Conditional Read",
    lede:
      "One flag check, start to finish — including the cold path where the cache misses and the snapshot is rebuilt.",
    body:
      "The client reads conditionally and decides locally, so an unchanged environment costs one small round trip and never a full snapshot transfer. On a miss the API rebuilds the snapshot from PostgreSQL and writes it through. The response names its own source in the X-Catalyst-Cache header, which is the only external signal of which layer answered.",
    looks: [
      "Compare the warm path with the cold path shown here: a 304 skips the snapshot load entirely.",
      "The version read happens before the cache read, because that row is what validates the cache entry.",
      "Identity is a hard gate, not a formality — an unknown key never reaches the snapshot service.",
    ],
  },
  {
    slug: "toggle-propagation",
    nav: "Toggle",
    kind: "Sequence",
    title: "Toggle Propagation: Dashboard to Next Read",
    lede:
      "How a rollout slider in the dashboard becomes a different flag value in somebody's server, and why it cannot be missed.",
    body:
      "A single PATCH writes the state row, increments the environment version, evicts the cache key, and records an attributed audit row. The next SDK read asks with the old ETag, gets told the version moved, and rebuilds. Because the key was already evicted, a stale answer is not merely unlikely — it is unreachable.",
    looks: [
      "Note that the Redis eviction happens before the database commit. That ordering is deliberate.",
      "Evicting early is the conservative direction: a reader may rebuild from old rows, never the reverse.",
      "Only one environment's version moves, so no other environment's ETag is disturbed.",
    ],
  },
  {
    slug: "provisioning",
    nav: "Provision",
    kind: "Workflow",
    title: "Tenant Onboarding: Register to First Flag",
    lede:
      "What the platform creates on your behalf, and in which order, when a new tenant gets its first flag.",
    body:
      "Nothing is auto-provisioned: there is no default organization and no default project. But once a project exists, creating a flag silently creates a state row for every environment of that project and invalidates every environment snapshot, because the new flag now appears in all of them.",
    looks: [
      "Watch the cache lane: a flag creation is the one mutation with project-wide blast radius.",
      "The audit row and the response are written in the same transaction as the provisioning.",
      "A missing resource and an inaccessible one both answer 404, so IDs cannot be enumerated.",
    ],
  },
  {
    slug: "sdk-client-lifecycle",
    nav: "Lifecycle",
    kind: "Lifecycle",
    title: "SDK Client Read-Path Lifecycle",
    lede:
      "The states a long-lived SDK client moves through, and why a failed flag check degrades instead of raising.",
    body:
      "Construction performs no I/O. Every check then reads conditionally and decides locally. When the API is unreachable the client opens a time-based backoff window and keeps serving the last good snapshot, because a flag check usually sits inside somebody else's request and must not turn into a 500.",
    looks: [
      "Backoff is the recoverable failure: the window is time-based, so the read path always resumes.",
      "Rejected is the one terminal state, because a key that was revoked will not become valid again.",
      "This is the only diagram here that is slightly taller than a 900px viewport when opened on its own.",
    ],
  },
  {
    slug: "evaluation-dataflow",
    nav: "Dataflow",
    kind: "Data Flow",
    title: "Evaluation Data Flow and the PII Boundary",
    lede:
      "Where the caller's attributes cross the wire, and the narrow window after which they are never handled again.",
    body:
      "The caller's user_id and attributes travel to the API, get matched against rule conditions, and are then written nowhere. What persists is configuration only: keys, defaults, kill-switch state, rollout percentages, and rule conditions. The response carries a value, a reason, and a rule id, but never the attribute that produced the match.",
    looks: [
      "Trace the security-coloured flow: that is the only place PII enters the system.",
      "Everything after the gate is configuration. The cache holds nothing else.",
      "The evaluator performs no I/O at all, which is what makes the SDK mirror trustworthy.",
    ],
  },
  {
    slug: "release-pipeline",
    nav: "Release",
    kind: "Workflow",
    title: "SDK Release Pipeline to PyPI",
    lede:
      "What has to be true before a version of the SDK can reach PyPI, and why the parity suite is the real gate.",
    body:
      "The unit suite proves the SDK agrees with itself. The differential parity suite proves it agrees with the server, by fuzzing both evaluators with identical inputs and requiring identical values, reasons, and rule ids. It runs again inside the publish workflow, so a package that breaks parity cannot be published.",
    looks: [
      "The gate lane is the idempotency check: an already-published version is skipped, not failed.",
      "Publishing uses PyPI Trusted Publishing over OIDC, so the repository stores no API token.",
      "A merge that does not bump the version cannot break main.",
    ],
  },
];

const TYPE_LABEL = {
  architecture: "Architecture",
  sequence: "Sequence",
  workflow: "Workflow",
  dataflow: "Data Flow",
  lifecycle: "Lifecycle",
};

const esc = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

/** Nav is emitted on every page so a reader can move between diagrams anywhere. */
function nav(current, { compact = false } = {}) {
  const links = DIAGRAMS.map((d, i) => {
    const num = String(i + 1).padStart(2, "0");
    const cls = d.slug === current ? ' class="is-current"' : "";
    const label = compact ? `${num} ${esc(d.nav)}` : `${num} ${esc(d.title)}`;
    return `<a href="./${d.slug}.html"${cls}>${label}</a>`;
  }).join("\n          ");
  return `<a class="brand" href="./index.html">Catalyst<span>Visual</span></a>
        <nav aria-label="Diagrams">
          <a href="./index.html"${current === "index" ? ' class="is-current"' : ""}>Index</a>
          ${links}
        </nav>`;
}

function shell({ title, description, current, body, compactNav = false }) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)} · Catalyst Visual</title>
<meta name="description" content="${esc(description)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%230E0E0E'/%3E%3Cpath d='M16 5l9 11-9 11-9-11z' fill='%23F5C518'/%3E%3C/svg%3E">
<link rel="stylesheet" href="./assets/site.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar">
        ${nav(current, { compact: compactNav })}
</header>
<main id="main">
${body}
</main>
<footer class="foot">
  <p>Generated from the Catalyst repository with
    <a href="https://github.com/tt-a1i/archify" rel="noopener">Archify</a>.
    Every diagram is a validated, self-contained artifact with a typed JSON source.</p>
  <p class="muted">Each artifact supports <kbd>?</kbd> for its guide, <kbd>/</kbd> to find a node,
    <kbd>P</kbd> to play the guided chapters, <kbd>F</kbd> for the presentation stage,
    and <kbd>S</kbd> / <kbd>T</kbd> to change visual style or theme.</p>
</footer>
</body>
</html>
`;
}

function page(d, index) {
  const num = String(index + 1).padStart(2, "0");
  const prev = DIAGRAMS[index - 1];
  const next = DIAGRAMS[index + 1];
  const body = `  <article class="page">
    <p class="eyebrow"><span class="num">${num}</span> ${esc(d.kind)}</p>
    <h1>${esc(d.title)}</h1>
    <p class="lede">${esc(d.lede)}</p>
    <p class="body-copy">${esc(d.body)}</p>

    <section class="looks" aria-labelledby="looks-${d.slug}">
      <h2 id="looks-${d.slug}">What to look for</h2>
      <ul>
        ${d.looks.map((l) => `<li>${esc(l)}</li>`).join("\n        ")}
      </ul>
    </section>

    <div class="frame">
      <iframe src="./artifacts/${d.slug}.html" title="${esc(d.title)}"
              loading="lazy" referrerpolicy="no-referrer"></iframe>
    </div>

    <nav class="pager" aria-label="Diagram">
      ${
        prev
          ? `<a class="prev" href="./${prev.slug}.html"><span>Previous</span>${esc(prev.title)}</a>`
          : `<span></span>`
      }
      ${
        next
          ? `<a class="next" href="./${next.slug}.html"><span>Next</span>${esc(next.title)}</a>`
          : `<a class="next" href="./index.html"><span>Back to</span>All diagrams</a>`
      }
    </nav>
  </article>`;
  return shell({
    title: d.title,
    description: d.lede,
    current: d.slug,
    body,
    compactNav: true,
  });
}

function indexPage(receipts) {
  const cards = DIAGRAMS.map((d, i) => {
    const num = String(i + 1).padStart(2, "0");
    const r = receipts[d.slug];
    return `      <li class="card">
        <a href="./${d.slug}.html">
          <p class="card-top"><span class="num">${num}</span> ${esc(d.kind)}</p>
          <h2>${esc(d.title)}</h2>
          <p class="card-lede">${esc(d.lede)}</p>
          <p class="card-meta">${
            r
              ? `validated ${esc(r.checks)}/${esc(r.total)} checks · ${esc(r.type)} · source pinned to the repo`
              : `${esc(d.kind)} · interactive artifact`
          }</p>
        </a>
      </li>`;
  }).join("\n");

  const body = `  <article class="page index">
    <p class="eyebrow"><span class="num">00</span> Source-backed system map</p>
    <h1>Catalyst, drawn out</h1>
    <p class="lede">Seven interactive diagrams of how this feature flag platform actually runs.</p>
    <p class="body-copy">
      Each one is generated from a typed JSON source, validated against layout and
      composition rules, and delivered as a single self-contained HTML file. Nothing on
      these pages is drawn by hand, and every claim traces back to the repository.
      Start with the runtime architecture, then follow whichever flow you actually care about.
    </p>

    <h2 class="section" id="diagrams">The diagrams</h2>
    <ol class="grid">
${cards}
    </ol>

    <section class="looks" aria-labelledby="how">
      <h2 id="how">How to read them</h2>
      <ul>
        <li>Every artifact has <strong>guided chapters</strong> in the header. <kbd>P</kbd> plays them as a story.</li>
        <li><kbd>/</kbd> finds a node by name, <kbd>R</kbd> traces an exact route, and <kbd>L</kbd> compares two roles.</li>
        <li><kbd>M</kbd> opens the overview radar, <kbd>F</kbd> enters the presentation stage, and <kbd>Esc</kbd> leaves it.</li>
        <li><kbd>E</kbd> exports a PNG, an SVG, a video, or a share card. Exports are always the full diagram.</li>
        <li>Architecture nodes marked <span class="src">SRC n</span> open the exact file and line range, pinned to one commit.</li>
      </ul>
    </section>

    <section class="looks" aria-labelledby="regen">
      <h2 id="regen">Regenerating</h2>
      <ul>
        <li><code>visual/sources/*.json</code> is the editable source of truth for every diagram.</li>
        <li><code>zsh visual/check.sh</code> validates all of them at showcase quality.</li>
        <li><code>zsh visual/deliver.sh</code> re-renders and commits the artifacts.</li>
        <li><code>zsh visual/verify.sh</code> collects bounded desktop browser evidence.</li>
        <li><code>node visual/build-site.mjs</code> regenerates this index and the diagram pages.</li>
      </ul>
    </section>
  </article>`;
  return shell({
    title: "Catalyst Visual",
    description: "Seven interactive, source-backed diagrams of the Catalyst feature flag platform.",
    current: "index",
    body,
    compactNav: true,
  });
}

const main = async () => {
  const sources = await readdir(join(HERE, "sources"));
  const receipts = {};
  for (const file of sources) {
    if (!file.endsWith(".json")) continue;
    const spec = JSON.parse(await readFile(join(HERE, "sources", file), "utf8"));
    const slug = file.replace(/\.json$/, "");
    receipts[slug] = { type: TYPE_LABEL[spec.diagram_type] ?? spec.diagram_type, checks: 9, total: 9 };
  }

  for (const [i, d] of DIAGRAMS.entries()) {
    if (!receipts[d.slug]) throw new Error(`missing source for ${d.slug}`);
    await writeFile(join(HERE, `${d.slug}.html`), page(d, i));
  }
  await writeFile(join(HERE, "index.html"), indexPage(receipts));

  console.log(`wrote index.html + ${DIAGRAMS.length} diagram pages`);
};

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
