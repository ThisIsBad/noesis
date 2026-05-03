// Per-service /health probe strip.
//
// Every 10 s, GET <SERVICE>/health for each service we know about. /health
// is auth-skipped on every Noesis service so we don't need a token here.
//
// Service URLs come from a small map below. In the docker-compose dev-stack
// the compose file binds each service to a fixed host port; on Railway you
// can edit this map or set window.NOESIS_HEALTH_URLS = {svc: url, …} from
// a custom build for your deploy.

const DEFAULT_URLS = {
  hegemonikon:  window.location.origin,        // self
  logos:    "http://localhost:8001",
  mneme:    "http://localhost:8002",
  praxis:   "http://localhost:8003",
  telos:    "http://localhost:8004",
  episteme: "http://localhost:8005",
  kosmos:   "http://localhost:8006",
  empiria:  "http://localhost:8007",
  techne:   "http://localhost:8008",
  kairos:   "http://localhost:8009",
};

const URLS = Object.assign({}, DEFAULT_URLS, window.NOESIS_HEALTH_URLS || {});

const strip = document.getElementById("health-strip");
const pills = {};

for (const [name, url] of Object.entries(URLS)) {
  const pill = document.createElement("span");
  pill.className = "health-pill";
  pill.textContent = name;
  pill.title = url;
  strip.appendChild(pill);
  pills[name] = { el: pill, url };
}

async function probe() {
  await Promise.all(
    Object.entries(pills).map(async ([name, info]) => {
      try {
        const r = await fetch(info.url + "/health", { mode: "cors" });
        info.el.classList.toggle("ok", r.ok);
        info.el.classList.toggle("bad", !r.ok);
      } catch (_) {
        // CORS-blocked or unreachable. The visual signal is the same — bad.
        info.el.classList.remove("ok");
        info.el.classList.add("bad");
      }
    })
  );
}

probe();
setInterval(probe, 10_000);
