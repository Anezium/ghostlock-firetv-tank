# Fire TV Stick tank : résultat du 25 octobre 2026

Nettoyage ultérieur demandé par l'utilisateur : onze applications désinstallées,
dont Amazon Music, miniTV et Game Hub pour le profil utilisateur. Après un nouveau
redémarrage, root, Home et réglages ont été vérifiés ; environ 716 Mo libérés.
Voir [le détail du nettoyage](NETTOYAGE-APPLICATIONS.md).

Mise à jour à 18h07 : [LeanbackOnFire 1.63](LEANBACKONFIRE.md) installé à la
demande de l'utilisateur. Il remplace maintenant l'accueil Amazon ; Home,
réglages Amazon, root et conservation des applications ont été revérifiés
après redémarrage. Les résultats ci-dessous décrivent le root/débloat initial.

Fire OS conservé : AFTT / tank, Android 5.1.1, build
`288.6.8.8_user_688805020`. Aucune remise à zéro, aucune désinstallation de paquet.

Le BootROM a été atteint en USB, le payload Amonet a démarré, puis les lectures
GPT/BOOT0/RPMB et les écritures du déblocage ont réussi. TWRP 3.2.3-0 a ensuite
démarré et Magisk 23.0 a été installé depuis TWRP, avec réapplication du patch
de démarrage Amonet. Après un nouveau redémarrage normal :

- `sys.boot_completed=1` ; `su -c id` renvoie `uid=0(root)`, contexte Magisk.
- Magisk indique `23.0:MAGISK` et son application de gestion est installée.
- Les 39 paquets relevés dans `/data/app` avant le root sont toujours présents.
  Cet inventaire inclut aussi des mises à jour d'applications Amazon.
- L'accueil Amazon est lancé ; Prime Video, Appstore, paramètres et Vizzini
  sont activés. Les applications tierces sont conservées.
- Les dix désactivations ci-dessous persistent après redémarrage.

## Désactivations réversibles

| Rôle | Paquet |
| --- | --- |
| Mise à jour OTA | `com.amazon.device.software.ota` |
| Composant OTA | `com.amazon.device.software.ota.override` |
| Mise à jour OTA forcée | `com.amazon.tv.forcedotaupdater.v2` |
| Composant de mise à niveau | `com.amazon.tv.easyupgrade` |
| Photos | `com.amazon.bueller.photos` |
| Écran de veille | `com.amazon.ftv.screensaver` |
| Achats Alexa | `com.amazon.alexashopping` |
| Shop TV | `com.amazon.shoptv.client` |
| Shop TV Fire TV | `com.amazon.shoptv.firetv.client` |
| Démonstration magasin | `com.amazon.kor.demo` |

La désactivation utilise `pm disable-user --user 0` ; les données des applications
ne sont pas effacées. Le script `../scripts/UNDO-DEBLOAT.ps1` réactive les six
applications optionnelles. Il laisse les quatre composants OTA désactivés pour
préserver l'installation root. Son exécution nécessite ce PC relié au stick et
l'accès ADB/Magisk déjà configuré.

## Preuves et sauvegardes

Dossier de cette exécution : `../analysis/amonet-live-20261025-154149/`.

- `final-verification.json` : vérification après redémarrage, root, paquets et accueil.
- `backup/` : RPMB original, début de BOOT0, GPT, UBOOT, TEE1 et premiers secteurs
  de boot/MISC avant les écritures Amonet ; manifeste SHA-256 vérifié et CRC GPT valide.
- `recovery-backup/` : image boot complète avant Magisk, 16 777 216 octets, et
  image système complète, 901 775 360 octets ; manifeste SHA-256.
- `recovery-after-magisk.log` : installation Magisk terminée avec RC=0 et patch
  Amonet réappliqué avec succès.
- `debloat-before.json`, `debloat-result.json` : états des paquets et changements.

L'accès root pour l'UID ADB 2000 a été autorisé dans Magisk pour cette maintenance ;
les demandes d'autres applications ne sont pas automatiquement autorisées.
La clé ADB de ce PC était déjà présente et n'a pas été remplacée.

Les transferts USB ont été intermittents ; la sauvegarde finale du système a été
faite par blocs de 4 Mio, chacun contrôlé en taille avant enregistrement. Les
copies interrompues n'ont pas été utilisées comme sauvegardes validées.

L'usage vidéo réel et la navigation avec la télécommande restent à vérifier sur
la TV ; les contrôles ci-dessus ont été faits par ADB. Aucun gain de performances
chiffré n'est revendiqué.

## Au retour devant le stick

Débrancher l'USB avant de remettre le pad thermique, le capot métallique et la
coque. Rebrancher ensuite pour l'usage normal. Il n'y a plus de manipulation CLK
à faire pour démarrer normalement.

Pour une future intervention sur boot/recovery, employer la procédure TWRP
adaptée à Amonet. Ne pas relancer le premier déblocage sur ce stick déjà préparé.
Les anciennes garanties « sans danger » ou « débrickable par construction » du
guide préparatoire étaient trop affirmatives ; elles ne constituent pas des
garanties matérielles.
