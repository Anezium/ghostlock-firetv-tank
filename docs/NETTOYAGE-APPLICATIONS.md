# Nettoyage des applications du Fire TV Stick tank

Le 25 octobre 2026, l'utilisateur a demandé la désinstallation des applications
ci-dessous, y compris Downloader et Send Files to TV puisque les installations
et transferts peuvent être réalisés par ADB depuis son PC.

## Applications retirées

- Plex : `com.plexapp.android`
- Molotov : `tv.molotov.app`
- Cloudstream : `com.lagradost.cloudstream3`
- Sparkle : `se.hedekonsult.sparkle`
- Classy Player : `com.classyplayerott.player`
- Downloader : `com.esaba.downloader`
- Send Files to TV : `com.yablio.sendfilestotv`
- Pokémon TV : `com.pokemontv`
- Amazon Music : `com.amazon.bueller.music`
- Amazon miniTV : `com.amazon.minitv.android.app`
- Amazon Game Hub : `com.amazon.gamehub`

Les onze désinstallations ont renvoyé `Success`. La commande employée est
`pm uninstall --user 0`, sans conserver les données des applications retirées.
Pour les trois applications système Amazon, le retrait concerne le profil
utilisateur ; leurs fichiers intégrés à la ROM restent sur la partition système.
Aucun fichier de la partition système n'a été supprimé manuellement.

## Applications et fonctions conservées

Kodi, LeanbackOnFire, Magisk et Mouse Toggle sont conservés, ainsi que Prime Video,
l'Appstore, Alexa, WebView, les réglages, le clavier, le Bluetooth et les services
de télécommande. Les désactivations OTA et le précédent débloat restent en place.
Les autres composants Amazon précédemment désactivés n'ont pas été désinstallés.

Inventaire initial, résultats de chaque retrait et vérification après redémarrage :
`analysis/app-cleanup-20261025/`. Le fichier `verification.json` consigne le root,
Home, les réglages, l'absence de changements inattendus et l'espace disponible.

Vérification après redémarrage réussie : démarrage complet, root présent,
Leanback sur Home, réglages Amazon accessibles, composants conservés activés,
blocages précédents conservés et aucun changement de paquet inattendu.
L'espace libre sur `/data` passe de 2 444 443 648 à 3 160 846 336 octets,
soit 716 402 688 octets supplémentaires disponibles (environ 716 Mo).

## Utiliser ADB depuis le PC

Le SDK installé sur le PC fournit ADB ; s'il n'est pas dans le `PATH`, pointe-le
avec `$env:ADB`. Cible toujours ce Stick avec `-s $serial`, car il peut aussi
apparaître en Wi-Fi ou d'autres appareils Android peuvent être connectés.

```powershell
$adbPath = if ($env:ADB) { $env:ADB } else { 'adb' }
& $adbPath devices                       # relever le numéro de série du Stick
$serial = $env:TANK_SERIAL                # ou le passer en dur / en argument
& $adbPath -s $serial install -r 'C:/chemin/application.apk'
& $adbPath -s $serial push 'C:/chemin/fichier.mp4' /sdcard/Download/
& $adbPath -s $serial pull /sdcard/Download/fichier.mp4 'C:/chemin/'
```

ADB remplace ces deux outils pour les opérations depuis un ordinateur connecté.
Le Stick n'a plus Downloader ni Send Files to TV pour effectuer leurs opérations
directement depuis la TV ou leur interface de transfert depuis un téléphone.
