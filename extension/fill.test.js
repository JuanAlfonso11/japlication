// Run: node extension/fill.test.js
const assert = require("node:assert");
const f = require("./fill.js");

const data = { full_name: "Ana María Pérez", email: "a@b.co", city: "Santo Domingo", country: "República Dominicana" };
const answers = [
  { question: "¿Requieres patrocinio de visa ahora o en el futuro?", answer: "No" },
  { question: "¿Cuál es tu expectativa salarial?", answer: "USD 3,000 al mes" },
  { question: "¿Tienes autorización para trabajar en el país de la vacante?", answer: "Sí, como contratista remoto" },
  { question: "Why do you want to work at Acme?", answer: "Because..." },
];

assert.equal(f.standardKey("Email*"), "email");
assert.equal(f.standardKey("First Name"), "first_name");
assert.equal(f.standardKey("Last name"), "last_name");
assert.equal(f.standardKey("Full name"), "full_name");
assert.equal(f.standardKey("LinkedIn Profile"), "linkedin");
assert.equal(f.standardKey("Current location"), "location");
assert.equal(f.standardKey("Current company name"), null);
assert.equal(f.standardKey("Other website"), null);
assert.equal(f.standardKey("Portfolio URL"), "portfolio");
assert.equal(f.standardKey("Legal Name (if different than above)"), null);
assert.equal(f.standardKey("Would you like to include your LinkedIn profile, personal website or blog?"), "linkedin");
assert.equal(f.standardKey("Referrer email"), null);
assert.equal(f.standardKey("Are you legally authorized to work in the country where this job is located?"), null);

assert.equal(f.standardValue("first_name", data), "Ana");
assert.equal(f.standardValue("last_name", data), "María Pérez");
assert.equal(f.standardValue("location", data), "Santo Domingo, República Dominicana");

assert.equal(f.bestAnswer("Will you now or in the future require visa sponsorship?", answers).answer, "No");
assert.equal(f.bestAnswer("What are your salary expectations?", answers).answer, "USD 3,000 al mes");
assert.equal(f.bestAnswer("Are you legally authorized to work in the US?", answers).answer, "Sí, como contratista remoto");
assert.equal(f.bestAnswer("Why do you want to work at Acme Corp?", answers).answer, "Because...");
assert.equal(f.bestAnswer("Favourite programming language?", answers), null);

assert.ok(f.optionMatches("Yes", "Sí, como contratista remoto"));
assert.ok(!f.optionMatches("No", "Sí, como contratista remoto"));
assert.ok(f.optionMatches("No", "No"));
assert.ok(f.optionMatches("Dominican Republic +1", "República Dominicana"));
assert.ok(f.optionMatches("Dominican Republic +1", "Dominican Republic"));
assert.ok(!f.optionMatches("Dominica +1", "República Dominicana"));
assert.ok(!f.optionMatches("Dominica", "República Dominicana"));
assert.ok(f.optionMatches("Dominican Republic", "República Dominicana"));

console.log("fill.js: ok");
