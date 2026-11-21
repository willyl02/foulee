#!/bin/sh
# Foulée : rappel des commandes du relais à la connexion SSH.
# Modèle copié par configurer-relais.sh (à l'installation et à chaque mise à jour) dans /etc/update-motd.d/90-foulee,
# après avoir remplacé @ROOT@ (dossier de Foulée) et @ENV@ (sa configuration). FOULEE_MOTD=0 dans la
# configuration pour s'en passer.
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "@ROOT@/foulee/__init__.py" 2>/dev/null)
CANAL=$(sed -n 's/^FOULEE_CANAL=//p' "@ENV@" 2>/dev/null)
B=$(printf '\033[1m'); D=$(printf '\033[2m'); R=$(printf '\033[0m'); G=$(printf '\033[32m'); X=$(printf '\033[31m')
state() {
    if systemctl is-active --quiet "$1" 2>/dev/null; then printf '%sactif%s' "$G" "$R"; else printf '%sarrêté%s' "$X" "$R"; fi
}

printf '\n%sFoulée · relais du club%s   version %s (canal %s)\n' "$B" "$R" "${VERSION:-?}" "${CANAL:-stable}"
printf '  relais : %s · tunnel Cloudflare : %s · mise à jour automatique chaque nuit vers 4 h 30\n\n' \
    "$(state foulee-relais)" "$(state cloudflared)"
printf '%sComptes%s  %s(les élèves s'"'"'inscrivent eux-mêmes, avec le code d'"'"'invitation de leur coach)%s\n' "$B" "$R" "$D" "$R"
printf '  sudo foulee relais comptes                   tous les comptes (coachs et élèves)\n'
printf '  sudo foulee relais groupes                   chaque coach et ses élèves\n'
printf '  sudo foulee relais coach                     créer un compte coach\n'
printf '  sudo foulee relais mot-de-passe IDENTIFIANT  changer un mot de passe\n'
printf '  sudo foulee relais desactiver IDENTIFIANT    bloquer un compte (reactiver pour le rouvrir)\n'
printf '  sudo foulee relais supprimer IDENTIFIANT     supprimer un compte et ce qu'"'"'il a partagé\n'
printf '%sGarmin%s  %s(envoi des séances sur les montres)%s\n' "$B" "$R" "$D" "$R"
printf '  sudo foulee relais garmin tester             vérifier l'"'"'appli Garmin du club\n'
printf '  sudo foulee relais garmin                    poser l'"'"'identifiant et le secret de l'"'"'appli\n'
printf '%sE-mails%s  %s(notifications par e-mail, service d'"'"'envoi Brevo ou autre SMTP)%s\n' "$B" "$R" "$D" "$R"
printf '  sudo foulee relais email                     poser le service d'"'"'envoi (clé SMTP)\n'
printf '  sudo foulee relais email tester ADRESSE      envoyer un e-mail d'"'"'essai\n'
printf '%sMises à jour et service%s\n' "$B" "$R"
printf '  sudo bash @ROOT@/scripts/mettre-a-jour-serveur.sh   mettre à jour tout de suite\n'
printf '  systemctl status foulee-relais               état du relais\n'
printf '  journalctl -u foulee-relais -n 50            ses derniers messages\n'
printf '  journalctl -u foulee-relais-maj -n 30        la dernière mise à jour automatique\n'
printf '  sudo systemctl restart foulee-relais         relancer le relais\n'
printf '  %sCe message : FOULEE_MOTD=0 dans @ENV@ pour le retirer.%s\n\n' "$D" "$R"
