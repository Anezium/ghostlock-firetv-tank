# Guide Amonet — débloquer / rooter / débloat le Fire TV Stick 2 (`tank`)

> **Guide préparatoire archivé.** L'opération a été effectuée et vérifiée : voir
> [le résultat et les sauvegardes](RESULTAT-ROOT-DEBLOAT.md). Ne pas relancer le
> premier déblocage sur le stick déjà rooté. Le schéma CLK reconstitué et le
> comptage des résistances ne doivent pas servir de repérage pour une intervention.
> Les anciennes formulations « sans danger » et « débrickable par construction »
> étaient trop affirmatives et ne constituent pas des garanties matérielles.

Appareil : AFTT, Fire OS 5.2.9.5 (688805020), noyau 3.10.54+ · Serial `<ton-serial>` (voir `adb devices`; probablement 2018 → bootrom probablement OK)

**Test décisif en 10 min** : le stick est-il débloquable ? → étapes §4–5.
Si le bootrom n'apparaît pas (matériel post-déc-2019), on arrête là, sans aucun risque.

---

## 0. Préparatifs DÉJÀ FAITS sur ce PC

| Élément | Emplacement / version |
|---|---|
| Kit Amonet v1.2.2 (scripts + twrp.img + tz.img + lk.bin + preloader) | `amonet/tank-convert/amonet-tank-v1.2.2/amonet/` |
| Magisk v23.0 (dernier compatible Android 5.x) | `amonet/magisk/Magisk-v23.0.apk` |
| WSL2 `Ubuntu_24_04` | python3 + pyserial 3.5 + adb + fastboot 34.0.4 |
| usbipd-win | 5.3.0 (`C:\Program Files\usbipd-win\usbipd.exe`) |
| ADB Windows | platform-tools 37.0.0 (déjà utilisé pour l'audit) |

Rien d'autre à installer.

---

## 1. Matériel (rien d'exotique, tout se trouve chez soi)

- **Câble micro-USB de transfert de données** (idéalement celui du chargeur du stick ; les câbles « charge only » ne marchent pas).
- **Outil d'ouverture plastique** : une **vieille carte bancaire** suffit (médiator, ongle épais acceptable).
- **Pour soulever le blindage métallique** : petit couteau **émoussé** ou petit tournevis plat fin.
- **Pour le court-circuit** : un **trombone** (idéal), sinon pince à épiler, attache de pain (fil métallique torsadé), bout de fil dénudé.
- Optionnel : une deuxième personne pour brancher le câble (sinon astuce §5.4).

---

## 2. Ouvrir le stick

1. Débrancher de la TV et du secteur. Travailler sur une table claire et éclairée.
2. **Coque plastique** : planter la carte bancaire dans la couture du bord, faire levier doucement jusqu'au « clic » d'un clip, avancer d'un cran, recommencer. Faire le tour des 4 côtés jusqu'à ce que les deux coques se séparent. Extraire la carte mère.
3. **Blindage métallique** : sur la face du port HDMI, il y a un petit blindage métallique **posé** (non soudé, forme de double rectangle couvrant le SoC + la mémoire). Glisser la lame dans les petits interstices (au-dessus / en-dessous du pad noir près du HDMI) et soulever, faire le tour du blindage.
   - ⚠️ Ne pas rayer la carte, et **laisser en place le cadre métallique soudé** (le « rim ») : c'est lui notre **GND**.
4. Garder le blindage retiré à portée de main : il servira de masse au besoin.

---

## 3. Le point CLK (et pourquoi c'est sans danger)

- Près du coin de la puce MediaTek (MT8127), il y a une **rangée de petites résistances** :
  - **1re depuis le coin** : probablement VCCQ (alimentation) → **ne pas toucher** ;
  - 2e : probablement CMD · 3e : probablement DAT0 ;
  - **4e : CLK** ← c'est celle-là.
- **GND** = le cadre métallique soudé (ou le blindage qu'on a retiré, posé en contact).
- Visuel de référence : photo du post #1 du thread XDA (lien en §10).
- ⚠️ Le court-circuit lui-même est **sans danger** : c'est un strap que le bootrom lit au démarrage (court-circuiter CLK à la masse = signal « entre en mode téléchargement »). Le seul risque réel est **mécanique** : déraper avec l'outil et rayer la carte. Outil fin, gestes lents, appui léger.

---

## 4. Préparation logicielle (à faire AVANT le branchement)

### 4.1 Un seul bind usbipd (une fois pour toutes, PowerShell **en administrateur**)

```powershell
& "C:\Program Files\usbipd-win\usbipd.exe" bind -i 0e8d:0003
```

### 4.2 Lancer le script dans WSL (il attend le stick)

```powershell
wsl -d Ubuntu_24_04 -u root
cd /mnt/e/Tools/FireStick/amonet/tank-convert/amonet-tank-v1.2.2/amonet
python3 modules/main.py
```

Il doit afficher `Waiting for bootrom`. **Le laisser tourner.**

---

## 5. Le test décisif : court-circuit + branchement

1. **Ne pas brancher le stick** au PC au départ (câble micro-USB branché au stick mais pas au PC).
2. Former le trombone en **L** : une branche droite, l'autre accrochée.
3. Positionner : la branche courte posée sur la **résistance CLK** (posée, appui léger), la branche longue en contact avec le **cadre métallique**. Astuce solo : accrocher la branche longue sous le bord du cadre pour que ça tienne tout seul ; sinon quelqu'un tient le trombone pendant que l'autre branche.
4. **Brancher le câble au PC en maintenant le court-circuit.** (Un utilisateur du thread a réussi avec une simple pince à épiler sur ce modèle exact.)
5. Côté Windows (PowerShell normal) :

   ```powershell
   & "C:\Program Files\usbipd-win\usbipd.exe" list
   ```

   **Interprétation — c'est ici que tout se joue :**
   - `0e8d:0003  MediaTek Inc. MT6227 phone` → ✅ **bootrom OK, stick débloquable.** Passer à l'attach :
     ```powershell
     & "C:\Program Files\usbipd-win\usbipd.exe" attach -w Ubuntu_24_04 -i 0e8d:0003
     ```
     Le script WSL passe de `Waiting for bootrom` à `Found port = /dev/ttyACM0`.
   - `0e8d:2000  MT65xx Preloader` → court-circuit passé trop tard / raté : débrancher, recommencer §5.4.
   - **Rien n'apparaît** (ni l'un ni l'autre) → ⚠️ très probablement matériel **post-déc-2019** (DL-mode désactivé en usine). Débrancher, retirer le trombone, remonter le stick : **aucune conséquence, il boote normalement.** On stoppe ici (et l'exploit noyau redevient la seule piste logicielle — voir RAPPORT.md).

6. Le script dit `remove the short and press enter` → **retirer le trombone**, puis Entrée dans le WSL.
7. Laisser tourner jusqu'au bout (quelques minutes). En cas de stall : Ctrl+C dans WSL, débrancher, relancer `python3 modules/main.py`, re-court-circuiter et rebrancher. (Le script efface le preloader **en premier** exprès pour qu'un stall retombe en mode bootrom sans re-court-circuiter.)
8. À la fin, le stick reboote tout seul en **fastboot déverrouillé** (logo Amazon figé + LED clignotante).

