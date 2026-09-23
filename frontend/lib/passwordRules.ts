/** The same four rules the backend enforces in `_NewPassword`
 * (`backend/app/schemas/user.py`). Kept as data so the form can show them
 * as a live checklist instead of only failing after a submit — the old
 * flow surfaced them as one red sentence *after* the user had already
 * picked a password, which is the worst possible moment to learn them. */
export const PASSWORD_RULES: { label: string; test: (v: string) => boolean }[] = [
  { label: "8+ caracteres", test: (v) => v.length >= 8 },
  { label: "Una mayúscula", test: (v) => /[A-Z]/.test(v) },
  { label: "Un número", test: (v) => /\d/.test(v) },
  { label: "Un carácter especial", test: (v) => /[^A-Za-z0-9]/.test(v) },
];
