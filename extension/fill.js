// JobPilot autofill: fills the application form on the current page with the
// contact data and answer bank synced from JobPilot. Never submits: the last
// click is the person's, same rule as the rest of JobPilot.
//
// Injected by popup.js with chrome.scripting.executeScript. The matching
// functions are pure so fill.test.js can run them under plain node.

(() => {
  const norm = (s) =>
    (s || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();

  // Standard fields, checked in order (email before name, "last name" before
  // "name"). Only for short labels: "Are you authorized to work in this
  // country?" mentions a country but is a question for the answer bank.
  const STANDARD = [
    // Someone else's name/email/phone: left for the person.
    [null, /\b(company|empresa|employer|school|universi\w*|reference|referr\w*|referid\w*|emergency|hiring manager|if different|preferred|nickname|other)\b/],
    ["email", /\b(e ?mail|correo)\b/],
    ["first_name", /\b(first name|given name|primer nombre|first)\b|^nombre$/],
    ["last_name", /\b(last name|family name|surname|apellidos?|last)\b/],
    ["full_name", /\b(full name|nombre completo|your name|name|nombre)\b/],
    ["phone", /\b(phone|telefono|mobile|celular|movil|whatsapp)\b/],
    ["linkedin", /\blinkedin\b/],
    ["github", /\bgithub\b/],
    ["portfolio", /\b(portfolio|portafolio|website|sitio web|personal site|web site)\b/],
    ["location", /\b(location|ubicacion|where are you based|current location|address|direccion)\b/],
    ["city", /\b(city|ciudad)\b/],
    ["country", /\b(country|pais)\b/],
  ];
  const SHORT_LABEL = 60;

  // Shared concepts, so a Spanish question in the bank answers an English
  // form and the other way round.
  const CONCEPTS = [
    ["sponsor", /sponsor|visa|patrocinio/],
    ["workauth", /authori[sz]ed|eligible to work|legally|right to work|autorizaci|permiso de trabajo/],
    ["salary", /salary|compensation|salari|pay expectation|sueldo|remuneraci/],
    ["start", /notice period|start date|when can you start|availability to start|preaviso|disponibilidad|incorporar/],
    ["relocate", /relocat|reubica|mudarte|trasladarte/],
    ["years", /years of experience|anos de experiencia/],
    ["source", /hear about|how did you find|conociste|enteraste/],
    ["english", /english|ingles/],
    ["remote", /remote|remoto|home office/],
  ];

  const STOP = new Set(
    "a an and are as at be by de del do does el en es for from have how in is it la las los o of on or para por que se the to tu tus un una what when where which who will with you your".split(" "),
  );
  const tokens = (s) => new Set(norm(s).split(" ").filter((t) => t.length > 1 && !STOP.has(t)));
  const concepts = (s) => {
    const n = norm(s);
    return CONCEPTS.filter(([, re]) => re.test(n)).map(([c]) => c);
  };

  function standardKey(label) {
    const n = norm(label);
    if (!n) return null;
    // "Would you like to include your LinkedIn profile, personal website or blog?"
    if (n.length > SHORT_LABEL) return /\blinkedin\b.*\b(profile|url)\b|perfil de linkedin/.test(n) ? "linkedin" : null;
    const hit = STANDARD.find(([, re]) => re.test(n));
    return hit ? hit[0] : null;
  }

  function standardValue(key, data) {
    const parts = (data.full_name || "").trim().split(/\s+/);
    switch (key) {
      case "first_name":
        return parts[0] || "";
      case "last_name":
        return parts.slice(1).join(" ");
      case "location":
        return [data.city, data.country].filter(Boolean).join(", ");
      default:
        return data[key] || "";
    }
  }

  // Best answer-bank entry for a form question: a shared concept wins
  // outright; otherwise word overlap (Dice) of at least 0.5.
  // ponytail: keyword heuristic, swap for embeddings if it misses too often.
  function bestAnswer(label, answers) {
    const lc = concepts(label);
    const lt = tokens(label);
    let best = null;
    let bestScore = 0;
    for (const a of answers || []) {
      const shared = concepts(a.question).filter((c) => lc.includes(c)).length;
      const qt = tokens(a.question);
      const inter = [...qt].filter((t) => lt.has(t)).length;
      const dice = qt.size + lt.size ? (2 * inter) / (qt.size + lt.size) : 0;
      const score = shared ? 1 + shared : dice;
      if (score > bestScore) {
        best = a;
        bestScore = score;
      }
    }
    return bestScore >= 0.5 ? best : null;
  }

  // "Sí, ..." / "Yes" / "No" at the start of an answer, for yes/no selects
  // and radios.
  function yesNo(answer) {
    const n = norm(answer);
    if (/^(si|yes|y)\b/.test(n)) return "yes";
    if (/^no\b/.test(n)) return "no";
    return null;
  }

  // Profiles keep the country in Spanish; English forms list it in English.
  // ponytail: only the common ones, add a country when a form misses it.
  const COUNTRY_EN = {
    "republica dominicana": "dominican republic",
    "estados unidos": "united states",
    espana: "spain",
    brasil: "brazil",
    "reino unido": "united kingdom",
    alemania: "germany",
    francia: "france",
    "paises bajos": "netherlands",
    canada: "canada",
    mexico: "mexico",
  };

  function optionMatches(optionText, answer) {
    const o = norm(optionText);
    if (!o) return false;
    const yn = yesNo(answer);
    if (yn === "yes" && /^(yes|si)\b/.test(o)) return true;
    if (yn === "no" && /^no\b/.test(o)) return true;
    const na = norm(answer);
    // "Dominican Republic +1": the option may carry a suffix (dial code).
    return [na, COUNTRY_EN[na]].some(
      (a) => a && (a === o || a.startsWith(o + " ") || (a.length > 3 && o.startsWith(a + " "))),
    );
  }

  const api = { norm, standardKey, standardValue, bestAnswer, yesNo, optionMatches };
  if (typeof module !== "undefined") {
    module.exports = api;
    return;
  }

  // ------------------------------------------------------------- DOM side

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function labelOf(el) {
    const parts = new Set();
    // A <select> inside its <label> would drag every option into the text.
    const own = el.tagName === "SELECT" ? el.innerText : "";
    if (el.labels) for (const l of el.labels) parts.add(l.innerText.replace(own, "").trim());
    const by = el.getAttribute("aria-labelledby");
    if (by) for (const id of by.split(/\s+/)) parts.add((document.getElementById(id)?.innerText || "").trim());
    parts.add((el.getAttribute("aria-label") || "").trim());
    parts.delete("");
    let text = [...parts].join(" ");
    if (!text) {
      // Greenhouse/Lever/Ashby wrap each field with its label text in a block.
      const box = el.closest("fieldset, .field, .application-question, li, [class*='field'], [class*='question'], div");
      text = (box?.querySelector("legend, label, .application-label, [class*='label']")?.innerText || "").replace(own, "").trim();
    }
    return text || el.getAttribute("placeholder") || el.getAttribute("name") || "";
  }

  function visible(el) {
    return !el.disabled && !el.readOnly && el.offsetParent !== null;
  }

  const required = (el, label) =>
    el.required || el.getAttribute("aria-required") === "true" || /[*✱]\s*$|[*✱]\s/.test(label);

  // React/Vue keep their own copy of the value: set it through the native
  // setter and fire the events they listen for, or the form "forgets" it.
  function setValue(el, value, mark = true) {
    const proto = Object.getPrototypeOf(el);
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    if (mark) el.style.outline = "2px solid #22c55e";
  }

  function valueFor(label, data) {
    const key = standardKey(label);
    if (key) return standardValue(key, data);
    return bestAnswer(label, data.answers)?.answer || "";
  }

  // React-Select (Greenhouse's new boards) only opens its menu on a real
  // click, so go through the component itself: its option list and its own
  // selectOption, which runs the form's onChange like a click would.
  // ponytail: relies on React internals (__reactFiber), the typing fallback
  // below covers anything else; async lists (city search) are left to you.
  function reactSelectOf(el) {
    const fk = Object.keys(el).find((k) => k.startsWith("__reactFiber"));
    for (let f = fk && el[fk], i = 0; f && i < 60; f = f.return, i++) {
      if (f.stateNode?.selectOption && Array.isArray(f.stateNode.props?.options)) return f.stateNode;
    }
    return null;
  }

  // Searchable dropdowns: through React-Select when it is one; otherwise type,
  // wait for the list, click the matching option. No match -> clear it.
  async function pickCombobox(el, value) {
    const rs = reactSelectOf(el);
    if (rs) {
      const label = rs.props.getOptionLabel || ((o) => o.label);
      const opt = rs.props.options.flatMap((o) => o.options || [o]).find((o) => optionMatches(label(o), value));
      if (!opt) return false;
      rs.selectOption(opt);
      el.closest("[class*='control']")?.style.setProperty("outline", "2px solid #22c55e");
      return true;
    }
    const yn = yesNo(value);
    const queries = yn ? (yn === "yes" ? ["Yes", "Sí"] : ["No"]) : [value];
    for (const q of queries) {
      el.focus();
      setValue(el, q, false);
      await sleep(400);
      const listId = el.getAttribute("aria-controls") || el.getAttribute("aria-owns");
      const scope = (listId && document.getElementById(listId)) || document;
      const opt = [...scope.querySelectorAll("[role=option]")].find((o) => optionMatches(o.innerText, yn ? q : value));
      if (opt) {
        opt.click();
        el.closest("[class*='container'], [class*='select']")?.style.setProperty("outline", "2px solid #22c55e");
        return true;
      }
    }
    setValue(el, "", false);
    el.blur();
    return false;
  }

  const hasSelection = (el) =>
    !!el.closest("[class*='control'], [class*='container']")?.querySelector("[class*='single-value'], [class*='singleValue']");

  window.__jobpilotFill = async (data) => {
    let filled = 0;
    const missing = [];
    const SKIP = new Set(["hidden", "file", "submit", "button", "checkbox", "radio", "password", "image", "reset"]);

    for (const el of document.querySelectorAll("input, textarea, select")) {
      if (!visible(el) || SKIP.has(el.type)) continue;
      const label = labelOf(el);
      const value = valueFor(label, data);

      if (el.tagName === "SELECT") {
        if (el.selectedIndex > 0) continue;
        // "What is your location?" as a list of countries: try the country too.
        const opt = [...el.options].find((o) => [value, data.country].some((v) => v && optionMatches(o.text, v)));
        if (opt) {
          setValue(el, opt.value);
          filled++;
        } else if (required(el, label)) missing.push(label);
        continue;
      }

      if (el.getAttribute("role") === "combobox") {
        if (hasSelection(el)) continue;
        if (value && (await pickCombobox(el, value))) filled++;
        else if (required(el, label)) missing.push(label);
        continue;
      }

      if (el.value) continue;
      if (value) {
        setValue(el, value);
        filled++;
      } else if (label && required(el, label)) {
        missing.push(label);
      }
    }

    // Yes/no radio groups.
    const groups = new Map();
    for (const r of document.querySelectorAll("input[type=radio]")) {
      if (visible(r) && r.name && !groups.has(r.name)) groups.set(r.name, r);
    }
    for (const [name, first] of groups) {
      const radios = [...document.querySelectorAll(`input[type=radio][name="${CSS.escape(name)}"]`)];
      if (radios.some((r) => r.checked)) continue;
      // The question is above the whole group, not inside an option's <li>.
      let box = first;
      while (box && !radios.every((r) => box.contains(r))) box = box.parentElement;
      box = box?.closest("fieldset, [role=radiogroup], .application-question, [class*='question']") || box?.parentElement;
      const heading = [...(box?.querySelectorAll("legend, [class*='label'], label") || [])].find((n) => !n.querySelector("input"));
      const label = (heading?.innerText || "").trim();
      const answer = bestAnswer(label, data.answers)?.answer;
      const pick = answer && radios.find((r) => optionMatches(labelOf(r) || r.value, answer));
      if (pick) {
        pick.click();
        filled++;
      } else if (label) missing.push(label);
    }

    return { filled, missing: [...new Set(missing)].slice(0, 15) };
  };
})();
