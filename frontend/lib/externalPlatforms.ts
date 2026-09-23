/**
 * Plataformas de trabajo remoto sin fuente de datos integrable (sin RSS/API
 * pública de autoservicio) — investigadas 2026-09 como buenas opciones para
 * alguien buscando trabajo remoto desde República Dominicana. A diferencia
 * de los proveedores en ExternalProvider (types.ts), estas no se pueden
 * buscar en vivo desde JobPilot: son modelos de "aplica con tu perfil"
 * (agencias de staffing/freelance) o simplemente no exponen una API pública.
 * Se muestran como accesos directos en Discover — ver
 * docs/PUBLIC_APIS_RESEARCH.md § 12 para el detalle de por qué cada una
 * quedó fuera de la búsqueda automática.
 */

export interface ExternalPlatform {
  name: string;
  url: string;
  note: string;
}

export interface ExternalPlatformGroup {
  label: string;
  platforms: ExternalPlatform[];
}

export const EXTERNAL_PLATFORM_GROUPS: ExternalPlatformGroup[] = [
  {
    label: "Freelance / proyectos",
    platforms: [
      { name: "Workana", url: "https://www.workana.com/es/jobs?country=DO", note: "Proyectos filtrables por RD — diseño, dev, redacción, soporte" },
      { name: "Upwork", url: "https://www.upwork.com/", note: "Sin restricción de país para aplicar — usa Payoneer para cobrar" },
      { name: "Fiverr", url: "https://www.fiverr.com/", note: "Marketplace de gigs, registro abierto" },
      { name: "Contra", url: "https://contra.com/", note: "Sin comisión, alcance mundial, volumen aún bajo" },
    ],
  },
  {
    label: "Redes nearshore para desarrolladores",
    platforms: [
      { name: "Toptal", url: "https://www.toptal.com/", note: "Filtra ~top 3%, aplica con perfil" },
      { name: "BairesDev", url: "https://www.bairesdev.com/join-us/", note: "Staffing agency, opera en 50+ países" },
      { name: "Turing", url: "https://www.turing.com/", note: "Aplica con perfil, pruebas técnicas" },
      { name: "Crossover", url: "https://www.crossover.com/", note: "Aplica con perfil" },
      { name: "Revelo", url: "https://www.revelo.com/", note: "Confirma nómina en 18 países LatAm incl. RD" },
      { name: "TECLA", url: "https://www.tecla.io/", note: "Aplica con perfil" },
      { name: "Near", url: "https://www.near.io/", note: "Aplica con perfil" },
      { name: "Arc.dev", url: "https://arc.dev/", note: "Marketplace global, perfil de developer gratis" },
      { name: "Lemon.io", url: "https://lemon.io/for-developers/", note: "Pool de talento; ~1-2% de aceptación" },
      { name: "Talently", url: "https://talently.tech/", note: "LatAm, aplica con perfil" },
    ],
  },
  {
    label: "Redes / networking LatAm",
    platforms: [
      { name: "Wellfound (ex-AngelList)", url: "https://wellfound.com/location/latin-america-8", note: "Filtro \"Latin America\" — revisa zona horaria por oferta" },
      { name: "Torre.ai", url: "https://torre.ai/", note: "Más red de networking que bolsa masiva" },
      { name: "WeRemoto", url: "https://weremoto.com/", note: "Remoto para LatAm" },
    ],
  },
  {
    label: "Bolsas tech sin API pública",
    platforms: [
      { name: "Work at a Startup (YC)", url: "https://www.workatastartup.com/", note: "Startups de Y Combinator, salarios visibles" },
      { name: "Levels.fyi Jobs", url: "https://www.levels.fyi/jobs", note: "Compensación estimada en cada oferta" },
      { name: "Built In", url: "https://builtin.com/jobs/remote", note: "Enfocada en EE.UU." },
      { name: "Dice", url: "https://www.dice.com/jobs", note: "Tech en EE.UU." },
      { name: "Welcome to the Jungle", url: "https://www.welcometothejungle.com/en/jobs", note: "Fichas de empresa detalladas" },
      { name: "Glassdoor", url: "https://www.glassdoor.com/Job/index.htm", note: "Útil para ver reseñas y salarios" },
      { name: "Indeed", url: "https://www.indeed.com/", note: "De todo, mucho ruido" },
      { name: "FlexJobs", url: "https://www.flexjobs.com/", note: "De pago, filtra estafas" },
      { name: "Teamblind", url: "https://www.teamblind.com/jobs", note: "Comunidad anónima de empleados tech" },
    ],
  },
  {
    label: "República Dominicana (local)",
    platforms: [
      { name: "Computrabajo RD", url: "https://do.computrabajo.com/empleos-en-remoto", note: "El portal local con más volumen de vacantes \"remoto\"" },
      { name: "LinkedIn (RD + Remote)", url: "https://www.linkedin.com/jobs/search/?location=Dominican%20Republic&f_WT=2", note: "Activa alertas de empleo con este filtro" },
      { name: "SuperEmpleo.com.do", url: "https://www.superempleo.com.do/", note: "Volumen bajo de remoto internacional" },
      { name: "Tecoloco RD", url: "https://www.tecoloco.com.do/", note: "Volumen bajo de remoto internacional" },
      { name: "OpcionEmpleo RD", url: "https://www.opcionempleo.com.do/", note: "Volumen bajo de remoto internacional" },
      { name: "Empléate (RD Trabaja)", url: "https://rdtrabaja.mt.gob.do/", note: "Portal del gobierno, casi todo presencial" },
    ],
  },
  {
    label: "Para negociar flexibilidad una vez hay entrevista",
    platforms: [
      { name: "Deel", url: "https://www.deel.com/", note: "Employer of Record — menciónalo si preguntan cómo te pueden pagar en RD" },
    ],
  },
];