---

## 6. Flash TWRP (fastboot côté Windows, plus simple que WSL)

Le stick est repassé en mode fastboot — il apparaît côté Windows comme périphérique USB fastboot. On n'a **plus besoin d'usbipd**, le fastboot Windows suffit :

```powershell
cd amonet\tank-convert\amonet-tank-v1.2.2\amonet
$fb = if ($env:FASTBOOT) { $env:FASTBOOT } else { 'fastboot' }
& $fb devices                                   # doit lister le stick
& $fb flash recovery bin\twrp.img
& $fb flash TEE2 bin\tz.img
& $fb oem reboot-recovery
```

→ le stick reboote dans **TWRP**.

---

## 7. Dans TWRP : BACKUP avant toute chose

TWRP est pilotable depuis le PC (`adb devices` doit le voir).

1. Backup **Boot + System** (Data optionnel, il faut de la place) vers le stockage interne :
   ```powershell
   adb shell twrp backup BSD
   ```
2. Le récupérer sur le PC :
   ```powershell
   adb pull /sdcard/TWRP/BACKUPS/ backup-tank\
   ```
3. (Après récupération, on pourra supprimer le backup du stick pour libérer la place.)

---

## 8. Flash Magisk

```powershell
adb push amonet\magisk\Magisk-v23.0.apk /sdcard/
adb shell twrp install /sdcard/Magisk-v23.0.apk
adb reboot
```

(L'APK Magisk est un zip flashable : TWRP l'accepte tel quel. v23.0 = dernière version supportant Android 5.1.)

Au premier `su` depuis `adb shell`, la demande d'autorisation Magisk s'affiche **à l'écran de la TV** → valider avec la télécommande.

---

## 9. Débloat (enfin !) — réversible

Tout se fait en `pm disable-user --user 0` (annulable avec `pm enable`) depuis `adb shell` + `su`.

Priorités :

1. **OTA** (protège aussi l'unlock) :
   ```
   com.amazon.device.software.ota
   com.amazon.device.software.ota.overlay
   ```
2. Gros bloat visible : Amazon Photos, Screensaver, IMDB TV, Prime Video (`com.amazon.avod`), Appstore (`com.amazon.venezia`)…
3. Launcher Amazon : **seulement après** avoir installé un launcher alternatif fonctionnel.

La liste exacte sera générée sur l'appareil au moment venu :
`pm list packages -s | grep amazon` → tri + validation un par un (jamais de suppressions en masse).

---

## 10. Règles d'or après l'unlock

- **Ne jamais flasher boot/recovery hors TWRP** (TWRP patch les images à la volée, FlashFire/Magisk-app flash boot = stick qui ne boote plus).
- OTA désactivées (§9). Si une OTA s'installe quand même : elle ne doit pas toucher LK/Preloader/TZ (TWRP protège), mais on ne tente rien sans vérif.
- Pépin de boot → le bootrom reste accessible : câble + trombone + `boot-fastboot.sh` / `boot-recovery.sh` (dans le dossier du kit, à lancer comme §4.2). **Le stick est débrickable par construction.**

## 11. Sources

- Thread XDA officiel (guide k4y0z, photos des points, vidéo de démontage) : https://xdaforums.com/t/unlock-root-twrp-unbrick-fire-tv-stick-2nd-gen-tank.3907002/
- Code : https://github.com/chaosmaster/amonet (branche `mt8127-tank`) — copie locale : `amonet/amonet-mt8127-tank`
- Package v1.2.2 inclus dans : https://github.com/kerta1n/tank-convert (option LineageOS 12.1 = débloat ultime, à envisager APRÈS un backup complet)
