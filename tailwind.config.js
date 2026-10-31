/** @type {import('tailwindcss').Config} */
// Tailwind 3.4 (même famille que l'ancien script cdn.tailwindcss.com) : le CSS est compilé
// dans static/css/output.css par `npm run build`, à relancer après tout ajout de classe.
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    "./apps/**/*.py",          // classes éventuellement construites dans les vues
    "./static/pwa/**/*.js",    // classes ajoutées par le JavaScript de la PWA
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
