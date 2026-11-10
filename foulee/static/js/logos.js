// Logos au choix de l'application (Réglages → Profil). Dessins originaux, carrés de 32 × 32 :
// fond écorce, motif blanc et rouge, comme la balise des sentiers qui sert d'identité à Foulée.
const BG = '<rect width="32" height="32" rx="7" fill="#4b3e34"/>';

export const LOGOS = {
  foulee: { label: "Foulée (balise)", svg: `${BG}<rect x="6" y="8" width="20" height="6" rx="1.5" fill="#fff"/><rect x="6" y="18" width="20" height="6" rx="1.5" fill="#d3263a"/>` },
  chaussure: { label: "Chaussure", svg: `${BG}<path d="M5 20.5c0-2 1-6.5 2.4-8.6.4-.6 1.2-.5 1.5.1.9 1.8 2.6 2.8 4.6 2.8.9 0 1.4.6 1.9 1.3 1.1 1.5 3.5 2 7 2.4 1.8.2 2.6 1.4 2.6 2.6v.4c0 .8-.6 1.4-1.4 1.4H6.4c-.8 0-1.4-.6-1.4-1.4z" fill="#fff"/><path d="M5 22.2h22" stroke="#d3263a" stroke-width="2.2" stroke-linecap="round"/><path d="M12.2 14.3l1.2-1.6M14.8 15.4l1.2-1.6" stroke="#4b3e34" stroke-width="1.3" stroke-linecap="round"/>` },
  chrono: { label: "Chrono", svg: `${BG}<circle cx="16" cy="18" r="8.5" fill="#fff"/><rect x="13.5" y="5.5" width="5" height="3" rx="1" fill="#fff"/><path d="M16 18V12.5" stroke="#d3263a" stroke-width="2.2" stroke-linecap="round"/><path d="m23.4 10.6 1.6-1.6" stroke="#fff" stroke-width="2" stroke-linecap="round"/>` },
  montagne: { label: "Montagne", svg: `${BG}<path d="M3.5 25 12 11l4.2 6.8L19.5 13 28.5 25z" fill="#fff"/><path d="m12 11-2.7 4.4 1.6-.7 1.1 1 1.2-1.1 1.4.6z" fill="#d3263a"/><path d="m19.5 13-2.1 3.4 1.2-.4.9.8 1-.9 1 .5z" fill="#d3263a"/>` },
  coeur: { label: "Cœur", svg: `${BG}<path d="M16 26s-9.5-5.6-9.5-12.3A5 5 0 0 1 16 10.9a5 5 0 0 1 9.5 2.8C25.5 20.4 16 26 16 26z" fill="#fff"/><path d="M8 17.5h4.2l1.6-3.4 2.6 6.4 2-4.2h5.6" fill="none" stroke="#d3263a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>` },
  eclair: { label: "Éclair", svg: `${BG}<path d="M18.5 4 8 18h6.6L12.5 28 24 13.5h-6.8z" fill="#fff"/><path d="M18.5 4 16 13.5h1.2z" fill="#d3263a"/>` },
  piste: { label: "Piste", svg: `${BG}<rect x="4.5" y="8.5" width="23" height="15" rx="7.5" fill="none" stroke="#d3263a" stroke-width="3"/><rect x="8.5" y="12.5" width="15" height="7" rx="3.5" fill="none" stroke="#fff" stroke-width="2"/><path d="M16 8.5v4" stroke="#fff" stroke-width="2"/>` },
};

export function logoSVG(name, size = 28) {
  const logo = LOGOS[name] || LOGOS.foulee;
  return `<svg class="logo" viewBox="0 0 32 32" width="${size}" height="${size}" aria-hidden="true">${logo.svg}</svg>`;
}

/** Logo de l'en-tête : un dessin, ou la photo de profil si elle est choisie (et présente). */
export function brandMark(profil, size = 28) {
  if (profil?.logo === "photo" && profil.photo) {
    return `<img class="logo logo-photo" src="/api/profil/photo?v=${profil.photo_maj || 0}" width="${size}" height="${size}" alt="">`;
  }
  return logoSVG(profil?.logo, size);
}

/** Icône de l'onglet du navigateur, assortie au logo choisi. */
export function setFavicon(profil) {
  let link = document.querySelector('link[rel="icon"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  if (profil?.logo === "photo" && profil.photo) {
    link.href = `/api/profil/photo?v=${profil.photo_maj || 0}`;
    return;
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">${(LOGOS[profil?.logo] || LOGOS.foulee).svg}</svg>`;
  link.href = `data:image/svg+xml,${encodeURIComponent(svg)}`;
}
