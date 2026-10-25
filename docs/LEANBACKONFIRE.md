# LeanbackOnFire sur le Fire TV Stick tank

Après cette installation, l'utilisateur a demandé un
[nettoyage de onze applications](NETTOYAGE-APPLICATIONS.md), réalisé et vérifié
après redémarrage. Les mentions de conservation intégrale ci-dessous décrivent
uniquement l'étape d'installation du launcher.

APK officiel 1.63, installé le 25 octobre 2026 sur AFTT / tank,
numéro de série G070L81694972B80, Fire OS 5 / Android 5.1.1.

Source : https://github.com/tsynik/LeanbackLauncher/releases/tag/v1.63

SHA-256 de l'APK :
`98824777eb845204fc82022a88b82dbce9940a802eaa0f55a28b58cdb9e5cacc`.
Signature APK v1 et v2 vérifiée, API minimum 22, ABI armeabi-v7a présente.

## Accueil et réglages

Seuls le paquet `com.amazon.firehomestarter` et le composant
`com.amazon.tv.launcher/.ui.HomeActivity_vNext` ont été désactivés pour
rediriger Home. Le paquet Amazon Launcher reste activé : ses autres activités,
dont `.ui.MainSettingsActivity`, servent encore aux réglages Fire OS.
Le raccourci Système de Leanback utilise cette dernière activité sur Fire OS.
L'action Android générique `android.settings.SETTINGS` ne fonctionne pas avec
cette configuration : elle passe par un intermédiaire Amazon qui revient à Home.

Le lancement de Kodi depuis une tuile Leanback et l'ouverture de l'écran de
réglages Amazon ont été observés. Les captures et diagnostics sont dans
`analysis/launchers/`. Le fichier `verification.json`, lorsqu'il est présent,
contient le résultat des vérifications après redémarrage réel.
La vérification à 18h07 a réussi : démarrage complet, Home sur Leanback,
réglages Amazon ouverts, root présent, aucun paquet original manquant et
tous les blocages précédents conservés.

Aucune application existante n'a été désinstallée ou effacée. Les blocages OTA
et le débloat précédent sont conservés. Aucun accès aux notifications ou droit
root supplémentaire n'a été accordé au launcher.

## Revenir à l'accueil Amazon

Avec le Stick connecté à ce PC, exécuter :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:/Tools/FireStick/scripts/RESTORE-AMAZON-HOME.ps1
```

Le script réactive l'accueil Amazon et son starter, puis ouvre l'accueil Amazon.
Leanback reste installé. Le root et les blocages OTA ne sont pas modifiés.

La capture ne mesure pas la fluidité à la télécommande, la stabilité sur plusieurs
jours, ni la lecture vidéo : ces points restent à vérifier en usage sur TV.
