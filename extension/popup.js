const $ = (id) => document.getElementById(id);

chrome.storage.local.get("autofill", ({ autofill }) => {
  if (!autofill) {
    $("status").textContent = "Abre una vacante en JobPilot (el Kit de aplicación) para sincronizar tus datos.";
    return;
  }
  const when = new Date(autofill.synced_at).toLocaleString();
  $("status").textContent = `${autofill.answers.length} respuestas, sincronizado ${when}.`;
  $("fill").disabled = false;
  $("fill").onclick = () => fill(autofill);
});

async function fill(data) {
  $("fill").disabled = true;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const target = { tabId: tab.id, allFrames: true };
  try {
    await chrome.scripting.executeScript({ target, files: ["fill.js"] });
    const runs = await chrome.scripting.executeScript({
      target,
      func: (d) => window.__jobpilotFill?.(d),
      args: [data],
    });
    const results = runs.map((r) => r.result).filter(Boolean);
    const filled = results.reduce((n, r) => n + r.filled, 0);
    const missing = [...new Set(results.flatMap((r) => r.missing))];
    $("result").textContent = filled
      ? `Rellené ${filled} campo(s), marcados en verde. Revísalos y envía tú.`
      : "No encontré campos que pueda rellenar aquí.";
    if (missing.length) {
      $("result").textContent += " Sin respuesta en tu banco (añádelas en el Kit de JobPilot):";
      $("missing").replaceChildren(...missing.map((m) => Object.assign(document.createElement("li"), { textContent: m })));
    }
  } catch (e) {
    $("result").textContent = `No se pudo rellenar esta página: ${e.message}`;
  } finally {
    $("fill").disabled = false;
  }
}
